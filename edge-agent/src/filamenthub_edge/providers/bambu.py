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

The printer measures no filament. Usage is the slicer's estimate for the job,
read from the file being printed and followed by layer or progress; where no
file can be read, a Bambu spool's own remaining-weight figure is followed
instead. The bookkeeping is the plugin's (``_bambu_usage``), so a print costs
the same whichever of the two watched it.

Reading a report is shared with the OrcaSlicer plugin (``_bambu_report``), as
is the rule for whose certificate is accepted (``_bambu_trust``, applied in
``bambu_tls``). The network code is Edge's own: the plugin's is tied to
OrcaSlicer's lifecycle.
"""

from __future__ import annotations

import copy
import ftplib
import json
import logging
import math
import re
import secrets
import select
import ssl
import struct
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errors import ProviderUnavailable
from ..state import EdgeState
from ._bambu_report import (
    BAMBU_EXTERNAL_TRAY_DEPUTY,
    BAMBU_EXTERNAL_TRAY_MAIN,
    BAMBU_WIDE_UNIT_BASE,
    _bambu_int,
    _bambu_tag_read_capable,
    parse_bambu_feed,
)
from ._bambu_trust import bambu_certificate_fingerprint
from ._bambu_usage import (
    _bambu_file_candidates,
    _bambu_job_key,
    _bambu_keep_gap_safe_baselines,
    _buffer_bambu_usage_report,
    capture_bambu_usage,
)
from .bambu_files import READ_ERRORS, read_job_estimate
from .bambu_tls import CertificateMemory, CertificateRejected, open_printer, resolve_printer
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
# A file that could not be read is asked for again only after a while: the
# printer is busy printing.
ESTIMATE_RETRY_S = 600.0
# Usage events one observation may queue; the rest wait for the next one.
MAX_EVENTS_PER_CAPTURE = 64
_JOB_IDENTITY = ("task_id", "subtask_id", "gcode_file", "subtask_name")
# What the last report of a finished job says about a job that is starting.
_JOB_PROGRESS = ("mc_percent", "mc_remaining_time", "layer_num", "total_layer_num", "print_error")
_ESTIMATE_STATES = frozenset({"RUNNING", "PAUSE", "FINISH", "FAILED"})
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


class _AccessRefused(Exception):
    pass


def normalize_serial(value: str) -> str:
    serial = value.strip()
    if not SERIAL_PATTERN.fullmatch(serial):
        raise ValueError("invalid Bambu serial number")
    return serial.upper()


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


def carry_over(known: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """What stays known about the printer when ``update`` arrives.

    A partial report is laid over the last one, so a job that starts would
    inherit the finished job's progress, and a job with another name the
    finished job's filament-to-slot mapping, until the printer says otherwise.
    """
    if any(
        update.get(name) and known.get(name) and update[name] != known[name]
        for name in _JOB_IDENTITY
    ):
        known = {key: value for key, value in known.items() if key != "ams_mapping"}
    if update.get("gcode_state") in {"PREPARE", "RUNNING"} and known.get("gcode_state") in {
        "FINISH",
        "FAILED",
        "IDLE",
    }:
        known = {key: value for key, value in known.items() if key not in _JOB_PROGRESS}
    return known


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
        read_estimate: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> None:
        self.serial_number = normalize_serial(serial_number)
        self._host = host
        self._port = port
        self._access_code = access_code
        self._timeout = float(timeout)
        self._memory = CertificateMemory(trust_path)
        self._connect = connect or self._open
        self._read_estimate = read_estimate or self._read_job_file
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
        # Reports that changed what a job has used, kept until they are counted.
        self._stream: dict[str, Any] = {}
        self._estimate: dict[str, Any] | None = None
        self._estimate_job: str | None = None
        self._estimate_retry_at = 0.0
        self._estimate_note: str | None = None

    def capabilities(self) -> list[str]:
        capabilities = ["read", "presence", "consumption"]
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

    def capture_usage(self, state: EdgeState, *, observed_at: str) -> list[dict[str, Any]]:
        """Count the reports gathered since the last call into usage events.

        The books are kept in ``state.usage_tracker`` and so survive a restart.
        Without the site's current assignments nothing is counted and the
        reports wait: a spool is charged only through a slot it is known to be in.
        """
        desired = state.desired_snapshot
        with self._lock:
            pending = list(self._stream.get("usage_reports", []))
        if not isinstance(desired, dict) or not pending:
            return []
        books = state.usage_tracker
        if not isinstance(books, dict) or books.get("provider") != "bambu":
            books = {"provider": "bambu"}
        events: list[dict[str, Any]] = []
        for observation in pending:
            if len(events) >= MAX_EVENTS_PER_CAPTURE:
                break
            report = observation["report"]
            tracker = books.get("tracker")
            if report.pop("_fh_observation_gap", False) and isinstance(tracker, dict):
                # A slicer figure resumes along its own curve; a sensor reading starts anew.
                _bambu_keep_gap_safe_baselines(tracker)
            events.extend(
                capture_bambu_usage(
                    books, report, desired, self._estimate_for(report), observation["observed_at"]
                )
            )
            with self._lock:
                queue = self._stream.get("usage_reports", [])
                if queue and queue[0] is observation:
                    queue.pop(0)
        tracker = books.get("tracker")
        # What the runtime asks before a connection may be reset.
        books["terminal_emitted"] = not isinstance(tracker, dict) or bool(
            tracker.get("terminal") or tracker.get("inactive")
        )
        state.usage_tracker = books
        return events

    def _estimate_for(self, report: dict[str, Any]) -> dict[str, Any] | None:
        job = _bambu_job_key(report)
        if job != self._estimate_job:
            self._estimate_job = job
            self._estimate = None
            self._estimate_retry_at = 0.0
        if (
            self._estimate is not None
            or str(report.get("gcode_state") or "").upper() not in _ESTIMATE_STATES
            or time.monotonic() < self._estimate_retry_at
        ):
            return self._estimate
        self._estimate_retry_at = time.monotonic() + ESTIMATE_RETRY_S
        note: str | None = None
        try:
            self._estimate = self._read_estimate(report)
        except ftplib.error_perm:
            note = "the printer refused to hand over the job's file"
        except ProviderUnavailable as exc:
            note = str(exc)
        except READ_ERRORS as exc:
            note = f"the job's file could not be read ({type(exc).__name__})"
        else:
            if self._estimate is None:
                note = (
                    "no file on the printer matches the job"
                    if _bambu_file_candidates(report)
                    else "the printer's report names no file"
                )
        if note != self._estimate_note:
            self._estimate_note = note
            if note is not None:
                logger.warning("Bambu job estimate unavailable: %s", note)
        return self._estimate

    def _read_job_file(self, report: dict[str, Any]) -> dict[str, Any] | None:
        return read_job_estimate(
            self._host,
            serial=self.serial_number,
            access_code=self._access_code,
            memory=self._memory,
            report=report,
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
                # The next report starts a new baseline for usage.
                self._stream.pop("usage_signature", None)
                self._stream["usage_gap_pending"] = True
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
            merged = merge_report(carry_over(self._report or {}, report), report)
            self._report = merged
            if _bambu_tag_read_capable(merged):
                self._tags_seen = True
            if "gcode_state" in merged:
                _buffer_bambu_usage_report(
                    self._stream, merged, datetime.now(timezone.utc).isoformat()
                )
                # A later failure of this link is a lost printer, not a wrong serial.
                self._failure = NO_ANSWER
                if _has_feed(merged):
                    self._complete.set()
