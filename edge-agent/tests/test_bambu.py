"""Bambu Lab reader over the printer's LAN MQTT service.

The printer is a fake broker in this process: over a socket pair for the MQTT
conversation, and behind real TLS on loopback for the certificate rule. The
report fixture is synthetic and follows the field names of a P1-series report.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import importlib.util
import json
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from test_runtime import FakeCloud

from filamenthub_edge.cloud import DesiredResult
from filamenthub_edge.config import NodeConfig
from filamenthub_edge.errors import ConfigurationError, ProviderUnavailable
from filamenthub_edge.node import build_connection
from filamenthub_edge.providers import bambu, bambu_files, bambu_tls
from filamenthub_edge.providers.bambu import BambuProvider
from filamenthub_edge.runtime import EdgeRuntime
from filamenthub_edge.state import EdgeState, StateStore

EDGE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "bambu" / "report_printing.json"
SERIAL = "01S00A123456789"
OTHER_SERIAL = "01S00A987654321"
ACCESS_CODE = "97531246"


def fixture_report() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _read_packet(sock: Any) -> tuple[int, bytes]:
    def exact(length: int) -> bytes:
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                raise ConnectionError("closed")
            data += chunk
        return data

    header = exact(1)[0]
    length = shift = 0
    while True:
        digit = exact(1)[0]
        length |= (digit & 0x7F) << shift
        shift += 7
        if not digit & 0x80:
            return header, exact(length)


def _field(body: bytes, offset: int) -> tuple[bytes, int]:
    length = struct.unpack("!H", body[offset : offset + 2])[0]
    return body[offset + 2 : offset + 2 + length], offset + 2 + length


def _packet(kind: int, body: bytes) -> bytes:
    length = len(body)
    encoded = bytearray()
    while True:
        digit = length & 0x7F
        length >>= 7
        encoded.append(digit | (0x80 if length else 0))
        if not length:
            return bytes([kind]) + bytes(encoded) + body


class Broker:
    """What a Bambu printer's MQTT service does for one client at a time."""

    def __init__(self, *, reports: list[dict[str, Any]] | None = None, refuse: bool = False):
        self.reports = [fixture_report()] if reports is None else reports
        self.report_serial = SERIAL
        self.refuse = refuse
        self.logins: list[tuple[bytes, bytes]] = []
        self.subscriptions: list[bytes] = []
        self.requests: list[tuple[bytes, dict[str, Any]]] = []
        self.connections = 0
        self._current: Any = None
        self._lock = threading.Lock()

    def connect(self) -> socket.socket:
        """The provider's way in when the test needs no TLS."""
        client, server = socket.socketpair()
        threading.Thread(target=self.serve, args=(server,), daemon=True).start()
        return client

    def publish(self, report: dict[str, Any], *, serial: str | None = None) -> None:
        topic = f"device/{serial or self.report_serial}/report".encode()
        body = struct.pack("!H", len(topic)) + topic + json.dumps({"print": report}).encode()
        with self._lock:
            self._current.sendall(_packet(0x30, body))

    def drop(self) -> None:
        with self._lock:
            # Closing alone does not end a connection another thread is reading.
            self._current.shutdown(socket.SHUT_RDWR)

    def serve(self, sock: Any) -> None:
        self.connections += 1
        try:
            _, body = _read_packet(sock)
            _, offset = _field(body, 0)
            _, offset = _field(body, offset + 4)
            user, offset = _field(body, offset)
            password, _ = _field(body, offset)
            self.logins.append((user, password))
            sock.sendall(_packet(0x20, bytes([0, 5 if self.refuse else 0])))
            if self.refuse:
                sock.close()
                return
            while True:
                header, body = _read_packet(sock)
                kind = header & 0xF0
                if kind == 0x80:
                    topic, _ = _field(body, 2)
                    self.subscriptions.append(topic)
                    sock.sendall(_packet(0x90, body[:2] + b"\x00"))
                elif kind == 0x30:
                    topic, offset = _field(body, 0)
                    self.requests.append((topic, json.loads(body[offset:])))
                    with self._lock:
                        self._current = sock
                    for report in self.reports:
                        self.publish(report)
                elif kind == 0xC0:
                    with self._lock:
                        sock.sendall(_packet(0xD0, b""))
                elif kind == 0xE0:
                    return
        except (OSError, ValueError, struct.error):
            pass
        finally:
            sock.close()


def provider(broker: Broker, **options: Any) -> BambuProvider:
    return BambuProvider(
        "192.168.1.50",
        serial_number=SERIAL,
        access_code=ACCESS_CODE,
        timeout=options.pop("timeout", 3),
        connect=broker.connect,
        read_estimate=options.pop("read_estimate", lambda report: None),
        **options,
    )


def eventually(check: Any, *, within: float = 5.0) -> Any:
    """The reader is another thread; give it a moment, never a fixed sleep."""
    deadline = time.monotonic() + within
    while True:
        try:
            return check()
        except (AssertionError, ProviderUnavailable):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


class BambuReadingTest(unittest.TestCase):
    def test_reading_matches_the_fixture_shared_with_the_orca_plugin(self) -> None:
        # The OrcaSlicer plugin builds the same snapshot from the same report
        # with its own code; both are held to this one expected result.
        expected = json.loads(
            FIXTURE.with_name("report_printing.expected.json").read_text(encoding="utf-8")
        )
        report = fixture_report()
        slots, complete = bambu.build_slots(report)

        self.assertEqual(
            {
                "printer": bambu.build_printer(report),
                "slots": slots,
                "slot_topology_complete": complete,
            },
            expected,
        )

    def test_copies_of_the_plugin_modules_match_their_sources(self) -> None:
        # Slot numbering and certificate rules are written once, in the plugin.
        # An edit there that is not copied here would make the two disagree
        # about which slot a spool sits in.
        if not (EDGE_ROOT.parent / "orca-plugin").is_dir():
            self.skipTest("the plugin sources are not part of this checkout")
        spec = importlib.util.spec_from_file_location(
            "mirror_plugin_modules", EDGE_ROOT / "scripts" / "mirror_plugin_modules.py"
        )
        assert spec is not None and spec.loader is not None
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        for path, text in script.mirrors():
            with self.subTest(copy=path.name):
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    text,
                    "run edge-agent/scripts/mirror_plugin_modules.py",
                )

    def test_a_partial_report_changes_only_what_it_names(self) -> None:
        merged = bambu.merge_report(
            fixture_report(),
            {
                "gcode_state": "PAUSE",
                "ams": {"ams": [{"id": "0", "tray": [{"id": "1", "tray_color": "00FF00FF"}]}]},
            },
        )
        slots, complete = bambu.build_slots(merged)

        self.assertTrue(complete)
        self.assertEqual(bambu.build_printer(merged)["state"], "paused")
        self.assertEqual([slot["provider_index"] for slot in slots], [0, 1, 2, 3, 254])
        self.assertEqual(slots[1]["color_hex"], "00FF00")
        self.assertEqual(slots[1]["material"], "PETG")
        self.assertEqual(slots[0]["color_hex"], "FF6A13")

    def test_a_report_without_the_feed_is_not_a_topology(self) -> None:
        slots, complete = bambu.build_slots({"gcode_state": "IDLE", "nozzle_temper": 25})

        self.assertEqual((slots, complete), ([], False))


class BambuProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.providers: list[BambuProvider] = []
        retry = patch.object(bambu, "RETRY_INITIAL_S", 0.05)
        refused = patch.object(bambu, "RETRY_REFUSED_S", 0.05)
        retry.start()
        refused.start()
        self.addCleanup(retry.stop)
        self.addCleanup(refused.stop)
        self.addCleanup(lambda: [item.close() for item in self.providers])

    def provider(self, broker: Broker, **options: Any) -> BambuProvider:
        self.providers.append(provider(broker, **options))
        return self.providers[-1]

    def test_logs_in_and_asks_for_the_whole_report_once(self) -> None:
        broker = Broker()
        reader = self.provider(broker)

        first = reader.observe()
        second = reader.observe()

        self.assertEqual(broker.logins, [(b"bblp", ACCESS_CODE.encode())])
        self.assertEqual(broker.subscriptions, [f"device/{SERIAL}/report".encode()])
        # Asking again on every observation slows a P1 or A1 printer down.
        self.assertEqual(
            broker.requests,
            [
                (
                    f"device/{SERIAL}/request".encode(),
                    {"pushing": {"sequence_id": "0", "command": "pushall"}},
                )
            ],
        )
        self.assertEqual(first.printer["state"], "printing")
        self.assertEqual(len(second.slots), 5)
        self.assertTrue(first.slot_topology_complete)
        self.assertEqual(first.device_identity, ("bambu_serial", SERIAL))
        self.assertEqual(first.capabilities, ["read", "presence", "consumption", "tag_read"])

    def test_later_partial_reports_are_laid_over_the_whole_one(self) -> None:
        broker = Broker()
        reader = self.provider(broker)
        reader.observe()

        broker.publish({"gcode_state": "PAUSE", "mc_percent": 43})

        def paused() -> None:
            snapshot = reader.observe()
            self.assertEqual(snapshot.printer["state"], "paused")
            self.assertEqual(snapshot.printer["progress_percent"], 43)
            self.assertEqual(len(snapshot.slots), 5)

        eventually(paused)

    def test_a_refused_access_code_is_reported_and_nothing_more_is_asked(self) -> None:
        broker = Broker(refuse=True)
        reader = self.provider(broker, timeout=0.5)

        with self.assertRaisesRegex(ProviderUnavailable, "rejected the access code"):
            reader.observe()

        self.assertEqual(broker.subscriptions, [])
        self.assertEqual(broker.requests, [])

    def test_a_lost_link_discards_the_report_until_the_printer_answers_again(self) -> None:
        broker = Broker()
        reader = self.provider(broker, timeout=1)
        reader.observe()
        broker.reports = []

        broker.drop()

        # What the printer said before the link dropped is not what it says now.
        def unavailable() -> None:
            with self.assertRaises(ProviderUnavailable):
                reader.observe()

        eventually(unavailable)
        broker.reports = [{**fixture_report(), "gcode_state": "FINISH"}]
        broker.drop()

        self.assertEqual(eventually(reader.observe).printer["state"], "finished")
        self.assertGreaterEqual(broker.connections, 2)

    def test_a_report_about_another_printer_is_not_this_printers_state(self) -> None:
        broker = Broker()
        broker.report_serial = OTHER_SERIAL
        reader = self.provider(broker, timeout=0.5)

        with self.assertRaisesRegex(ProviderUnavailable, "check the serial number"):
            reader.observe()

    def test_a_printer_that_never_names_its_feed_still_reports_its_state(self) -> None:
        broker = Broker(reports=[{"gcode_state": "IDLE", "nozzle_temper": 24.0}])
        reader = self.provider(broker, timeout=0.5)

        snapshot = reader.observe()

        self.assertEqual(snapshot.printer, {"state": "idle", "nozzle_temperature": 24.0})
        self.assertEqual((snapshot.slots, snapshot.slot_topology_complete), ([], False))
        self.assertEqual(snapshot.capabilities, ["read", "presence", "consumption"])

    def test_observation_reaches_the_site_under_the_identity_the_plugin_uses(self) -> None:
        # A printer linked through OrcaSlicer and through Edge must stay one
        # printer: both derive the same evidence token from the serial number.
        key = "ab" * 32
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "connections" / "p1s.json")
            state = EdgeState(
                bridge_token="fhpb_" + "t" * 40,
                printer_discovery_key=key,
                physical_printer_id=7,
                material_system_id=9,
            )
            config = BambuConfigTest.load(BambuConfigTest.ENTRY).connections[0]
            cloud = FakeCloud()
            cloud.fail_upload = False
            runtime = EdgeRuntime(
                config=config,
                store=store,
                state=state,
                cloud=cloud,  # type: ignore[arg-type]
                provider=self.provider(Broker()),
            )

            runtime.run_cycle()

        observation = cloud.uploads[-1]
        self.assertEqual(
            (observation["provider"], observation["transport"]), ("bambu", "edge_agent")
        )
        self.assertEqual(
            observation["device_identity"],
            {
                "kind": "bambu_serial",
                "token": hmac.new(
                    bytes.fromhex(key),
                    ("device\0bambu_serial\0" + SERIAL).encode(),
                    hashlib.sha256,
                ).hexdigest(),
            },
        )
        self.assertNotIn(ACCESS_CODE, json.dumps(observation))
        self.assertNotIn(SERIAL, json.dumps(observation))


class TlsPrinter:
    """The same broker behind TLS on loopback, with a certificate of the test's choice."""

    def __init__(self, pki: Path) -> None:
        self.pki = pki
        self.broker = Broker()
        self._context: ssl.SSLContext | None = None
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.port = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def present(self, name: str) -> str:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.pki / f"{name}.pem", self.pki / f"{name}.key")
        self._context = context
        pem = (self.pki / f"{name}.pem").read_text(encoding="ascii")
        return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.strip())).hexdigest()

    def _accept(self) -> None:
        while True:
            try:
                connection, _ = self._listener.accept()
            except OSError:
                return
            assert self._context is not None
            try:
                secured = self._context.wrap_socket(connection, server_side=True)
            except OSError:
                connection.close()
                continue
            threading.Thread(target=self.broker.serve, args=(secured,), daemon=True).start()

    def close(self) -> None:
        self._listener.close()


class PrinterCertificates(unittest.TestCase):
    """A private authority, printer certificates it issued, and one it did not."""

    pki: Path
    _directory: tempfile.TemporaryDirectory[str]

    @classmethod
    def setUpClass(cls) -> None:
        openssl = shutil.which("openssl")
        if openssl is None:
            raise unittest.SkipTest("the openssl command is needed to make test certificates")
        cls._directory = tempfile.TemporaryDirectory()
        cls.pki = root = Path(cls._directory.name)
        (root / "openssl.cnf").write_text(
            "[req]\ndistinguished_name = dn\nprompt = no\n[dn]\nCN = unused\n"
            "[ca]\nbasicConstraints = critical,CA:TRUE\nkeyUsage = critical,keyCertSign,cRLSign\n",
            encoding="ascii",
        )

        def run(*args: str) -> None:
            subprocess.run([openssl, *args], cwd=root, check=True, capture_output=True, timeout=60)

        def key(name: str) -> None:
            run("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256",
                "-out", f"{name}.key")

        def self_signed(name: str, common_name: str, *extra: str) -> None:
            key(name)
            run("req", "-new", "-x509", "-config", "openssl.cnf", "-key", f"{name}.key",
                "-subj", f"/CN={common_name}", "-days", "30", "-out", f"{name}.pem", *extra)

        def issued(name: str, common_name: str) -> None:
            key(name)
            run("req", "-new", "-config", "openssl.cnf", "-key", f"{name}.key",
                "-subj", f"/CN={common_name}", "-out", f"{name}.csr")
            run("x509", "-req", "-in", f"{name}.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
                "-CAcreateserial", "-days", "30", "-out", f"{name}.pem")

        self_signed("ca", "Test Printer CA", "-extensions", "ca")
        issued("printer", SERIAL)
        issued("reissued", SERIAL)
        issued("neighbour", OTHER_SERIAL)
        self_signed("stranger", SERIAL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()


class BambuTrustTest(PrinterCertificates):
    def setUp(self) -> None:
        self.printer = TlsPrinter(self.pki)
        self.addCleanup(self.printer.close)
        self.state = tempfile.TemporaryDirectory()
        self.addCleanup(self.state.cleanup)
        self.trust_path = Path(self.state.name) / "connections" / "p1s.bambu.json"
        issuers = patch.object(
            bambu_tls, "BAMBU_CA_CERTIFICATES", (self.pki / "ca.pem").read_text(encoding="ascii")
        )
        retry = patch.object(bambu, "RETRY_REFUSED_S", 0.05)
        issuers.start()
        retry.start()
        self.addCleanup(issuers.stop)
        self.addCleanup(retry.stop)

    def reader(self) -> BambuProvider:
        reader = BambuProvider(
            "127.0.0.1",
            port=self.printer.port,
            serial_number=SERIAL,
            access_code=ACCESS_CODE,
            timeout=3,
            trust_path=self.trust_path,
        )
        self.addCleanup(reader.close)
        return reader

    def remembered(self) -> str | None:
        if not self.trust_path.exists():
            return None
        document = json.loads(self.trust_path.read_text(encoding="utf-8"))
        return document["certificate"] if document["serial"] == SERIAL else None

    def test_a_printer_is_remembered_once_it_accepts_the_access_code(self) -> None:
        shown = self.printer.present("stranger")

        self.assertEqual(self.reader().observe().printer["state"], "printing")

        # Bambu Lab did not issue this certificate; a printer met for the
        # first time is still trusted, because newer models have issuers this
        # build may not carry.
        self.assertEqual(self.remembered(), shown)

    def test_a_device_that_refuses_the_access_code_is_not_remembered(self) -> None:
        self.printer.present("printer")
        self.printer.broker.refuse = True

        with self.assertRaises(ProviderUnavailable):
            self.reader().observe()

        self.assertIsNone(self.remembered())

    def test_another_device_at_the_address_never_receives_the_access_code(self) -> None:
        self.printer.present("printer")
        self.reader().observe()
        logins = len(self.printer.broker.logins)

        self.printer.present("stranger")

        with self.assertRaisesRegex(ProviderUnavailable, "certificate changed"):
            self.reader().observe()
        self.assertEqual(len(self.printer.broker.logins), logins)

    def test_a_new_certificate_issued_to_the_same_printer_is_accepted(self) -> None:
        self.printer.present("printer")
        self.reader().observe()

        reissued = self.printer.present("reissued")

        self.assertEqual(self.reader().observe().printer["state"], "printing")
        self.assertEqual(self.remembered(), reissued)

    def test_a_reset_connection_meets_the_printer_anew(self) -> None:
        # A replaced mainboard shows a certificate nobody vouches for. Without
        # a way to forget the old one the printer could never be linked again.
        self.printer.present("printer")
        reader = self.reader()
        reader.observe()
        reader.close()
        replaced = self.printer.present("stranger")

        reader.forget()

        self.assertEqual(reader.observe().printer["state"], "printing")
        self.assertEqual(self.remembered(), replaced)

    def test_a_certificate_issued_to_another_printer_is_refused(self) -> None:
        self.printer.present("printer")
        self.reader().observe()
        logins = len(self.printer.broker.logins)

        self.printer.present("neighbour")

        with self.assertRaisesRegex(ProviderUnavailable, "names another printer"):
            self.reader().observe()
        self.assertEqual(len(self.printer.broker.logins), logins)


ESTIMATE = {"source": "slicer_gcode", "weights": {0: 20.0}, "sha256": "ab" * 32}


class AssignedCloud(FakeCloud):
    """The site with one spool assigned to the AMS slot the fixture prints from."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_upload = False

    def desired_snapshot(self, **kwargs: Any) -> DesiredResult:
        return DesiredResult(
            True,
            '"revision-1"',
            {
                "revision": "revision-1",
                "physical_printer_id": 7,
                "material_system_id": 9,
                "system_name": "AMS",
                "system_kind": "mmu",
                "slots": [
                    {
                        "index": 1,
                        "usage_route_proof": "proof-for-slot-1",
                        "spool": {"id": 99, "initial_weight_g": 1000},
                    }
                ],
            },
        )


class BambuUsageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = StateStore(Path(self.directory.name) / "connections" / "p1s.json")
        self.store.save(
            EdgeState(
                bridge_token="fhpb_" + "t" * 40,
                printer_discovery_key="ab" * 32,
                physical_printer_id=7,
                material_system_id=9,
            )
        )
        self.cloud = AssignedCloud()
        self.readers: list[BambuProvider] = []
        self.addCleanup(lambda: [item.close() for item in self.readers])

    def start(self, broker: Broker) -> tuple[EdgeRuntime, BambuProvider]:
        """Edge as it comes up: state from disk, a new link to the printer."""
        reader = provider(broker, read_estimate=lambda report: dict(ESTIMATE))
        self.readers.append(reader)
        runtime = EdgeRuntime(
            config=BambuConfigTest.load(BambuConfigTest.ENTRY).connections[0],
            store=self.store,
            state=self.store.load(),
            cloud=self.cloud,  # type: ignore[arg-type]
            provider=reader,
        )
        return runtime, reader

    def cycle_at(self, runtime: EdgeRuntime, reader: BambuProvider, percent: int) -> None:
        """Run a cycle once the reader has heard the printer reach ``percent``."""

        def heard() -> None:
            self.assertEqual(reader.observe().printer["progress_percent"], percent)

        eventually(heard)
        runtime.run_cycle()

    def test_a_job_watched_across_a_restart_is_charged_once(self) -> None:
        # The file says the job takes 20 g. Edge starts watching at 42 %, is
        # restarted at 50 % and sees the job finish: 58 % of 20 g, charged to
        # the spool the site put in the slot that is feeding, in one event.
        broker = Broker()
        runtime, reader = self.start(broker)
        self.cycle_at(runtime, reader, 42)
        broker.publish({"mc_percent": 50})
        self.cycle_at(runtime, reader, 50)
        self.assertEqual(self.cloud.usage_uploads, [])
        reader.close()

        restarted = Broker(reports=[{**fixture_report(), "mc_percent": 60}])
        runtime, reader = self.start(restarted)
        self.cycle_at(runtime, reader, 60)
        restarted.publish({"gcode_state": "FINISH", "mc_percent": 100})
        self.cycle_at(runtime, reader, 100)

        self.assertEqual(len(self.cloud.usage_uploads), 1)
        batch = self.cloud.usage_uploads[0]
        self.assertEqual((batch["provider"], batch["transport"]), ("bambu", "edge_agent"))
        (event,) = batch["events"]
        self.assertEqual((event["event_type"], event["outcome"]), ("terminal", "completed"))
        (item,) = event["items"]
        self.assertAlmostEqual(item["used_weight_g"], 11.6)
        self.assertEqual(
            {key: item[key] for key in ("slot_index", "spool_id", "usage_route_proof")},
            {"slot_index": 1, "spool_id": 99, "usage_route_proof": "proof-for-slot-1"},
        )
        self.assertEqual(
            (item["consumption_kind"], item["estimate_source"]), ("estimated", "slicer_progress")
        )
        # A finished job no longer stands in the way of resetting the connection.
        self.assertEqual(runtime.connection_reset_blockers(), [])

        runtime.run_cycle()
        self.assertEqual(len(self.cloud.usage_uploads), 1)

    def test_a_starting_job_does_not_inherit_the_finished_one(self) -> None:
        finished = {
            **fixture_report(),
            "gcode_state": "FINISH",
            "mc_percent": 100,
            "ams_mapping": [1],
        }

        again = bambu.carry_over(finished, {"gcode_state": "PREPARE"})
        other = bambu.carry_over(finished, {"subtask_name": "another.3mf"})

        # The same job sent again keeps its mapping; its progress starts over.
        self.assertNotIn("mc_percent", again)
        self.assertEqual(again["ams_mapping"], [1])
        self.assertIn("ams", again)
        # Another job must not be counted against the finished job's slots.
        self.assertNotIn("ams_mapping", other)


GCODE = b"; filament used [g] = 20.00\nG1 X1 E1\n"


class FilePrinter:
    """Implicit-TLS FTP holding print files, as much of it as Edge's reader uses."""

    def __init__(self, pki: Path, *, data_certificate: str | None = None) -> None:
        # The fixture report names its job "fixture.3mf".
        self.files = {"/cache": ["fixture.3mf", "other.gcode"]}
        self.logins: list[tuple[str, str]] = []
        self._control = self._context(pki, "printer")
        # Data connections from the control context can resume its session;
        # another context forces a new one with its own certificate.
        self._data = self._control if data_certificate is None else self._context(
            pki, data_certificate
        )
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.port = self._listener.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    @staticmethod
    def _context(pki: Path, name: str) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(pki / f"{name}.pem", pki / f"{name}.key")
        return context

    def _serve(self) -> None:
        while True:
            try:
                raw, _ = self._listener.accept()
            except OSError:
                return
            try:
                self._session(self._control.wrap_socket(raw, server_side=True))
            except OSError:
                raw.close()

    def _session(self, control: ssl.SSLSocket) -> None:
        def reply(text: str) -> None:
            control.sendall(text.encode("ascii") + b"\r\n")

        passive: socket.socket | None = None
        user = ""
        reply("220 ready")
        for line in control.makefile("rb"):
            command, _, argument = line.decode("ascii").strip().partition(" ")
            if command == "USER":
                user = argument
                reply("331 password")
            elif command == "PASS":
                self.logins.append((user, argument))
                reply("230 in")
            elif command in {"PBSZ", "PROT", "TYPE"}:
                reply("200 ok")
            elif command == "PASV":
                passive = socket.create_server(("127.0.0.1", 0))
                port = passive.getsockname()[1]
                reply("227 Entering Passive Mode (127,0,0,1,%d,%d)" % (port >> 8, port & 255))
            elif command == "SIZE":
                reply("213 %d" % len(GCODE))
            elif command in {"NLST", "RETR"} and passive is not None:
                body = GCODE if command == "RETR" else "".join(
                    name + "\r\n" for name in self.files.get(argument, [])
                ).encode("ascii")
                reply("150 sending")
                raw, _ = passive.accept()
                passive.close()
                try:
                    data = self._data.wrap_socket(raw, server_side=True)
                    data.sendall(body)
                    data.unwrap().close()
                except OSError:
                    raw.close()
                reply("226 done")
            elif command == "QUIT":
                reply("221 bye")
                return
            else:
                reply("502 not here")

    def close(self) -> None:
        self._listener.close()


class BambuFileTest(PrinterCertificates):
    def read(self, printer: FilePrinter, report: dict[str, Any]) -> dict[str, Any] | None:
        self.addCleanup(printer.close)
        return bambu_files.read_job_estimate(
            "127.0.0.1",
            port=printer.port,
            serial=SERIAL,
            access_code=ACCESS_CODE,
            memory=bambu_tls.CertificateMemory(None),
            report=report,
        )

    def test_the_running_jobs_own_file_gives_the_estimate(self) -> None:
        printer = FilePrinter(self.pki)

        estimate = self.read(printer, fixture_report())

        assert estimate is not None
        self.assertEqual(estimate["weights"], {0: 20.0})
        self.assertEqual(estimate["sha256"], hashlib.sha256(GCODE).hexdigest())
        self.assertEqual(printer.logins, [("bblp", ACCESS_CODE)])

    def test_a_job_whose_file_cannot_be_told_apart_has_no_estimate(self) -> None:
        # Two files could be the job's; taking either would be a guess.
        printer = FilePrinter(self.pki)
        printer.files["/model"] = ["fixture.3mf"]

        self.assertIsNone(self.read(printer, fixture_report()))

    def test_a_file_served_by_another_device_is_not_believed(self) -> None:
        # The control connection is the printer, but the file would come from
        # somebody else: what it says about filament must not be charged.
        printer = FilePrinter(self.pki, data_certificate="stranger")

        with self.assertRaisesRegex(ProviderUnavailable, "changed certificate"):
            self.read(printer, fixture_report())


class BambuConfigTest(unittest.TestCase):
    ENTRY = {
        "id": "p1s",
        "adapter": "bambu",
        "printer_url": "192.168.1.50",
        "serial_number": SERIAL,
        "access_code": ACCESS_CODE,
        "pairing_code": "FH-AAAAA-BBBBB",
    }

    @staticmethod
    def load(entry: dict[str, Any]) -> NodeConfig:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"connections": [entry]}), encoding="utf-8")
            with patch.dict("os.environ", {"FH_EDGE_OPTIONS_FILE": str(path)}, clear=True):
                return NodeConfig.load()

    def test_a_printer_is_named_by_its_address_alone_and_its_code_stays_hidden(self) -> None:
        config = self.load(self.ENTRY).connections[0]

        self.assertEqual(config.material_provider, "bambu")
        self.assertEqual(config.moonraker_url, "mqtts://192.168.1.50:8883")
        self.assertNotIn(ACCESS_CODE, repr(config))
        self.assertIsInstance(
            build_connection(config, store=None, state=None).provider,  # type: ignore[arg-type]
            BambuProvider,
        )

    def test_incomplete_or_mixed_settings_fail_closed(self) -> None:
        entry = copy.deepcopy(self.ENTRY)
        invalid = [
            {k: v for k, v in entry.items() if k != "access_code"},
            {k: v for k, v in entry.items() if k != "serial_number"},
            {**entry, "serial_number": "no spaces allowed"},
            {**entry, "printer_url": "http://192.168.1.50"},
            {**entry, "printer_url": "192.168.1.50/path"},
            {**entry, "material_provider": "happy_hare"},
            {**entry, "check_code": "a1b2c3d4"},
            {**entry, "moonraker_api_key": "secret"},
            {"id": "voron", "moonraker_url": "http://voron.test", "access_code": ACCESS_CODE},
        ]
        for item in invalid:
            with self.subTest(entry=item), self.assertRaises(ConfigurationError):
                self.load(item)


if __name__ == "__main__":
    unittest.main()
