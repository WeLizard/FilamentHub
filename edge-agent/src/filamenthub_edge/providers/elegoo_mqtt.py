"""The Elegoo Centauri Carbon 2 over Elegoo's own MQTT interface.

The Centauri Carbon 2 does not speak SDCP. It runs an MQTT broker and answers
a JSON API on topics named after its serial number; Elegoo's own LAN library
keeps it as a separate adapter from SDCP. The OrcaSlicer plugin reads it the
same way in ``orca-plugin/filamenthub_elegoo_mqtt.py``; both are held to the
fixtures in ``edge-agent/tests/fixtures/elegoo_mqtt``.

Sources. Every field read here is named in at least one of them; an item
marked "not confirmed" is not.

[link]  elegooofficial/elegoo-link @ ec2d2269 (Elegoo's own LAN library):
        ``src/lan/adapters/elegoo_fdm_cc2/elegoo_fdm_cc2_protocol.cpp``: one
        client id ``1_PC_<4 digits>`` per printer for the client's life and
        request id ``<client>_req`` (l. 15-17), the broker on TCP 1883 (l. 25),
        the serial number from ``GET /system/info`` with the access code as
        ``X-Token`` header and query, default "123456" (l. 68-101), user
        ``elegoo`` with the access code as password (l. 150-186), the topics
        (l. 198-232) and the register answer with ``client_id`` and ``error``
        "ok" or "too many clients" (l. 248-290);
        ``src/lan/protocols/mqtt_protocol.cpp``: a clean session, and the same
        client id registered again on every connection (l. 160-161, 236-247);
        ``src/lan/adapters/elegoo_fdm_cc2/elegoo_fdm_cc2_message_adapter.cpp``:
        ``machine_status.status`` / ``sub_status`` (l. 639-960),
        ``print_status`` (l. 973-985), ``extruder``, ``heater_bed`` and
        ``ztemperature_sensor`` (l. 1004-1029), the methods 1002 status and
        2005 CANVAS (l. 1391-1423).
[orca]  OrcaSlicer/OrcaSlicer @ 7cdc829a,
        ``resources/web/elegoolink/lan_service_web/index.html`` (Elegoo's
        bundled panel): requests ``{"method", "id"}`` and the method
        ``GetMonoFilamentInfo`` = 1061 answered by ``mono_filament_info``.

Not confirmed on a printer of FilamentHub's own: the whole provider. Not
confirmed by a source: reading power-loss recovery (machine status 15) as a
paused job.

Edge only reads: it registers as a client, asks for methods 1002, 2005 and,
without CANVAS, 1061, and leaves. It keeps one client id for the printer, as
Elegoo's library does, so its readings never take another client's place.
The printer counts no filament, so nothing is charged to a spool.
"""

from __future__ import annotations

import json
import re
import secrets
import struct
import time
import urllib.parse
from collections.abc import Callable
from typing import Any

from ..errors import HttpRequestError, ProviderUnavailable
from ..http import JsonHttpClient
from . import _canvas
from ._lan import (
    MqttLink,
    connect_local,
    mqtt_field,
    mqtt_publish_body,
    mqtt_published,
    resolve_local,
)
from .base import ProviderSnapshot

HTTP_PORT = 80
DEFAULT_PORT = 1883
USERNAME = "elegoo"
DEFAULT_ACCESS_CODE = "123456"
METHOD_STATUS = 1002
METHOD_CANVAS = 2005
METHOD_MONO_FILAMENT = 1061
IDENTITY_KIND = "elegoo_serial"
MAX_PACKET_BYTES = 512 * 1024
REPLY_SECONDS = 4.0
NO_ANSWER = "Elegoo printer did not answer"
ACCESS_REFUSED = "Elegoo printer rejected the access code"
BUSY = "Elegoo printer already serves as many clients as it allows"
NO_IDENTITY = "Elegoo printer did not report its serial number"
INVALID = "Elegoo printer gave an unexpected answer"
_SERIAL = re.compile(r"[A-Za-z0-9_-]{4,64}")
_JOB_STATES = {"printing", "paused", "preparing", "finished", "failed"}
_RUNNING_STATES = {"printing", "paused", "preparing"}
# machine_status.sub_status while the status is 2, printing ([link] l. 653-760).
_PRINT_SUBSTATES = {
    1081: "preparing", 1082: "preparing", 1086: "preparing",
    1045: "preparing", 1096: "preparing", 1405: "preparing", 1906: "preparing",
    2801: "preparing", 2802: "preparing", 2901: "preparing", 2902: "preparing",
    2501: "paused", 2502: "paused", 2505: "paused",
    2503: "failed", 2504: "failed", 2077: "finished",
}  # fmt: skip


def serial_number(value: Any) -> str:
    """A serial number, or ``""``; it is a topic segment, so strictly checked."""
    text = value.strip() if isinstance(value, str) else ""
    return text if _SERIAL.fullmatch(text) and text.strip("0") else ""


def topics(serial: str, client_id: str) -> dict[str, str]:
    base = f"elegoo/{serial}/"
    return {
        "register": base + "api_register",
        "register_response": f"{base}{client_id}_req/register_response",
        "request": f"{base}{client_id}/api_request",
        "response": f"{base}{client_id}/api_response",
    }


def _object(result: Any, key: str) -> dict[str, Any]:
    value = result.get(key) if isinstance(result, dict) else None
    return value if isinstance(value, dict) else {}


def build_printer(result: dict[str, Any]) -> dict[str, Any]:
    """A status answer (method 1002) in the provider-neutral bridge contract."""
    machine = _object(result, "machine_status")
    job_status = _object(result, "print_status")
    code = _canvas.integer(machine.get("status"))
    job = _canvas.job_name(job_status.get("filename"))
    if code == 1:
        state = "idle"
    elif code == 2:
        sub_status = _canvas.integer(machine.get("sub_status"))
        state = "printing" if sub_status is None else _PRINT_SUBSTATES.get(sub_status, "printing")
    elif code == 15:
        # Power-loss recovery: the job waits to be resumed (not confirmed).
        state = "paused"
    elif code == 14:
        # Emergency stop.
        state = "failed"
    else:
        state = "unknown"
    if not job and state in _JOB_STATES:
        state = "unknown"
    printer: dict[str, Any] = {"state": state}
    if job and state in _JOB_STATES:
        printer["job_name"] = job
        progress = _canvas.number(machine.get("progress"))
        if progress is not None and 0 <= progress <= 100:
            printer["progress_percent"] = round(progress)
        remaining = _canvas.number(job_status.get("remaining_time_sec"))
        if state in _RUNNING_STATES and remaining is not None and 0 <= remaining <= 2_592_000:
            printer["remaining_seconds"] = int(remaining)
        layer = _canvas.integer(job_status.get("current_layer"))
        layers = _canvas.integer(job_status.get("total_layer"))
        if layer is not None and 0 <= layer <= 10_000_000:
            printer["current_layer"] = layer
        if layers is not None and 0 < layers <= 10_000_000:
            printer["total_layers"] = layers
    for key, source, field, low, high in (
        ("nozzle_temperature", "extruder", "temperature", -50, 600),
        ("nozzle_target_temperature", "extruder", "target", 0, 600),
        ("bed_temperature", "heater_bed", "temperature", -50, 250),
        ("bed_target_temperature", "heater_bed", "target", 0, 250),
        ("chamber_temperature", "ztemperature_sensor", "temperature", -50, 150),
    ):
        value = _canvas.number(_object(result, source).get(field))
        if value is not None and low <= value <= high:
            printer[key] = round(value, 1)
    return printer


def _json(payload: bytes) -> dict[str, Any] | None:
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return message if isinstance(message, dict) else None


class ElegooMqttProvider:
    def __init__(
        self,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        access_code: str | None,
        timeout: float,
        connect: Callable[..., Any] = connect_local,
        http_client: JsonHttpClient | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._access_code = access_code or DEFAULT_ACCESS_CODE
        self._timeout = timeout
        self._connect = connect
        self._http = http_client
        # One client for the printer's whole life here, as Elegoo's library keeps.
        self._client_id = f"1_PC_{1000 + secrets.randbelow(9000)}"

    def capabilities(self) -> list[str]:
        return ["read", "presence"]

    def _serial(self) -> str:
        """The serial number the printer reports for this access code."""
        client = self._http
        if client is None:
            _family, sockaddr = resolve_local(self._host, HTTP_PORT, device="Elegoo printer")
            address = str(sockaddr[0])
            authority = f"[{address}]" if ":" in address else address
            client = JsonHttpClient(
                f"http://{authority}:{HTTP_PORT}", allow_http=True, timeout=self._timeout
            )
        token = urllib.parse.quote(self._access_code, safe="")
        try:
            _status, answer, _headers = client.request(
                "GET", f"/system/info?X-Token={token}", headers={"X-Token": self._access_code}
            )
        except HttpRequestError as exc:
            if exc.status_code in {401, 403}:
                raise ProviderUnavailable(ACCESS_REFUSED) from exc
            raise ProviderUnavailable(NO_ANSWER) from exc
        if not isinstance(answer, dict):
            raise ProviderUnavailable(INVALID)
        if answer.get("error_code") == 1000:
            raise ProviderUnavailable(ACCESS_REFUSED)
        if answer.get("error_code") != 0:
            raise ProviderUnavailable(INVALID)
        serial = serial_number(_object(answer, "system_info").get("sn"))
        if not serial:
            raise ProviderUnavailable(NO_IDENTITY)
        return serial

    def read(self) -> dict[str, Any]:
        """One reading: ``{"serial", "answers"}`` keyed by method."""
        serial = self._serial()
        names = topics(serial, self._client_id)
        deadline = time.monotonic() + self._timeout
        try:
            sock, _sockaddr = self._connect(
                self._host, self._port, device="Elegoo printer", timeout=self._timeout
            )
        except OSError as exc:
            raise ProviderUnavailable(NO_ANSWER) from exc
        link = MqttLink(sock, name="Elegoo", max_packet_bytes=MAX_PACKET_BYTES)
        answers: dict[int, dict[str, Any]] = {}
        try:
            link.send(
                0x10,
                mqtt_field(b"MQTT")
                + bytes([4, 0xC2])
                + struct.pack("!H", 60)
                + mqtt_field(self._client_id.encode("ascii"))
                + mqtt_field(USERNAME.encode("ascii"))
                + mqtt_field(self._access_code.encode("utf-8")),
            )
            header, connack = link.packet(deadline)
            if header >> 4 != 2 or len(connack) < 2:
                raise ProviderUnavailable(INVALID)
            if connack[1] in {4, 5}:
                raise ProviderUnavailable(ACCESS_REFUSED)
            if connack[1] != 0:
                raise ProviderUnavailable(INVALID)
            link.send(
                0x82,
                struct.pack("!H", 1)
                + b"".join(
                    mqtt_field(names[name].encode("utf-8")) + b"\x00"
                    for name in ("register_response", "response")
                ),
            )
            while link.packet(deadline)[0] >> 4 != 9:
                pass
            register = {"client_id": self._client_id, "request_id": f"{self._client_id}_req"}
            self._publish(link, names["register"], register)
            self._exchange(link, names, answers, deadline)
            try:
                sock.sendall(b"\xe0\x00")
            except OSError:
                pass
        except (OSError, ValueError) as exc:
            if METHOD_STATUS not in answers:
                raise ProviderUnavailable(NO_ANSWER) from exc
        finally:
            try:
                sock.close()
            except OSError:
                pass
        if METHOD_STATUS not in answers:
            raise ProviderUnavailable(NO_ANSWER)
        return {"serial": serial, "answers": answers}

    @staticmethod
    def _publish(link: MqttLink, topic: str, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        link.send(0x30, mqtt_publish_body(topic, payload))

    def _exchange(
        self,
        link: MqttLink,
        names: dict[str, str],
        answers: dict[int, dict[str, Any]],
        deadline: float,
    ) -> None:
        """Register, then ask for status, CANVAS and, without CANVAS, the single spool."""
        asked: tuple[int, int] | None = None
        reply_deadline = min(deadline, time.monotonic() + REPLY_SECONDS)
        while True:
            try:
                header, body = link.packet(reply_deadline)
            except TimeoutError:
                # What the printer answered in time is still a reading.
                return
            received = mqtt_published(header, body)
            if received is None:
                continue
            topic, payload, packet_id = received
            if packet_id is not None:
                link.send(0x40, packet_id)
            message = _json(payload)
            if message is None:
                continue
            if topic == names["register_response"] and asked is None:
                if message.get("client_id") != self._client_id:
                    continue
                error = message.get("error")
                if error != "ok":
                    if isinstance(error, str) and "too many clients" in error:
                        raise ProviderUnavailable(BUSY)
                    raise ProviderUnavailable(INVALID)
                asked = (1, METHOD_STATUS)
            elif topic == names["response"] and asked is not None:
                result = message.get("result")
                if message.get("id") != asked[0] or not isinstance(result, dict):
                    continue
                if result.get("error_code", 0) == 0:
                    answers[asked[1]] = result
                if asked[1] == METHOD_STATUS:
                    asked = (2, METHOD_CANVAS)
                elif asked[1] == METHOD_CANVAS and not _canvas.connected_units(
                    answers.get(METHOD_CANVAS, {}).get("canvas_info")
                ):
                    # Without CANVAS the printer names its single spool.
                    asked = (3, METHOD_MONO_FILAMENT)
                else:
                    return
            else:
                continue
            reply_deadline = min(deadline, time.monotonic() + REPLY_SECONDS)
            self._publish(link, names["request"], {"method": asked[1], "id": asked[0]})

    def observe(self) -> ProviderSnapshot:
        reading = self.read()
        answers = reading["answers"]
        canvas = answers.get(METHOD_CANVAS, {}).get("canvas_info")
        mono = answers.get(METHOD_MONO_FILAMENT, {}).get("mono_filament_info")
        slots, complete = _canvas.feed(
            canvas if isinstance(canvas, dict) else None,
            mono if isinstance(mono, dict) else None,
            canvas_answered=isinstance(canvas, dict),
        )
        return ProviderSnapshot(
            printer=build_printer(answers[METHOD_STATUS]),
            slots=slots,
            slot_topology_complete=complete,
            capabilities=self.capabilities(),
            # The serial number comes from the printer itself, for this access code.
            device_identity=(IDENTITY_KIND, reading["serial"]),
        )
