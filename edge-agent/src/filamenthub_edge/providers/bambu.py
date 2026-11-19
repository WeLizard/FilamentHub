"""Bambu Lab observations over the printer's LAN MQTT service.

A Bambu printer runs an MQTT broker on port 8883 behind TLS. A client logs in
as ``bblp`` with the access code shown on the printer's screen and receives
status reports on ``device/<serial>/report``. X1 printers repeat the whole
report; P1 and A1 printers send it once when asked (``pushall``) and after
that only what changed, so the reports are merged here. The whole report is
asked for once per connection: asking often slows the smaller printers down.

The connection stays open between observations. A reader thread keeps the
merged report current and ``observe`` returns what it holds; when the link
drops, the report is discarded and ``observe`` fails until a new one arrives.

Reading a report is shared with the OrcaSlicer plugin (``_bambu_report``), as
is the rule for whose certificate is accepted (``_bambu_trust``). The network
code is Edge's own: the plugin's is tied to OrcaSlicer's lifecycle.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import logging
import math
import re
import secrets
import select
import socket
import ssl
import struct
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..errors import ProviderUnavailable, StateError
from ..storage import JsonStateFile
from ._bambu_report import (
    BAMBU_EXTERNAL_TRAY_DEPUTY,
    BAMBU_EXTERNAL_TRAY_MAIN,
    BAMBU_WIDE_UNIT_BASE,
    _bambu_int,
    _bambu_tag_read_capable,
    parse_bambu_feed,
)
from ._bambu_trust import (
    BAMBU_CA_CERTIFICATES,
    bambu_certificate_fingerprint,
    bambu_certificate_serial,
)
from .base import ProviderSnapshot
from .moonraker import _tag_uid

logger = logging.getLogger("filamenthub_edge.bambu")

MQTT_PORT = 8883
IDENTITY_KIND = "bambu_serial"
SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9._-]{4,80}$")
KEEPALIVE_S = 60
PING_INTERVAL_S = 20.0
# A live link answers a ping within this time even when the printer is idle.
SILENCE_LIMIT_S = 60.0
RETRY_INITIAL_S = 5.0
RETRY_MAX_S = 300.0
# A refused access code or certificate does not fix itself in seconds.
RETRY_REFUSED_S = 60.0
MAX_PACKET_BYTES = 2 * 1024 * 1024
MAX_TRUST_BYTES = 4096
_STATES = {
    "RUNNING": "printing",
    "PAUSE": "paused",
    "PAUSED": "paused",
    "IDLE": "idle",
    "FINISH": "finished",
    "FAILED": "failed",
    "PREPARE": "preparing",
    "SLICING": "preparing",
}
NO_ANSWER = "Bambu printer did not answer"
NO_REPORT = "Bambu printer accepted the connection but sent no report; check the serial number"
ACCESS_REFUSED = "Bambu printer rejected the access code"


class CertificateRejected(ProviderUnavailable):
    """The device at the printer's address is not the printer that was linked."""


class _AccessRefused(Exception):
    pass


def normalize_serial(value: str) -> str:
    serial = value.strip()
    if not SERIAL_PATTERN.fullmatch(serial):
        raise ValueError("invalid Bambu serial number")
    return serial.upper()


def resolve_printer(host: str, port: int) -> tuple[socket.AddressFamily, tuple[Any, ...]]:
    """Resolve once and accept only an address inside the local network.

    The access code is sent to whatever answers there, so it never goes to an
    address on the public internet.
    """
    try:
        candidates = socket.getaddrinfo(
            host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
    except (OSError, UnicodeError) as exc:
        raise ProviderUnavailable("Bambu printer address could not be resolved") from exc
    for family, _, _, _, sockaddr in candidates:
        try:
            address = ipaddress.ip_address(str(sockaddr[0]).split("%")[0])
        except ValueError:
            continue
        local = address.is_private or address.is_link_local or address.is_loopback
        if local and not (address.is_multicast or address.is_unspecified):
            return family, sockaddr
    raise ProviderUnavailable("Bambu printer address must be inside the local network")


def _tls_context(*, verify: bool) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # A printer certificate names a serial number, not a host; the caller
    # compares it.
    context.check_hostname = False
    if verify:
        context.verify_mode = ssl.CERT_REQUIRED
        # Bambu Lab's root certificates do not satisfy the strict X.509 checks
        # that newer Python turns on by default.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        context.load_verify_locations(cadata=BAMBU_CA_CERTIFICATES)
    else:
        context.verify_mode = ssl.CERT_NONE
    return context


def _handshake(
    family: socket.AddressFamily, sockaddr: tuple[Any, ...], timeout: float, *, verify: bool
) -> ssl.SSLSocket:
    raw = socket.socket(family, socket.SOCK_STREAM)
    raw.settimeout(timeout)
    try:
        raw.connect(sockaddr)
        return _tls_context(verify=verify).wrap_socket(raw, server_hostname=None)
    except BaseException:
        raw.close()
        raise


def open_printer(
    family: socket.AddressFamily,
    sockaddr: tuple[Any, ...],
    *,
    serial: str,
    pinned: str,
    timeout: float,
) -> ssl.SSLSocket:
    """Connect to the printer that was linked and to nobody else.

    A linked printer is recognised by the certificate it showed when it last
    accepted the access code. A different certificate is accepted only when
    Bambu Lab issued it to the same serial number; otherwise nothing, the
    access code included, is sent. A printer seen for the first time is
    trusted as it is: newer models are issued by certificates this build may
    not carry yet, so the chain alone cannot be required of everyone.
    """
    deadline = time.monotonic() + timeout

    def handshake(*, verify: bool) -> ssl.SSLSocket:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Bambu TLS connection timed out")
        return _handshake(family, sockaddr, remaining, verify=verify)

    sock = handshake(verify=False)
    if pinned and bambu_certificate_fingerprint(sock.getpeercert(True)) != pinned:
        sock.close()
        try:
            sock = handshake(verify=True)
        except ssl.SSLCertVerificationError:
            raise CertificateRejected("Bambu printer certificate changed") from None
        if bambu_certificate_serial(sock.getpeercert()) != serial:
            sock.close()
            raise CertificateRejected("Bambu certificate names another printer")
    sock.settimeout(timeout)
    return sock


class CertificateMemory:
    """The certificate a printer showed when it last accepted the access code."""

    def __init__(self, path: Path | None) -> None:
        self._file = JsonStateFile(path) if path is not None else None
        self._held: dict[str, str] = {}

    def pinned(self, serial: str) -> str:
        if serial in self._held:
            return self._held[serial]
        if self._file is None:
            return ""
        try:
            document = self._file.read_document(max_bytes=MAX_TRUST_BYTES) or {}
        except StateError:
            # An unreadable file is no evidence; the next accepted login rewrites it.
            return ""
        certificate = document.get("certificate")
        if (
            document.get("serial") != serial
            or not isinstance(certificate, str)
            or not re.fullmatch(r"[0-9a-f]{64}", certificate)
        ):
            return ""
        self._held[serial] = certificate
        return certificate

    def remember(self, serial: str, fingerprint: str) -> None:
        if not fingerprint or self.pinned(serial) == fingerprint:
            return
        self._held = {serial: fingerprint}
        if self._file is None:
            return
        try:
            self._file.write_document(
                {"serial": serial, "certificate": fingerprint}, max_bytes=MAX_TRUST_BYTES
            )
        except StateError:
            # Held for this run; the next start learns it again.
            logger.warning("Bambu printer certificate could not be saved")

    def forget(self) -> None:
        self._held = {}
        if self._file is None:
            return
        try:
            self._file.write_document({}, max_bytes=MAX_TRUST_BYTES)
        except StateError:
            logger.warning("Bambu printer certificate could not be forgotten")


def _remaining_length(length: int) -> bytes:
    encoded = bytearray()
    while True:
        digit = length & 0x7F
        length >>= 7
        if length:
            digit |= 0x80
        encoded.append(digit)
        if not length:
            return bytes(encoded)


def _field(payload: bytes) -> bytes:
    return struct.pack("!H", len(payload)) + payload


class _Link:
    """MQTT framing over one socket, every read bounded by a deadline."""

    def __init__(self, sock: Any) -> None:
        self.sock = sock

    def send(self, kind: int, body: bytes = b"") -> None:
        self.sock.sendall(bytes([kind]) + _remaining_length(len(body)) + body)

    def readable(self, wait: float) -> bool:
        pending = getattr(self.sock, "pending", None)
        if callable(pending) and pending():
            return True
        return bool(select.select([self.sock], [], [], wait)[0])

    def _receive(self, length: int, deadline: float) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Bambu MQTT timed out")
            self.sock.settimeout(max(0.1, remaining))
            try:
                chunk = self.sock.recv(length - len(chunks))
            except TimeoutError:
                continue
            if not chunk:
                raise ConnectionError("Bambu MQTT connection closed")
            chunks.extend(chunk)
        return bytes(chunks)

    def packet(self, deadline: float) -> tuple[int, bytes]:
        header = self._receive(1, deadline)[0]
        length = 0
        multiplier = 1
        for _ in range(4):
            digit = self._receive(1, deadline)[0]
            length += (digit & 0x7F) * multiplier
            if length > MAX_PACKET_BYTES:
                raise ValueError("Bambu MQTT packet exceeds the limit")
            if not digit & 0x80:
                return header, self._receive(length, deadline) if length else b""
            multiplier *= 128
        raise ValueError("invalid MQTT remaining length")


def merge_report(previous: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Lay a partial report over what is known.

    Objects merge by field. Lists whose items carry an ``id`` (AMS units,
    trays) merge by that id, because a partial report names only the items
    that changed. Anything else is replaced.
    """
    result = dict(previous)
    for key, value in update.items():
        old = result.get(key)
        if isinstance(old, dict) and isinstance(value, dict):
            result[key] = merge_report(old, value)
        elif (
            isinstance(old, list)
            and isinstance(value, list)
            and value
            and all(isinstance(item, dict) and "id" in item for item in (*old, *value))
        ):
            indexed = {str(item["id"]): item for item in old}
            for item in value:
                indexed[str(item["id"])] = merge_report(indexed.get(str(item["id"]), {}), item)
            result[key] = list(indexed.values())
        else:
            result[key] = value
    return result


def _has_feed(report: dict[str, Any]) -> bool:
    return any(name in report for name in ("ams", "vt_tray", "vir_slot"))


def _number(value: Any, low: float, high: float) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and low <= number <= high else None


def _integer(value: Any, low: int, high: int) -> int | None:
    number = _bambu_int(value)
    return number if number is not None and low <= number <= high else None


def build_printer(report: dict[str, Any]) -> dict[str, Any]:
    state = str(report.get("gcode_state") or "").strip().upper()
    printer: dict[str, Any] = {"state": _STATES.get(state, "unknown")}
    progress = _bambu_int(report.get("mc_percent"))
    remaining_minutes = _integer(report.get("mc_remaining_time"), 0, 43_200)
    job = report.get("subtask_name") or report.get("gcode_file")
    wifi = report.get("wifi_signal")
    error = report.get("print_error")
    for key, value in (
        ("progress_percent", None if progress is None else max(0, min(progress, 100))),
        ("remaining_seconds", None if remaining_minutes is None else remaining_minutes * 60),
        ("current_layer", _integer(report.get("layer_num"), 0, 10_000_000)),
        ("total_layers", _integer(report.get("total_layer_num"), 0, 10_000_000)),
        ("job_name", job[:300] if isinstance(job, str) and job else None),
        ("nozzle_temperature", _number(report.get("nozzle_temper"), -100, 600)),
        ("nozzle_target_temperature", _number(report.get("nozzle_target_temper"), -100, 600)),
        ("bed_temperature", _number(report.get("bed_temper"), -100, 250)),
        ("bed_target_temperature", _number(report.get("bed_target_temper"), -100, 250)),
        ("chamber_temperature", _number(report.get("chamber_temper"), -100, 150)),
        ("wifi_signal", str(wifi).strip()[:32] if wifi else None),
        ("error_code", str(error)[:80] if error not in (None, 0, "0", "") else None),
    ):
        if value not in (None, ""):
            printer[key] = value
    return printer


def slot_label(index: int) -> str:
    if index == BAMBU_EXTERNAL_TRAY_MAIN:
        return "External spool"
    if index == BAMBU_EXTERNAL_TRAY_DEPUTY:
        return "External spool 2"
    if index >= BAMBU_WIDE_UNIT_BASE:
        return f"AMS HT {index - BAMBU_WIDE_UNIT_BASE + 1}"
    return f"AMS {index // 4 + 1} · {index % 4 + 1}"


def build_slots(report: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Return the feed slots and whether the report described the whole feed."""
    feed = parse_bambu_feed(report)
    if feed is None:
        return [], False
    active = feed.get("active_index")
    slots: list[dict[str, Any]] = []
    for parsed in feed["slots"]:
        index = parsed["index"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 1023:
            return [], False
        slot: dict[str, Any] = {
            "provider_index": index,
            "label": slot_label(index),
            "kind": (
                "external"
                if index in {BAMBU_EXTERNAL_TRAY_MAIN, BAMBU_EXTERNAL_TRAY_DEPUTY}
                else "slot"
            ),
            "present": parsed.get("present"),
            "active_feed": index == active if active is not None else None,
        }
        material = parsed.get("material")
        for key, value in (
            ("material", material[:80] if isinstance(material, str) else None),
            ("color_hex", parsed.get("color_hex")),
            ("remaining_percent", _integer(parsed.get("remaining_pct"), 0, 100)),
            ("remaining_grams", _integer(parsed.get("remaining_g"), 0, 100_000)),
        ):
            if value is not None:
                slot[key] = value
        tag_uid = _tag_uid(parsed.get("provider_uid"))
        if tag_uid is not None:
            slot["tag_uid"] = tag_uid
            # The report proves an identifier, not the radio technology.
            slot["tag_technology"] = "unknown"
        slots.append(slot)
    return slots, True


class BambuProvider:
    def __init__(
        self,
        host: str,
        *,
        serial_number: str,
        access_code: str,
        timeout: float,
        trust_path: Path | None = None,
        port: int = MQTT_PORT,
        connect: Callable[[], Any] | None = None,
    ) -> None:
        self.serial_number = normalize_serial(serial_number)
        self._host = host
        self._port = port
        self._access_code = access_code
        self._timeout = float(timeout)
        self._memory = CertificateMemory(trust_path)
        self._connect = connect or self._open
        self._lock = threading.Lock()
        self._complete = threading.Event()
        # Set while the reader waits before its next attempt: nothing will
        # arrive, so an observation need not wait for it.
        self._resting = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._report: dict[str, Any] | None = None
        self._heard_at = 0.0
        self._failure = NO_ANSWER
        self._logged: str | None = None
        self._tags_seen = False

    def capabilities(self) -> list[str]:
        capabilities = ["read", "presence"]
        if self._tags_seen:
            capabilities.append("tag_read")
        return capabilities

    def observe(self) -> ProviderSnapshot:
        self._start()
        # Wait for the whole report; one that never names the feed still
        # carries the printer's state and is returned as incomplete.
        deadline = time.monotonic() + self._timeout
        while not self._complete.wait(0.2):
            if self._resting.is_set() or time.monotonic() >= deadline:
                break
        with self._lock:
            report = copy.deepcopy(self._report)
            silent = time.monotonic() - self._heard_at > SILENCE_LIMIT_S
            failure = self._failure
            repeated = failure == self._logged
        if report is None or "gcode_state" not in report or silent:
            if not repeated:
                self._logged = failure
                logger.warning("%s", failure)
            raise ProviderUnavailable(failure)
        if self._logged is not None:
            self._logged = None
            logger.info("Bambu printer is reporting again")
        slots, complete = build_slots(report)
        return ProviderSnapshot(
            printer=build_printer(report),
            slots=slots,
            slot_topology_complete=complete,
            capabilities=self.capabilities(),
            # The printer publishes only on the topic of its own serial number,
            # so a report received there is the device naming itself.
            device_identity=(IDENTITY_KIND, self.serial_number),
        )

    def forget(self) -> None:
        """Drop the remembered certificate: the connection is being set up anew."""
        self._memory.forget()

    def close(self) -> None:
        """Leave the printer; a later observation connects again."""
        with self._lock:
            thread, self._thread = self._thread, None
            self._stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(self._timeout + 2)

    def _start(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop = threading.Event()
                self._resting.clear()
                self._thread = threading.Thread(
                    target=self._run, args=(self._stop,), name="edge-bambu-mqtt", daemon=True
                )
                self._thread.start()

    def _open(self) -> ssl.SSLSocket:
        family, sockaddr = resolve_printer(self._host, self._port)
        return open_printer(
            family,
            sockaddr,
            serial=self.serial_number,
            pinned=self._memory.pinned(self.serial_number),
            timeout=self._timeout,
        )

    def _explain(self, failure: str) -> None:
        with self._lock:
            self._failure = failure

    def _run(self, stop: threading.Event) -> None:
        delay = RETRY_INITIAL_S
        while not stop.is_set():
            refused = False
            try:
                self._session(stop)
            except _AccessRefused:
                refused = True
                self._explain(ACCESS_REFUSED)
            except CertificateRejected as exc:
                refused = True
                self._explain(str(exc))
            except ProviderUnavailable as exc:
                self._explain(str(exc))
            except (OSError, ValueError):
                with self._lock:
                    reported = self._report is not None
                # A link that never produced a report keeps its own explanation.
                if reported or self._failure != NO_REPORT:
                    self._explain(NO_ANSWER)
            except Exception:
                logger.error("Bambu reader stopped on an unexpected failure")
                self._explain(NO_ANSWER)
            with self._lock:
                had_report = self._report is not None
                self._report = None
                self._complete.clear()
            if had_report:
                delay = RETRY_INITIAL_S
            self._resting.set()
            try:
                if stop.wait(max(delay, RETRY_REFUSED_S) if refused else delay):
                    return
            finally:
                self._resting.clear()
            delay = min(delay * 2, RETRY_MAX_S)

    def _session(self, stop: threading.Event) -> None:
        sock = self._connect()
        link = _Link(sock)
        try:
            deadline = time.monotonic() + self._timeout
            connect = (
                _field(b"MQTT")
                + bytes([4, 0xC2])
                + struct.pack("!H", KEEPALIVE_S)
                + _field(("fhedge-" + secrets.token_hex(6)).encode("ascii"))
                + _field(b"bblp")
                + _field(self._access_code.encode("utf-8"))
            )
            link.send(0x10, connect)
            header, answer = link.packet(deadline)
            if (header & 0xF0) != 0x20 or len(answer) < 2:
                raise ConnectionError("Bambu MQTT gave an unexpected answer")
            if answer[1] != 0:
                raise _AccessRefused()
            # Remembered only now: a device that merely answered at the address
            # has not shown that it is the printer.
            peer = getattr(sock, "getpeercert", None)
            if callable(peer):
                self._memory.remember(
                    self.serial_number, bambu_certificate_fingerprint(peer(True))
                )
            topic = f"device/{self.serial_number}/report".encode("ascii")
            link.send(0x82, struct.pack("!H", 1) + _field(topic) + b"\x00")
            header, answer = link.packet(deadline)
            if (header & 0xF0) != 0x90 or len(answer) < 3 or answer[2] == 0x80:
                raise ConnectionError("Bambu MQTT subscription rejected")
            self._explain(NO_REPORT)
            request = json.dumps(
                {"pushing": {"sequence_id": "0", "command": "pushall"}}, separators=(",", ":")
            ).encode("utf-8")
            link.send(
                0x30, _field(f"device/{self.serial_number}/request".encode("ascii")) + request
            )
            heard = pinged = time.monotonic()
            while not stop.is_set():
                now = time.monotonic()
                if now - heard > SILENCE_LIMIT_S:
                    raise TimeoutError("Bambu MQTT went silent")
                if now - pinged >= PING_INTERVAL_S:
                    link.send(0xC0)
                    pinged = now
                if not link.readable(0.25):
                    continue
                header, body = link.packet(time.monotonic() + self._timeout)
                heard = time.monotonic()
                with self._lock:
                    self._heard_at = heard
                if (header & 0xF0) == 0x30:
                    self._published(header, body, topic)
        finally:
            try:
                sock.sendall(b"\xe0\x00")
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def _published(self, header: int, body: bytes, expected_topic: bytes) -> None:
        if len(body) < 2:
            return
        topic_length = struct.unpack("!H", body[:2])[0]
        offset = 2 + topic_length
        if len(body) < offset or body[2:offset] != expected_topic:
            return
        quality = (header >> 1) & 0x03
        if quality == 0x03:
            return
        if quality:
            offset += 2
        try:
            message = json.loads(body[offset:].decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return
        report = message.get("print") if isinstance(message, dict) else None
        if not isinstance(report, dict):
            return
        with self._lock:
            merged = merge_report(self._report or {}, report)
            self._report = merged
            if _bambu_tag_read_capable(merged):
                self._tags_seen = True
            if "gcode_state" in merged:
                # A later failure of this link is a lost printer, not a wrong serial.
                self._failure = NO_ANSWER
                if _has_feed(merged):
                    self._complete.set()
