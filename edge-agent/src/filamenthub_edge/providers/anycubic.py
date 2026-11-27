"""Anycubic Kobra 3 / S1 / X observations over the printer's LAN mode.

The protocol itself (the ``/info`` answer, the signed ``/ctrl`` request, the
sealed MQTT login, topics, reports, printer state and ACE slots) is read by
``_anycubic.py``, a copy of the OrcaSlicer plugin's module, so Edge and the
plugin understand a printer the same way. This file only does the I/O:

1. ``GET http://<printer>:18910/info`` says whether LAN mode is on and gives
   the token for the next request;
2. a signed ``POST /ctrl`` on the same host returns the login of the
   printer's own MQTT broker;
3. the provider connects to that broker over TLS on the port it named, asks
   once for ``info``, ``multiColorBox`` and ``extfilbox``, gathers the answers
   for a few seconds and disconnects.

Every request goes to the one address resolved inside the local network; the
broker host the printer names is ignored. The broker's certificate is the
printer's own and nothing can vouch for it, so it is not verified. Nothing is
ever sent to the printer except these read requests, and no filament usage is
counted: the meaning of the job's ``supplies_usage`` figure is not confirmed.

Nothing here has run against a real printer yet; see the plugin module for
the sources and for what they leave open.
"""

from __future__ import annotations

import secrets
import socket
import ssl
import struct
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from ..errors import HttpRequestError, ProviderUnavailable
from ..http import JsonHttpClient
from ._anycubic import (
    ANYCUBIC_CAPABILITIES,
    ANYCUBIC_IDENTITY_KIND,
    ANYCUBIC_INFO_PORT,
    ANYCUBIC_MAX_MESSAGE_BYTES,
    ANYCUBIC_QUERIES,
    anycubic_ctrl_url,
    anycubic_info,
    anycubic_info_url,
    anycubic_merge_boxes,
    anycubic_printer,
    anycubic_query,
    anycubic_report,
    anycubic_report_filter,
    anycubic_session,
    anycubic_slots,
)
from .bambu_tls import resolve_printer
from .base import ProviderSnapshot
from .mqtt import MqttLink, field, published

LABEL = "Anycubic printer"
KEEPALIVE_S = 30
# How long the broker is given to answer the requests, and how much longer to
# wait for the ACE units once the state has arrived.
REPLY_SECONDS = 4.0
AFTER_INFO_SECONDS = 1.5
# Why a read failed, in words a person can act on. The keys are the codes the
# shared module returns.
FAILURES = {
    "lan_mode": "Anycubic LAN mode is off; turn it on in the printer's network settings",
    "unsupported": "The device at this address does not offer Anycubic LAN mode",
    "refused": "The Anycubic printer refused the LAN connection",
    "invalid": "The Anycubic printer gave an unexpected answer",
    "unreachable": "Anycubic printer did not answer",
}


def _failure(code: str | None) -> ProviderUnavailable:
    return ProviderUnavailable(FAILURES.get(code or "", FAILURES["invalid"]))


def _tls_context() -> ssl.SSLContext:
    # The printer presents a certificate of its own that nothing can vouch
    # for, and its login came over plain HTTP in the same network.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _split(url: str) -> tuple[str, str]:
    """An absolute URL from the shared module as ``(origin, path?query)``."""
    parts = urlsplit(url)
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    return f"{parts.scheme}://{parts.netloc}", target


def _mqtt_reading(
    sock: Any,
    info: dict[str, Any],
    session: dict[str, Any],
    *,
    deadline: float,
    reply_seconds: float,
) -> dict[str, Any]:
    """Log in, ask for the reports and gather them from one open socket."""
    link = MqttLink(sock, label="Anycubic MQTT", max_packet=ANYCUBIC_MAX_MESSAGE_BYTES + 4096)
    connect = (
        field(b"MQTT")
        + bytes([4, 0xC2])
        + struct.pack("!H", KEEPALIVE_S)
        + field(("fhedge-" + secrets.token_hex(6)).encode("ascii"))
        + field(session["username"].encode("utf-8"))
        + field(session["password"].encode("utf-8"))
    )
    link.send(0x10, connect)
    header, answer = link.packet(deadline)
    if (header & 0xF0) != 0x20 or len(answer) < 2 or answer[1] != 0:
        raise _failure("refused")
    model_id, device_id = info["model_id"], session["device_id"]
    topic_filter = anycubic_report_filter(model_id, device_id).encode("utf-8")
    link.send(0x82, struct.pack("!H", 1) + field(topic_filter) + b"\x00")
    header, answer = link.packet(deadline)
    if (header & 0xF0) != 0x90 or len(answer) < 3 or answer[2] == 0x80:
        raise _failure("invalid")
    for report_type, action in ANYCUBIC_QUERIES:
        topic, text = anycubic_query(
            model_id, device_id, report_type, action, uuid.uuid4().hex, int(time.time() * 1000)
        )
        link.send(0x30, field(topic.encode("utf-8")) + text.encode("utf-8"))
    reading: dict[str, Any] = {"info": None, "boxes": None, "holder": None}
    wait_until = min(deadline, time.monotonic() + reply_seconds)
    while time.monotonic() < wait_until:
        try:
            header, body = link.packet(wait_until)
        except TimeoutError:
            break
        message = published(header, body) if (header & 0xF0) == 0x30 else None
        if message is None:
            continue
        report = anycubic_report(
            message[0].decode("utf-8", "replace"), message[1], model_id, device_id
        )
        if report is None:
            continue
        report_type, data = report
        if report_type == "info":
            if reading["info"] is None:
                wait_until = min(wait_until, time.monotonic() + AFTER_INFO_SECONDS)
            reading["info"] = data
        elif report_type == "multiColorBox":
            reading["boxes"] = anycubic_merge_boxes(reading["boxes"], data)
        elif report_type == "extfilbox":
            reading["holder"] = data
        if reading["info"] is not None and reading["boxes"] is not None:
            break
    try:
        sock.sendall(b"\xe0\x00")
    except OSError:
        pass
    if reading["info"] is None:
        raise ProviderUnavailable("The Anycubic printer sent no state report")
    return reading


def _open_broker(
    family: socket.AddressFamily, sockaddr: tuple[Any, ...], timeout: float
) -> ssl.SSLSocket:
    raw = socket.socket(family, socket.SOCK_STREAM)
    raw.settimeout(timeout)
    try:
        raw.connect(sockaddr)
        return _tls_context().wrap_socket(raw, server_hostname=None)
    except BaseException:
        raw.close()
        raise


class AnycubicProvider:
    def __init__(
        self,
        printer_url: str,
        *,
        timeout: float,
        reply_seconds: float = REPLY_SECONDS,
        http: Callable[[str, str], Any] | None = None,
        connect: Callable[[socket.AddressFamily, tuple[Any, ...]], Any] | None = None,
    ) -> None:
        host = urlsplit(printer_url).hostname
        if not host:
            raise ValueError("invalid Anycubic printer address")
        self.host = host
        self._timeout = timeout
        self._reply_seconds = reply_seconds
        self._http = http or self._request
        self._connect = connect or (
            lambda family, sockaddr: _open_broker(family, sockaddr, timeout)
        )

    def capabilities(self) -> list[str]:
        return list(ANYCUBIC_CAPABILITIES)

    def _request(self, url: str, method: str) -> Any:
        origin, target = _split(url)
        client = JsonHttpClient(origin, allow_http=True, timeout=self._timeout)
        try:
            _, decoded, _ = client.request(method, target)
        except HttpRequestError as exc:
            raise _failure("invalid" if exc.status_code else "unreachable") from exc
        return decoded

    def _read(self) -> dict[str, Any]:
        family, sockaddr = resolve_printer(self.host, ANYCUBIC_INFO_PORT, label=LABEL)
        address = str(sockaddr[0]).split("%")[0]
        info, failure = anycubic_info(self._http(anycubic_info_url(address), "GET"))
        if failure or info is None:
            raise _failure(failure)
        body = self._http(
            anycubic_ctrl_url(
                address,
                info,
                int(time.time() * 1000),
                secrets.token_hex(3),
                secrets.token_hex(16).upper(),
            ),
            "POST",
        )
        session, failure = anycubic_session(body, info)
        if failure or session is None:
            raise _failure(failure)
        deadline = time.monotonic() + self._timeout
        # The broker is the printer itself, whatever host its answer names.
        _, broker = resolve_printer(address, session["port"], label=LABEL)
        try:
            sock = self._connect(family, broker)
        except (OSError, ValueError) as exc:
            raise _failure("unreachable") from exc
        try:
            reading = _mqtt_reading(
                sock, info, session, deadline=deadline, reply_seconds=self._reply_seconds
            )
        except (OSError, ValueError) as exc:
            raise _failure("unreachable") from exc
        finally:
            try:
                sock.close()
            except OSError:
                pass
        reading["serial"] = info["serial"]
        return reading

    def observe(self) -> ProviderSnapshot:
        reading = self._read()
        slots, complete = anycubic_slots(reading["boxes"], reading["holder"])
        return ProviderSnapshot(
            printer=anycubic_printer(reading["info"]),
            slots=slots,
            slot_topology_complete=complete,
            capabilities=self.capabilities(),
            # The printer reported this serial number itself.
            device_identity=(ANYCUBIC_IDENTITY_KIND, reading["serial"]),
        )
