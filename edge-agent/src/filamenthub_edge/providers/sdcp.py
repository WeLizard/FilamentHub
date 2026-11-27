"""Printers on the open SDCP protocol, read over the local network.

SDCP (Smart Device Control Protocol) is Chitu Systems' open LAN protocol.
This provider knows the protocol, not a brand: any FDM printer that speaks it
is read the same way. The known devices are Elegoo's Centauri and Centauri
Carbon; the Centauri Carbon 2 speaks Elegoo's MQTT interface instead
(``elegoo_mqtt.py``). The OrcaSlicer plugin reads SDCP the same way in
``orca-plugin/filamenthub_sdcp.py``; both are held to the fixtures in
``edge-agent/tests/fixtures/sdcp``.

Sources. Every field read here is named in at least one of them; an item
marked "not confirmed" is not.

[spec]  cbd-tech/SDCP-Smart-Device-Control-Protocol-V3.0.0 @ f9772157,
        "SDCP(Smart Device Control Protocol)_V3.0.0_EN.md": the WebSocket at
        ``ws://<printer>:3030/websocket`` (l. 13, 34), the topics
        ``sdcp/{request,response,status,attributes}/<MainboardID>`` (l. 41-47),
        the status object (l. 136-158), command 0 status and 1 attributes
        (l. 302, 341), ``Ack`` 0 for success (l. 252).
[link]  elegooofficial/elegoo-link @ ec2d2269 (Elegoo's own LAN library),
        ``src/lan/adapters/elegoo_fdm_cc/elegoo_fdm_cc_message_adapter.cpp``:
        machine and print status codes of FDM firmware (l. 19-61), the request
        envelope (l. 85-106), a file transfer giving way to the second machine
        status (l. 564-600), ``PrintInfo`` fields (l. 742-752), temperatures
        (l. 821-828), ``MainboardID`` and ``FirmwareVersion`` with multi-colour
        support from firmware 1.2 (l. 835-898), the CANVAS answer (l. 902-947),
        the commands 0, 1 and 324 (l. 975-1001) and a reply in ``Data.Data``
        with ``Ack`` (l. 353-410).
[orca]  OrcaSlicer/OrcaSlicer @ 7cdc829a, ``src/slic3r/Utils/ElegooLink.cpp``:
        the request envelope with ``From`` 1 (l. 1121-1137).
[ha]    danielcherubini/elegoo-homeassistant @ ce9c1559,
        ``custom_components/elegoo_printer/sdcp/models/status.py`` l. 185-194:
        FDM firmware counts ``CurrentTicks`` / ``TotalTicks`` in seconds.
[tiger] TigerTag-Project/TigerTag-Studio-Manager issue #41 (2026-10-08): a
        status and attributes capture of a Centauri Carbon on V1.4.49.

Not confirmed on a printer of FilamentHub's own: the whole provider. Not
confirmed by any source: the meaning of print status codes 23-26, read here
as a running job.

Edge sends the printer only read commands: 1 (attributes), 0 (status) and, on
firmware with multi-colour support, 324 (CANVAS). A command the firmware does
not know may stop its daemon, so nothing else is sent. The printer counts no
filament, so nothing is charged to a spool.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from collections.abc import Callable
from typing import Any

from ..errors import ProviderUnavailable
from . import _canvas
from ._lan import WebSocketLink, connect_local
from .base import ProviderSnapshot

DEFAULT_PORT = 3030
PATH = "/websocket"
CMD_STATUS = 0
CMD_ATTRIBUTES = 1
CMD_CANVAS = 324
IDENTITY_KIND = "sdcp_mainboard"
MAX_MESSAGE_BYTES = 256 * 1024
# How long the printer may take for one answer once the link is open.
REPLY_SECONDS = 4.0
NO_ANSWER = "SDCP printer did not answer"
NO_STATUS = "SDCP printer answered without its status"
NO_IDENTITY = "SDCP printer did not report its mainboard ID"
_MAINBOARD_ID = re.compile(r"[0-9a-f]{8,64}")
_FIRMWARE = re.compile(r"[vV]?(\d+)\.(\d+)")
_JOB_STATES = {"printing", "paused", "preparing", "finished", "failed"}
_RUNNING_STATES = {"printing", "paused", "preparing"}
# Machine status ([link] l. 19-30): 0 idle, 1 printing, 2 file transfer.
_MACHINE_IDLE = 0
_MACHINE_PRINTING = 1
_MACHINE_FILE_TRANSFER = 2
# PrintInfo.Status of FDM firmware while the machine prints ([link] l. 35-61).
_PRINT_STATES = {
    0: "printing", 1: "preparing", 5: "paused", 6: "paused", 7: "failed", 8: "failed",
    9: "finished", 10: "preparing", 11: "preparing", 12: "printing", 13: "printing",
    14: "failed", 15: "preparing", 16: "preparing", 17: "preparing", 18: "printing",
    19: "preparing", 20: "preparing", 21: "printing", 22: "printing",
}  # fmt: skip


def mainboard_id(value: Any) -> str:
    """A printer's ``MainboardID`` in lower case, or ``""``."""
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if _MAINBOARD_ID.fullmatch(text) and text.strip("0") else ""


def request(command: int, request_id: str, timestamp_ms: int, board: str = "") -> bytes:
    """One request in OrcaSlicer's envelope ([orca]); Elegoo's library names the board."""
    return json.dumps(
        {
            "Id": "",
            "Data": {
                "Cmd": command,
                "Data": {},
                "RequestID": request_id,
                "MainboardID": board,
                "TimeStamp": timestamp_ms,
                "From": 1,
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


def topic_kind(message: dict[str, Any]) -> str:
    """``"status"``, ``"attributes"``, ``"response"`` or ``""``."""
    topic = message.get("Topic")
    if not isinstance(topic, str) or not topic.startswith("sdcp/") or topic.count("/") < 2:
        return ""
    kind = topic.split("/", 2)[1]
    return kind if kind in {"status", "attributes", "response"} else ""


def canvas_supported(attributes: dict[str, Any] | None) -> bool:
    """Whether the firmware answers command 324: version 1.2 or later ([link] l. 877-895)."""
    version = attributes.get("FirmwareVersion") if isinstance(attributes, dict) else None
    match = _FIRMWARE.match(version.strip()) if isinstance(version, str) else None
    if not match:
        return False
    major, minor = int(match.group(1)), int(match.group(2))
    return major > 1 or (major == 1 and minor > 1)


def _machine_status(status: dict[str, Any]) -> int | None:
    """The machine status that matters: a file transfer gives way to the next one."""
    codes = status.get("CurrentStatus")
    if not isinstance(codes, list):
        return None
    known = [code for code in map(_canvas.integer, codes) if code is not None]
    if not known:
        return _MACHINE_IDLE
    if known[0] == _MACHINE_FILE_TRANSFER and len(known) > 1:
        return known[1]
    return known[0]


def build_printer(status: dict[str, Any]) -> dict[str, Any]:
    """An SDCP status in the provider-neutral bridge contract."""
    machine = _machine_status(status)
    found = status.get("PrintInfo")
    info: dict[str, Any] = found if isinstance(found, dict) else {}
    job = _canvas.job_name(info.get("Filename"))
    if machine is None:
        state = "unknown"
    elif machine == _MACHINE_IDLE:
        state = "idle"
    elif machine == _MACHINE_PRINTING:
        code = _canvas.integer(info.get("Status"))
        # A code no source names, during a print, is still a running job.
        state = _PRINT_STATES.get(code, "printing") if code is not None else "printing"
    else:
        # Calibrating, homing or handling filament: part of a job only if one is named.
        state = "preparing" if job else "unknown"
    if not job and state in _JOB_STATES:
        # An idle printer keeps the last job's totals without its file name.
        state = "unknown"
    printer: dict[str, Any] = {"state": state}
    if job and state in _JOB_STATES:
        printer["job_name"] = job
        progress = _canvas.number(info.get("Progress"))
        if progress is not None and 0 <= progress <= 100:
            printer["progress_percent"] = round(progress)
        total = _canvas.number(info.get("TotalTicks"))
        ticks = _canvas.number(info.get("CurrentTicks"))
        if state in _RUNNING_STATES and total is not None and ticks is not None and total > 0:
            # FDM firmware counts seconds ([ha]).
            remaining = max(0.0, total - ticks)
            if remaining <= 2_592_000:
                printer["remaining_seconds"] = int(remaining)
        layer = _canvas.integer(info.get("CurrentLayer"))
        layers = _canvas.integer(info.get("TotalLayer"))
        if layer is not None and 0 <= layer <= 10_000_000:
            printer["current_layer"] = layer
        if layers is not None and 0 < layers <= 10_000_000:
            printer["total_layers"] = layers
    for key, field, low, high in (
        ("nozzle_temperature", "TempOfNozzle", -50, 600),
        ("nozzle_target_temperature", "TempTargetNozzle", 0, 600),
        ("bed_temperature", "TempOfHotbed", -50, 250),
        ("bed_target_temperature", "TempTargetHotbed", 0, 250),
        ("chamber_temperature", "TempOfBox", -50, 150),
    ):
        value = _canvas.number(status.get(field))
        if value is not None and low <= value <= high:
            printer[key] = round(value, 1)
    return printer


class SdcpProvider:
    def __init__(
        self,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        timeout: float,
        connect: Callable[..., Any] = connect_local,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._connect = connect

    def capabilities(self) -> list[str]:
        return ["read", "presence"]

    def read(self) -> dict[str, Any]:
        """One reading: the board ID, status, attributes and CANVAS answer, if asked."""
        deadline = time.monotonic() + self._timeout
        try:
            sock, sockaddr = self._connect(
                self._host, self._port, device="SDCP printer", timeout=self._timeout
            )
        except OSError as exc:
            raise ProviderUnavailable(NO_ANSWER) from exc
        link = WebSocketLink(sock, name="SDCP printer", max_message_bytes=MAX_MESSAGE_BYTES)
        reading: dict[str, Any] = {
            "board": "",
            "status": None,
            "attributes": None,
            "canvas": None,
            "canvas_asked": False,
            "canvas_done": False,
        }
        canvas_request = ""
        try:
            link.open(str(sockaddr[0]), self._port, PATH, deadline)
            stamp = int(time.time() * 1000)
            for command in (CMD_ATTRIBUTES, CMD_STATUS):
                link.send(request(command, secrets.token_hex(16), stamp))
            reply_deadline = min(deadline, time.monotonic() + REPLY_SECONDS)
            while not self._finished(reading, canvas_request):
                try:
                    payload = link.message(reply_deadline)
                except TimeoutError:
                    break
                if payload is None:
                    break
                self._take(reading, payload, canvas_request)
                if (
                    not canvas_request
                    and reading["board"]
                    and canvas_supported(reading["attributes"])
                ):
                    canvas_request = secrets.token_hex(16)
                    reading["canvas_asked"] = True
                    stamp = int(time.time() * 1000)
                    link.send(request(CMD_CANVAS, canvas_request, stamp, reading["board"]))
                    reply_deadline = min(deadline, time.monotonic() + REPLY_SECONDS)
            link.close()
        except (OSError, ValueError) as exc:
            if reading["status"] is None:
                raise ProviderUnavailable(NO_ANSWER) from exc
        finally:
            try:
                sock.close()
            except OSError:
                pass
        if reading["status"] is None:
            raise ProviderUnavailable(NO_STATUS)
        if not reading["board"]:
            raise ProviderUnavailable(NO_IDENTITY)
        return reading

    @staticmethod
    def _finished(reading: dict[str, Any], canvas_request: str) -> bool:
        if reading["status"] is None or reading["attributes"] is None:
            return False
        if canvas_request:
            return bool(reading["canvas_done"])
        return not canvas_supported(reading["attributes"])

    @staticmethod
    def _take(reading: dict[str, Any], payload: bytes, canvas_request: str) -> None:
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return
        if not isinstance(message, dict):
            return
        kind = topic_kind(message)
        if kind == "status" and isinstance(message.get("Status"), dict):
            reading["status"] = message["Status"]
            reading["board"] = reading["board"] or mainboard_id(message.get("MainboardID"))
        elif kind == "attributes" and isinstance(message.get("Attributes"), dict):
            reading["attributes"] = message["Attributes"]
            reading["board"] = mainboard_id(message["Attributes"].get("MainboardID")) or (
                reading["board"]
            )
        elif kind == "response" and canvas_request:
            data = message.get("Data")
            if isinstance(data, dict) and data.get("RequestID") == canvas_request:
                answer = data.get("Data")
                # A refused request (Ack other than 0) ends the wait without slots.
                reading["canvas_done"] = True
                if isinstance(answer, dict) and answer.get("Ack") == 0:
                    reading["canvas"] = answer

    def observe(self) -> ProviderSnapshot:
        reading = self.read()
        slots, complete = _canvas.feed(
            reading["canvas"],
            None,
            # Older firmware has no CANVAS to ask about: the printer feeds its own spool.
            canvas_answered=reading["canvas"] is not None or not reading["canvas_asked"],
        )
        return ProviderSnapshot(
            printer=build_printer(reading["status"]),
            slots=slots,
            slot_topology_complete=complete,
            capabilities=self.capabilities(),
            # The board ID comes from the printer itself, not from a setting.
            device_identity=(IDENTITY_KIND, reading["board"]),
        )
