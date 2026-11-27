"""Anycubic Kobra 3 / S1 / X reader over the printer's LAN mode.

The fixtures are the ones the OrcaSlicer plugin is tested with: hand-made to
the fields of open LAN clients, not captured from a printer. The printer's
HTTP handshake is a dictionary of answers and its broker an in-memory socket,
so the sealed login in ``ctrl_answer.json`` is opened for real.
"""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit

from filamenthub_edge.config import NodeConfig
from filamenthub_edge.errors import ConfigurationError, ProviderUnavailable
from filamenthub_edge.node import build_connection
from filamenthub_edge.providers.anycubic import AnycubicProvider

FIXTURES = Path(__file__).parent / "fixtures" / "anycubic"
HOST = "192.168.1.60"
MODEL_ID = "20025"
DEVICE_ID = "d0e1f2a3b4c5d6e7f8091a2b3c4d5e6f"
SERIAL = "KS1SN0000000001"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _length(value: int) -> bytes:
    out = bytearray()
    while True:
        digit, value = value & 0x7F, value >> 7
        out.append(digit | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _packet(kind: int, body: bytes) -> bytes:
    return bytes([kind]) + _length(len(body)) + body


def _string(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack("!H", len(data)) + data


def _split(data: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    packets = []
    while len(data) >= 2:
        length = shift = 0
        offset = 1
        while True:
            if offset >= len(data):
                return packets, data
            digit = data[offset]
            length |= (digit & 0x7F) << shift
            shift += 7
            offset += 1
            if not digit & 0x80:
                break
        if len(data) < offset + length:
            break
        packets.append((data[0], data[offset : offset + length]))
        data = data[offset + length :]
    return packets, data


class Printer:
    """The printer's HTTP handshake and its MQTT broker."""

    def __init__(self, info: Any = None, answers: dict[str, list[Any]] | None = None) -> None:
        self.info = info if info is not None else fixture("info_lan_s1.json")
        self.ctrl = fixture("ctrl_answer.json")
        self.answers = answers if answers is not None else {
            "info": [fixture("info_printing_s1.json")],
            "multiColorBox": [fixture("multicolorbox_ace_pro.json")],
        }
        self.requests: list[tuple[str, str]] = []
        self.broker_address: tuple[Any, ...] | None = None
        self.incoming = b""
        self.outgoing = b""
        self.login: tuple[str, str] | None = None
        self.subscribed: str | None = None
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.disconnected = False
        self.closed = False
        self.refuse = False

    # HTTP
    def http(self, url: str, method: str) -> Any:
        parts = urlsplit(url)
        self.requests.append((method, f"{parts.hostname}:{parts.port}{parts.path}"))
        return self.info if parts.path == "/info" else self.ctrl

    # The broker's socket
    def connect(self, _family: Any, sockaddr: tuple[Any, ...]) -> Printer:
        self.broker_address = sockaddr
        return self

    def settimeout(self, _seconds: float) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def sendall(self, data: bytes) -> None:
        self.incoming += data
        packets, self.incoming = _split(self.incoming)
        for header, body in packets:
            kind = header & 0xF0
            if kind == 0x10:
                offset, fields = 2 + 4 + 1 + 1 + 2, []
                while offset < len(body):
                    size = struct.unpack("!H", body[offset : offset + 2])[0]
                    fields.append(body[offset + 2 : offset + 2 + size].decode("utf-8"))
                    offset += 2 + size
                self.login = (fields[1], fields[2])
                self.outgoing += _packet(0x20, b"\x00\x05" if self.refuse else b"\x00\x00")
            elif kind == 0x80:
                size = struct.unpack("!H", body[2:4])[0]
                self.subscribed = body[4 : 4 + size].decode("utf-8")
                self.outgoing += _packet(0x90, body[:2] + b"\x00")
            elif kind == 0x30:
                size = struct.unpack("!H", body[:2])[0]
                topic = body[2 : 2 + size].decode("utf-8")
                message = json.loads(body[2 + size :])
                self.published.append((topic, message))
                for answer in self.answers.get(message["type"], []):
                    report = "anycubic/anycubicCloud/v1/printer/public/%s/%s/%s/report" % (
                        MODEL_ID, DEVICE_ID, message["type"],
                    )
                    self.outgoing += _packet(
                        0x30, _string(report) + json.dumps(answer).encode("utf-8")
                    )
            elif kind == 0xE0:
                self.disconnected = True

    def recv(self, size: int) -> bytes:
        if not self.outgoing:
            raise TimeoutError("nothing more from the broker")
        chunk, self.outgoing = self.outgoing[:size], self.outgoing[size:]
        return chunk


def provider(printer: Printer) -> AnycubicProvider:
    return AnycubicProvider(
        f"http://{HOST}:18910",
        timeout=2,
        reply_seconds=0.3,
        http=printer.http,
        connect=printer.connect,
    )


class AnycubicReadingTest(unittest.TestCase):
    def test_a_printing_kobra_s1_reports_its_job_and_ace_slots(self) -> None:
        printer = Printer()

        snapshot = provider(printer).observe()

        self.assertEqual(snapshot.printer["state"], "printing")
        self.assertEqual(snapshot.printer["progress_percent"], 37)
        self.assertEqual(snapshot.printer["remaining_seconds"], 52 * 60)
        self.assertEqual([slot["provider_index"] for slot in snapshot.slots], [0, 1, 2, 3])
        feeding = [slot for slot in snapshot.slots if slot["active_feed"]]
        self.assertEqual([(s["provider_index"], s["material"]) for s in feeding], [(2, "PETG")])
        self.assertTrue(snapshot.slot_topology_complete)
        self.assertEqual(snapshot.capabilities, ["read", "presence"])
        self.assertIsNone(snapshot.usage)
        self.assertEqual(snapshot.device_identity, ("anycubic_serial", SERIAL))

    def test_the_login_is_opened_and_only_read_requests_are_sent(self) -> None:
        printer = Printer()

        provider(printer).observe()

        self.assertEqual([method for method, _ in printer.requests], ["GET", "POST"])
        # Both requests and the broker go to the configured printer, not to the
        # host its own answers name.
        self.assertEqual(
            [target.rsplit(":", 1)[0] for _, target in printer.requests], [HOST, HOST]
        )
        self.assertEqual(printer.broker_address, (HOST, 9883))
        session = fixture("ctrl_session.json")
        self.assertEqual(printer.login, (session["username"], session["password"]))
        self.assertEqual(
            printer.subscribed,
            f"anycubic/anycubicCloud/v1/printer/public/{MODEL_ID}/{DEVICE_ID}/#",
        )
        self.assertEqual(
            [(topic.rsplit("/", 1)[-1], message["action"], message["data"])
             for topic, message in printer.published],
            [("info", "query", None), ("multiColorBox", "getInfo", None),
             ("extfilbox", "reportInfo", None)],
        )
        self.assertTrue(printer.disconnected and printer.closed)

    def test_lan_mode_off_is_explained_and_no_login_is_asked(self) -> None:
        printer = Printer(info=fixture("info_cloud_s1.json"))

        with self.assertRaisesRegex(ProviderUnavailable, "LAN mode is off"):
            provider(printer).observe()
        self.assertEqual([method for method, _ in printer.requests], ["GET"])

    def test_a_refused_broker_login_is_reported(self) -> None:
        printer = Printer()
        printer.refuse = True

        with self.assertRaisesRegex(ProviderUnavailable, "refused"):
            provider(printer).observe()

    def test_a_printer_that_sends_no_state_is_not_reported(self) -> None:
        printer = Printer(answers={"multiColorBox": [fixture("multicolorbox_ace_pro.json")]})

        with self.assertRaisesRegex(ProviderUnavailable, "no state"):
            provider(printer).observe()

    def test_a_partial_ace_report_does_not_claim_the_whole_topology(self) -> None:
        printer = Printer(answers={
            "info": [fixture("info_idle_kobra3.json")],
            "multiColorBox": [fixture("multicolorbox_partial.json")],
        })

        snapshot = provider(printer).observe()

        self.assertEqual(snapshot.printer["state"], "finished")
        self.assertFalse(snapshot.slot_topology_complete)

    def test_a_public_address_is_refused_before_anything_is_sent(self) -> None:
        printer = Printer()

        with self.assertRaisesRegex(ProviderUnavailable, "inside the local network"):
            AnycubicProvider(
                "http://8.8.8.8", timeout=2, http=printer.http, connect=printer.connect
            ).observe()
        self.assertEqual(printer.requests, [])


class AnycubicConfigTest(unittest.TestCase):
    def _config(self, **entry: Any) -> NodeConfig:
        base = {"id": "kobra", "adapter": "anycubic", "printer_url": HOST, "pairing_code": "x"}
        with tempfile.TemporaryDirectory() as directory:
            options = Path(directory) / "options.json"
            options.write_text(json.dumps({"connections": [{**base, **entry}]}), encoding="utf-8")
            with patch.dict("os.environ", {"FH_EDGE_OPTIONS_FILE": str(options)}, clear=True):
                return NodeConfig.load()

    def test_the_address_alone_sets_up_a_connection(self) -> None:
        for address in (HOST, f"http://{HOST}", f"http://{HOST}:18910/"):
            config = self._config(printer_url=address).connections[0]
            self.assertEqual((config.adapter, config.material_provider), ("anycubic", "anycubic"))
            self.assertEqual(config.moonraker_url, f"http://{HOST}:18910")

    def test_options_of_other_printers_are_refused(self) -> None:
        for extra in (
            {"serial_number": SERIAL},
            {"check_code": "abc"},
            {"access_code": "123"},
            {"moonraker_api_key": "key"},
            {"auto_refresh": True},
            {"material_provider": "happy_hare"},
            {"printer_url": f"http://{HOST}:7125"},
            {"printer_url": f"https://{HOST}"},
        ):
            with self.subTest(extra=extra), self.assertRaises(ConfigurationError):
                self._config(**extra)

    def test_the_node_builds_an_anycubic_reader(self) -> None:
        config = self._config().connections[0]
        reader = build_connection(config, store=None, state=None).provider  # type: ignore[arg-type]
        self.assertIsInstance(reader, AnycubicProvider)
        assert isinstance(reader, AnycubicProvider)
        self.assertEqual(reader.host, HOST)


if __name__ == "__main__":
    unittest.main()
