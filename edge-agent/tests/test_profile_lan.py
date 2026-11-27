"""SDCP printers and the Elegoo Centauri Carbon 2 over Elegoo's MQTT interface.

The fixtures are shared with the OrcaSlicer plugin (see their README files):
two SDCP messages are a published capture of a Centauri Carbon, the rest are
written by hand from Elegoo's and OrcaSlicer's own code. The printers here
are fakes on a socket pair that speak the protocol as those sources describe.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from filamenthub_edge.config import NodeConfig
from filamenthub_edge.errors import ConfigurationError, HttpRequestError, ProviderUnavailable
from filamenthub_edge.node import build_connection
from filamenthub_edge.providers import _canvas
from filamenthub_edge.providers.elegoo_mqtt import ElegooMqttProvider
from filamenthub_edge.providers.sdcp import SdcpProvider, build_printer

FIXTURES = Path(__file__).parent / "fixtures"
BOARD = "1c7319d30105041800009c0000000000"
SERIAL = "CC2A1B2C3D4E5F"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _exactly(sock: socket.socket, length: int) -> bytes:
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise ConnectionError("closed")
        data += chunk
    return data


# --------------------------------------------------------------------------- #
# A fake SDCP printer
# --------------------------------------------------------------------------- #
class FakeSdcpPrinter:
    def __init__(
        self,
        *,
        attributes: dict[str, Any] | None = None,
        status: dict[str, Any] | None = None,
        canvas: dict[str, Any] | None = None,
    ) -> None:
        self.attributes = attributes or fixture("sdcp/attributes.json")
        self.status = status or fixture("sdcp/status_printing.json")
        self.canvas = canvas or fixture("sdcp/canvas_response.json")
        self.requests: list[dict[str, Any]] = []
        self.path = ""
        self.done = threading.Event()

    def connect(self, host: str, port: int, *, device: str, timeout: float):  # noqa: ANN201
        client, server = socket.socketpair()
        client.settimeout(timeout)
        threading.Thread(target=self.serve, args=(server,), daemon=True).start()
        return client, ("192.168.1.139", port)

    def _send(self, sock: socket.socket, message: dict[str, Any]) -> None:
        payload = json.dumps(message).encode("utf-8")
        length = len(payload)
        if length < 126:
            header = bytes([0x81, length])
        elif length < 65536:
            header = bytes([0x81, 126]) + struct.pack("!H", length)
        else:
            header = bytes([0x81, 127]) + struct.pack("!Q", length)
        sock.sendall(header + payload)

    def serve(self, sock: socket.socket) -> None:
        try:
            head = b""
            while b"\r\n\r\n" not in head:
                head += sock.recv(1)
            lines = head.decode("latin-1").split("\r\n")
            self.path = lines[0].split(" ")[1]
            key = next(
                line.split(":", 1)[1].strip()
                for line in lines
                if line.lower().startswith("sec-websocket-key")
            )
            digest = hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
            accept = base64.b64encode(digest).decode()
            sock.sendall(
                (
                    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                    f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"
                ).encode()
            )
            while True:
                first, second = _exactly(sock, 2)
                length = second & 0x7F
                if length == 126:
                    length = struct.unpack("!H", _exactly(sock, 2))[0]
                assert second & 0x80, "a client frame is masked"
                mask = _exactly(sock, 4)
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(_exactly(sock, length)))
                if first & 0x0F == 0x8:
                    return
                request = json.loads(payload)
                self.requests.append(request)
                command = request["Data"]["Cmd"]
                if command == 1:
                    self._send(sock, self.attributes)
                elif command == 0:
                    self._send(sock, self.status)
                elif command == 324:
                    answer = copy.deepcopy(self.canvas)
                    answer["Data"]["RequestID"] = request["Data"]["RequestID"]
                    self._send(sock, answer)
        except (ConnectionError, OSError):
            pass
        finally:
            self.done.set()
            sock.close()

    @property
    def commands(self) -> list[int]:
        return [item["Data"]["Cmd"] for item in self.requests]


def sdcp(printer: FakeSdcpPrinter) -> SdcpProvider:
    return SdcpProvider("192.168.1.139", timeout=3, connect=printer.connect)


class SdcpTest(unittest.TestCase):
    def test_a_canvas_printer_shows_its_state_and_slots(self) -> None:
        printer = FakeSdcpPrinter()
        snapshot = sdcp(printer).observe()

        self.assertEqual(printer.path, "/websocket")
        self.assertEqual(printer.commands, [1, 0, 324])
        # The CANVAS request names the board the attributes reported.
        self.assertEqual(printer.requests[2]["Data"]["MainboardID"], BOARD)
        self.assertEqual(snapshot.device_identity, ("sdcp_mainboard", BOARD))
        self.assertEqual(snapshot.capabilities, ["read", "presence"])
        self.assertIsNone(snapshot.usage)
        self.assertEqual(snapshot.printer["state"], "printing")
        self.assertEqual(snapshot.printer["remaining_seconds"], 4692)
        self.assertTrue(snapshot.slot_topology_complete)
        self.assertEqual(
            [
                (s["provider_index"], s["present"], s.get("material"), s.get("color_hex"),
                 s.get("active_feed"))
                for s in snapshot.slots
            ],
            [
                (0, True, "PLA", "FFFFFF", True),
                (1, True, "PLA", "000000", False),
                # "?" is a spool the printer did not recognise.
                (2, True, None, None, False),
                (3, False, None, None, False),
            ],
        )  # fmt: skip
        self.assertTrue(printer.done.wait(2))

    def test_older_firmware_is_not_asked_about_canvas_and_feeds_its_own_spool(self) -> None:
        attributes = fixture("sdcp/attributes.json")
        attributes["Attributes"]["FirmwareVersion"] = "V1.1.9"
        printer = FakeSdcpPrinter(attributes=attributes)
        snapshot = sdcp(printer).observe()

        self.assertEqual(printer.commands, [1, 0])
        self.assertEqual([s["provider_index"] for s in snapshot.slots], [255])
        self.assertTrue(snapshot.slot_topology_complete)

    def test_a_refused_canvas_request_claims_no_slots(self) -> None:
        canvas = fixture("sdcp/canvas_response.json")
        canvas["Data"]["Data"] = {"Ack": 1}
        snapshot = sdcp(FakeSdcpPrinter(canvas=canvas)).observe()

        self.assertEqual((snapshot.slots, snapshot.slot_topology_complete), ([], False))
        self.assertEqual(snapshot.printer["state"], "printing")

    def test_a_printer_that_does_not_name_its_board_is_not_reported(self) -> None:
        attributes = fixture("sdcp/attributes.json")
        status = fixture("sdcp/status_printing.json")
        attributes["Attributes"].pop("MainboardID")
        attributes.pop("MainboardID", None)
        status.pop("MainboardID", None)
        with self.assertRaisesRegex(ProviderUnavailable, "mainboard ID"):
            sdcp(FakeSdcpPrinter(attributes=attributes, status=status)).observe()

    def test_a_silent_or_missing_printer_is_unavailable(self) -> None:
        def refuse(*_args: Any, **_kwargs: Any) -> Any:
            raise ConnectionRefusedError()

        with self.assertRaisesRegex(ProviderUnavailable, "did not answer"):
            SdcpProvider("192.168.1.139", timeout=1, connect=refuse).observe()

    def test_an_idle_printer_with_the_last_jobs_totals_reads_as_idle(self) -> None:
        printer = build_printer(fixture("sdcp/status_idle.json")["Status"])
        self.assertEqual(printer["state"], "idle")
        self.assertNotIn("job_name", printer)


# --------------------------------------------------------------------------- #
# A fake Centauri Carbon 2
# --------------------------------------------------------------------------- #
class FakeSystemInfo:
    def __init__(self, answer: Any = None, error: Exception | None = None) -> None:
        self.answer = answer if answer is not None else fixture("elegoo_mqtt/system_info.json")
        self.error = error
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request(self, method: str, path: str, **kwargs: Any):  # noqa: ANN201
        self.calls.append((path, kwargs.get("headers") or {}))
        if self.error is not None:
            raise self.error
        return 200, self.answer, {}


def _remaining(length: int) -> bytes:
    out = bytearray()
    while True:
        digit, length = length & 0x7F, length >> 7
        out.append(digit | (0x80 if length else 0))
        if not length:
            return bytes(out)


def _string(data: bytes, offset: int) -> tuple[str, int]:
    size = struct.unpack("!H", data[offset : offset + 2])[0]
    return data[offset + 2 : offset + 2 + size].decode(), offset + 2 + size


class FakeElegooBroker:
    def __init__(
        self,
        *,
        access_code: str = "123456",
        canvas: dict[str, Any] | None = None,
        register: str = "ok",
    ) -> None:
        self.access_code = access_code
        self.canvas = canvas or fixture("elegoo_mqtt/canvas.json")
        self.register = register
        self.logins: list[tuple[str, str, str]] = []
        self.subscriptions: list[str] = []
        self.registered: list[dict[str, Any]] = []
        self.methods: list[int] = []

    def connect(self, host: str, port: int, *, device: str, timeout: float):  # noqa: ANN201
        client, server = socket.socketpair()
        client.settimeout(timeout)
        threading.Thread(target=self.serve, args=(server,), daemon=True).start()
        return client, ("192.168.1.150", port)

    def _publish(self, sock: socket.socket, topic: str, message: dict[str, Any]) -> None:
        body = struct.pack("!H", len(topic)) + topic.encode() + json.dumps(message).encode()
        sock.sendall(b"\x30" + _remaining(len(body)) + body)

    def serve(self, sock: socket.socket) -> None:
        client = ""
        try:
            while True:
                header = _exactly(sock, 1)[0]
                length, multiplier = 0, 1
                while True:
                    digit = _exactly(sock, 1)[0]
                    length += (digit & 0x7F) * multiplier
                    multiplier *= 128
                    if not digit & 0x80:
                        break
                body = _exactly(sock, length) if length else b""
                kind = header >> 4
                if kind == 1:
                    offset = 10
                    client, offset = _string(body, offset)
                    user, offset = _string(body, offset)
                    password, offset = _string(body, offset)
                    self.logins.append((client, user, password))
                    refused = password != self.access_code
                    sock.sendall(bytes([0x20, 2, 0, 5 if refused else 0]))
                    if refused:
                        return
                elif kind == 8:
                    offset = 2
                    while offset < len(body):
                        topic, offset = _string(body, offset)
                        offset += 1
                        self.subscriptions.append(topic)
                    sock.sendall(b"\x90\x04" + body[:2] + b"\x00\x00")
                elif kind == 3:
                    topic, offset = _string(body, 0)
                    message = json.loads(body[offset:])
                    if topic == f"elegoo/{SERIAL}/api_register":
                        self.registered.append(message)
                        self._publish(
                            sock,
                            f"elegoo/{SERIAL}/{message['request_id']}/register_response",
                            {"client_id": message["client_id"], "error": self.register},
                        )
                    elif topic == f"elegoo/{SERIAL}/{client}/api_request":
                        self.methods.append(message["method"])
                        result = {
                            1002: fixture("elegoo_mqtt/status_printing.json"),
                            2005: self.canvas,
                            1061: fixture("elegoo_mqtt/mono_filament.json"),
                        }[message["method"]]
                        self._publish(
                            sock,
                            f"elegoo/{SERIAL}/{client}/api_response",
                            {"id": message["id"], "method": message["method"], "result": result},
                        )
                elif kind == 14:
                    return
        except (ConnectionError, OSError):
            pass
        finally:
            sock.close()


def carbon2(
    broker: FakeElegooBroker, *, access_code: str | None = None, info: FakeSystemInfo | None = None
) -> ElegooMqttProvider:
    return ElegooMqttProvider(
        "192.168.1.150",
        access_code=access_code,
        timeout=3,
        connect=broker.connect,
        http_client=info or FakeSystemInfo(),
    )


class ElegooMqttTest(unittest.TestCase):
    def test_a_carbon_2_with_canvas_shows_its_state_and_slots(self) -> None:
        broker = FakeElegooBroker()
        info = FakeSystemInfo()
        snapshot = carbon2(broker, info=info).observe()

        # Empty access code: the printer's default one, as Elegoo's apps assume.
        self.assertEqual(info.calls, [("/system/info?X-Token=123456", {"X-Token": "123456"})])
        client, user, password = broker.logins[0]
        self.assertTrue(client.startswith("1_PC_"))
        self.assertEqual((user, password), ("elegoo", "123456"))
        self.assertEqual(
            broker.subscriptions,
            [
                f"elegoo/{SERIAL}/{client}_req/register_response",
                f"elegoo/{SERIAL}/{client}/api_response",
            ],
        )
        self.assertEqual(broker.registered, [{"client_id": client, "request_id": f"{client}_req"}])
        self.assertEqual(broker.methods, [1002, 2005])
        self.assertEqual(snapshot.device_identity, ("elegoo_serial", SERIAL))
        self.assertEqual(snapshot.printer["job_name"], "cube_4colors.gcode")
        self.assertEqual(snapshot.printer["total_layers"], 200)
        self.assertTrue(snapshot.slot_topology_complete)
        feeding = [s["provider_index"] for s in snapshot.slots if s.get("active_feed")]
        self.assertEqual(feeding, [1])

    def test_every_reading_registers_the_same_client(self) -> None:
        broker = FakeElegooBroker()
        provider = carbon2(broker)
        provider.observe()
        provider.observe()

        self.assertEqual(len({login[0] for login in broker.logins}), 1)
        self.assertEqual(len(broker.registered), 2)

    def test_without_canvas_the_single_spool_is_asked_for(self) -> None:
        canvas = fixture("elegoo_mqtt/canvas.json")
        for unit in canvas["canvas_info"]["canvas_list"]:
            unit["connected"] = 0
        broker = FakeElegooBroker(canvas=canvas)
        snapshot = carbon2(broker).observe()

        self.assertEqual(broker.methods, [1002, 2005, 1061])
        self.assertEqual(len(snapshot.slots), 1)
        self.assertEqual(
            (snapshot.slots[0]["provider_index"], snapshot.slots[0]["material"]), (255, "PLA")
        )

    def test_a_refusing_printer_says_why(self) -> None:
        cases = [
            (carbon2(FakeElegooBroker(), access_code="000000"), "rejected the access code"),
            (carbon2(FakeElegooBroker(register="too many clients")), "as many clients"),
            (
                carbon2(
                    FakeElegooBroker(),
                    info=FakeSystemInfo({"error_code": 1000}),
                ),
                "rejected the access code",
            ),
            (
                carbon2(
                    FakeElegooBroker(),
                    info=FakeSystemInfo(error=HttpRequestError("x", status_code=401)),
                ),
                "rejected the access code",
            ),
            (
                carbon2(FakeElegooBroker(), info=FakeSystemInfo({"error_code": 0})),
                "serial number",
            ),
        ]
        for provider, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(ProviderUnavailable, reason):
                provider.observe()


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class ProfileLanConfigTest(unittest.TestCase):
    def load(self, entry: dict[str, Any]) -> NodeConfig:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"connections": [entry]}), encoding="utf-8")
            with patch.dict("os.environ", {"FH_EDGE_OPTIONS_FILE": str(path)}, clear=True):
                return NodeConfig.load()

    def test_a_printer_is_named_by_its_address_alone(self) -> None:
        sdcp_config = self.load(
            {"id": "carbon", "adapter": "sdcp", "printer_url": "192.168.1.139"}
        ).connections[0]
        mqtt_config = self.load(
            {
                "id": "carbon2",
                "adapter": "elegoo_mqtt",
                "printer_url": "192.168.1.150",
                "access_code": "654321",
            }
        ).connections[0]

        self.assertEqual(
            (sdcp_config.material_provider, sdcp_config.moonraker_url),
            ("sdcp", "ws://192.168.1.139:3030"),
        )
        self.assertEqual(
            (mqtt_config.material_provider, mqtt_config.moonraker_url),
            ("elegoo_mqtt", "mqtt://192.168.1.150:1883"),
        )
        self.assertNotIn("654321", repr(mqtt_config))
        self.assertIsInstance(
            build_connection(sdcp_config, store=None, state=None).provider,  # type: ignore[arg-type]
            SdcpProvider,
        )
        self.assertIsInstance(
            build_connection(mqtt_config, store=None, state=None).provider,  # type: ignore[arg-type]
            ElegooMqttProvider,
        )

    def test_settings_that_do_not_apply_fail_closed(self) -> None:
        base = {"id": "carbon", "adapter": "sdcp", "printer_url": "192.168.1.139"}
        invalid = [
            {**base, "access_code": "123456"},
            {**base, "serial_number": "ABC12345"},
            {**base, "check_code": "a1b2c3d4"},
            {**base, "material_provider": "happy_hare"},
            {**base, "printer_url": "http://192.168.1.139"},
            {**base, "adapter": "elegoo_mqtt", "serial_number": "ABC12345"},
            {**base, "adapter": "elegoo_mqtt", "moonraker_api_key": "secret"},
        ]
        for entry in invalid:
            with self.subTest(entry=entry), self.assertRaises(ConfigurationError):
                self.load(entry)


class CanvasTest(unittest.TestCase):
    def test_a_unit_numbered_from_one_is_read_as_such(self) -> None:
        info = fixture("elegoo_mqtt/canvas.json")["canvas_info"]
        for tray in info["canvas_list"][0]["tray_list"]:
            tray["tray_id"] += 1
        slots, complete = _canvas.canvas_slots(info)
        self.assertTrue(complete)
        self.assertEqual([s["provider_index"] for s in slots], [0, 1, 2, 3])
        self.assertEqual(slots[1]["material"], "PETG")


if __name__ == "__main__":
    unittest.main()
