"""Creality printers linked through OrcaSlicer's own connection settings."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from .filamenthub_plugin_test_support import PLUGIN_ROOT

# The fixtures are shared with FH Edge, which reads the same printers.
FIXTURES = PLUGIN_ROOT.parent / "edge-agent" / "tests" / "fixtures" / "creality"
DISCOVERY_KEY = "cd" * 32
MAC = "FCEE28A1F6BE"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _connection(label="K2 Plus 0.4", host="192.168.1.50"):
    return {"label": label, "host": host}


def test_slots_follow_what_the_printer_marks_as_selected(plugin_module):
    slots, complete = plugin_module.creality_slots(_fixture("boxsinfo_selected.json"))

    assert complete is True
    assert [slot["provider_index"] for slot in slots] == [0, 1, 2, 3, 255]
    assert [slot["present"] for slot in slots] == [True, True, False, True, True]
    # Only the slot the printer selected feeds; the others are merely loaded.
    assert [slot["active_feed"] for slot in slots] == [False, True, False, False, False]
    assert (slots[0]["material"], slots[0]["color_hex"], slots[0]["remaining_percent"]) == (
        "PETG", "7A92AC", 64,
    )
    assert "material" not in slots[2] and "color_hex" not in slots[2]
    assert (slots[4]["kind"], slots[4]["material"]) == ("external", "ABS")


def test_firmware_without_a_selected_mark_tells_selected_from_loaded_by_state(plugin_module):
    slots, complete = plugin_module.creality_slots(_fixture("boxsinfo_by_state.json"))

    assert complete is True
    # Two chained CFS units and a spool holder the printer left blank.
    assert [slot["provider_index"] for slot in slots] == [0, 1, 2, 3, 4, 5, 6, 7, 255]
    assert [slot["label"] for slot in slots][4] == "CFS 2 slot 1"
    assert [slot.get("active_feed") for slot in slots[:8]] == [
        False, True, False, False, False, False, False, False,
    ]
    assert slots[8]["present"] is None


def test_firmware_that_marks_nothing_leaves_the_feed_unknown(plugin_module):
    answer = _fixture("boxsinfo_by_state.json")
    for box in answer["boxsInfo"]["materialBoxs"]:
        for material in box["materials"]:
            material["state"] = min(material["state"], 1)

    slots, _complete = plugin_module.creality_slots(answer)

    assert all("active_feed" not in slot for slot in slots)
    assert plugin_module.creality_slots({"boxsInfo": {}}) == ([], False)


def test_status_of_a_real_idle_k1c_reads_as_idle_with_nothing_to_charge(plugin_module):
    status = _fixture("status_idle_k1c.json")

    assert plugin_module.creality_printer(status) == {
        "state": "idle",
        "nozzle_temperature": 25.0,
        "nozzle_target_temperature": 0.0,
        "bed_temperature": 24.0,
        "bed_target_temperature": 0.0,
        "chamber_temperature": 25.0,
    }
    assert plugin_module.creality_usage(status) == {"state": "standby", "filament_used_mm": 0.0}


@pytest.mark.parametrize(("code", "extra", "expected"), [
    (1, {}, "printing"),
    (1, {"pause": 1}, "paused"),
    (5, {}, "paused"),
    (2, {}, "complete"),
    (3, {}, "error"),
    (4, {}, "cancelled"),
    # A job being started or cancelled says nothing certain about its filament.
    (9, {}, None),
    (7, {}, None),
])
def test_print_states_are_read_as_the_k1_family_sends_them(plugin_module, code, extra, expected):
    status = dict(_fixture("status_printing.json"), state=code, **extra)

    usage = plugin_module.creality_usage(status)

    assert (usage or {}).get("state") == expected
    if expected:
        assert usage["file_name"] == "benchy.gcode"
        assert usage["filament_used_mm"] == pytest.approx(2350.5)
        assert usage["duration_s"] == 1260


def test_a_printing_status_fills_the_printer_card(plugin_module):
    printer = plugin_module.creality_printer(_fixture("status_printing.json"))

    assert printer["state"] == "printing"
    assert (printer["job_name"], printer["progress_percent"]) == ("benchy.gcode", 42)
    assert (printer["current_layer"], printer["total_layers"]) == (58, 140)
    assert printer["remaining_seconds"] == 1740


def test_mac_address_and_host_are_read_strictly(plugin_module):
    assert plugin_module.creality_mac({"model": "F008", "mac": "fc:ee:28:a1:f6:be"}) == MAC
    assert plugin_module.creality_mac({"mac": "00:00:00:00:00:00"}) == ""
    assert plugin_module.creality_mac({"mac": "not a mac"}) == ""
    assert plugin_module.creality_host("http://192.168.1.50:80/") == "192.168.1.50"
    assert plugin_module.creality_host("192.168.1.50/secret?x=1") == ""


@pytest.mark.parametrize(("host_type", "agent", "model", "route"), [
    ("crealityprint", "crealityprint", "Creality K2 Plus", "known"),
    # OrcaSlicer 2.5 profiles: type Octo/Klipper, agent CrealityPrint.
    ("octoprint", "crealityprint", "Creality K1C", "known"),
    # Saved before OrcaSlicer knew CrealityPrint: the default type, no agent.
    ("octoprint", "", "Creality K1C", "probe"),
    ("moonraker", "", "Creality K1 Max_CFS-C", "probe"),
    ("octoprint", "", "Creality SPARKX i7", "probe"),
    # OrcaSlicer does not reach these models through CrealityPrint.
    ("octoprint", "", "Creality Ender-3 V3 KE", ""),
    ("octoprint", "", "Creality Hi", ""),
    ("prusalink", "", "Creality K1C", ""),
])
def test_a_profile_says_how_a_creality_printer_is_reached(plugin_module, host_type, agent, model, route):
    assert plugin_module.creality_profile_route(host_type, agent, model) == route


def test_a_creality_profile_of_another_type_is_offered_only_when_the_printer_answers(
    plugin_module, monkeypatch,
):
    answers = {"192.168.1.60": ({"mac": "fc:ee:28:a1:f6:be"}, None),
               "192.168.1.61": (None, "unreachable"),
               # A rooted K1 serving something else at /info is not a stock Creality.
               "192.168.1.62": ({"result": {}}, None)}
    asked = []

    def read_info(connection):
        asked.append(connection["host"])
        return answers[connection["host"]]

    monkeypatch.setattr(plugin_module, "read_creality_info", read_info)
    candidates = plugin_module.creality_setup_candidates([
        {"label": "K2 Plus", "host": "192.168.1.50", "route": "known"},
        {"label": "K1C old profile", "host": "192.168.1.60", "route": "probe"},
        {"label": "K1 off", "host": "192.168.1.61", "route": "probe"},
        {"label": "K1 rooted", "host": "192.168.1.62", "route": "probe"},
        # Two nozzle presets of one printer; one of them names it Creality.
        {"label": "K1 0.6", "host": "192.168.1.63", "route": "probe"},
        {"label": "K1 0.4", "host": "192.168.1.63", "route": "known"},
    ])
    assert [item["label"] for item in candidates] == ["K2 Plus", "K1C old profile", "K1 0.6"]
    assert {item["provider"] for item in candidates} == {"creality"}
    # A printer known from its profile is not asked; only the uncertain ones are.
    assert asked == ["192.168.1.60", "192.168.1.61", "192.168.1.62"]


def _server_frame(payload, opcode=1):
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    if len(data) < 126:
        return struct.pack("!BB", 0x80 | opcode, len(data)) + data
    return struct.pack("!BBH", 0x80 | opcode, 126, len(data)) + data


class _FakePrinter:
    """A socket that answers like the printer: status first, slots when asked."""

    def __init__(self, plugin, *, answer_slots=True, status=None):
        self.plugin = plugin
        self.answer_slots = answer_slots
        self.status = status or _fixture("status_printing.json")
        self.incoming = b""
        self.outgoing = []
        self.texts = []
        self.closed = False
        self.handshaken = False

    def settimeout(self, _seconds):
        pass

    def connect(self, _address):
        pass

    def close(self):
        self.closed = True

    def sendall(self, data):
        if not self.handshaken:
            self.handshaken = True
            key = next(
                line.split(b":", 1)[1].strip()
                for line in data.split(b"\r\n") if line.lower().startswith(b"sec-websocket-key")
            )
            accept = base64.b64encode(
                hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
            )
            self.outgoing.append(
                b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n"
                + _server_frame(json.dumps(self.status))
                + _server_frame(json.dumps({"ModeCode": "heart_beat"}))
            )
            return
        self.incoming += data
        frames, self.incoming = self.plugin.creality_ws_frames(self.incoming)
        for _final, opcode, payload in frames:
            if opcode != 1:
                continue
            text = payload.decode("utf-8")
            self.texts.append(text)
            if "boxsInfo" in text and self.answer_slots:
                self.outgoing.append(
                    _server_frame(json.dumps(_fixture("boxsinfo_selected.json")))
                )

    def recv(self, _size):
        if not self.outgoing:
            raise TimeoutError("nothing more from the printer")
        return self.outgoing.pop(0)


@pytest.fixture
def wire(plugin_module, monkeypatch):
    plugin = plugin_module
    monkeypatch.setattr(
        plugin, "_resolved_lan_address", lambda host, port, error="": (2, 1, 6, (host, port))
    )
    monkeypatch.setattr(plugin, "CREALITY_SLOTS_REPLY_SECONDS", 0.2)
    monkeypatch.setattr(plugin, "CREALITY_NO_CFS_REPLY_SECONDS", 0.05)

    def use(printer):
        monkeypatch.setattr(plugin.socket, "socket", lambda *_args: printer)
        return printer

    return plugin, use


def test_one_reading_asks_only_for_slots_and_answers_the_heartbeat(wire):
    plugin, use = wire
    printer = use(_FakePrinter(plugin))

    reading, failure = plugin.read_creality_status(_connection())

    assert failure is None
    assert reading["status"]["printFileName"].endswith("benchy.gcode")
    assert plugin.creality_slots(reading["boxes"])[0][1]["active_feed"] is True
    # The slot query, the heartbeat answer, and nothing that changes the printer.
    assert printer.texts == ['{"method":"get","params":{"boxsInfo":1}}', "ok"]
    assert printer.closed is True


def test_a_printer_without_a_cfs_is_still_read(wire):
    plugin, use = wire
    use(_FakePrinter(plugin, answer_slots=False, status=_fixture("status_idle_k1c.json")))

    reading, failure = plugin.read_creality_status(_connection())

    assert failure is None and reading["boxes"] is None
    assert reading["status"]["model"] == "K1C 2025_CFS-C"


def test_something_else_at_the_address_is_not_taken_for_a_printer(wire):
    plugin, use = wire
    stranger = _FakePrinter(plugin)
    stranger.sendall = lambda data: stranger.outgoing.append(b"HTTP/1.1 200 OK\r\n\r\n")
    use(stranger)

    assert plugin.read_creality_status(_connection()) == (None, "invalid")


@pytest.fixture
def linked(plugin_module, monkeypatch, tmp_path):
    """A linked printer, its connection copied from OrcaSlicer, and a watcher driven by hand."""
    plugin = plugin_module
    calls = SimpleNamespace(
        posted=[], revoked=[], desired=0, status=_fixture("status_idle_k1c.json"),
        boxes=_fixture("boxsinfo_selected.json"), failure=None, mac=MAC,
    )
    monkeypatch.setattr(plugin, "CREALITY_CONFIG_FILE", str(tmp_path / ".fh_creality.json"))
    monkeypatch.setattr(plugin, "_CREALITY_KNOWN_HOSTS", {})
    monkeypatch.setattr(plugin, "plugin_source_instance_id", lambda: "desktop-source-instance")
    monkeypatch.setattr(plugin, "USAGE_WATCH_RETRY_SECONDS", 0.0)
    monkeypatch.setattr(plugin, "USAGE_WATCH_SNAPSHOT_MIN_SECONDS", 0.0)
    monkeypatch.setitem(plugin._CREALITY_CONNECTIONS, "items", [_connection()])

    def info(_connection_):
        return ({"model": "F008", "mac": calls.mac}, None) if calls.mac else (None, "unreachable")

    def status(_connection_):
        if calls.failure:
            return None, calls.failure
        return {"status": dict(calls.status), "boxes": calls.boxes}, None

    def pair(path, token, payload):
        return 200, json.dumps({
            "bridge_token": "fhpb_" + "c" * 40, "physical_printer_id": 7,
            "material_system_id": 9, "printer_discovery_key": DISCOVERY_KEY,
        }).encode("utf-8")

    def post(path, token, payload):
        calls.posted.append((path, token, payload))
        if path.endswith("usage-batches"):
            return 200, json.dumps(
                {"accepted": True, "ack_sequence": payload["sequence"]}
            ).encode("utf-8"), None
        return 200, b"{}", None

    def desired(path, token):
        calls.desired += 1
        return 200, json.dumps({"slots": [
            {"index": 1, "usage_route_proof": "proof-slot-2", "spool": {"id": 31}},
            {"index": 3, "usage_route_proof": "proof-slot-4", "spool": {"id": 33}},
        ]}).encode("utf-8")

    monkeypatch.setattr(plugin, "read_creality_info", info)
    monkeypatch.setattr(plugin, "read_creality_status", status)
    monkeypatch.setattr(plugin, "http_post_json", pair)
    monkeypatch.setattr(plugin, "http_post_bridge_json", post)
    monkeypatch.setattr(plugin, "http_get_bridge_json", desired)
    monkeypatch.setattr(plugin, "revoke_fresh_bridge_token", calls.revoked.append)

    result = plugin.configure_creality_bridge(7, 9, "FH-AAAAA-BBBBB", "", [_connection()])
    assert result == {"ok": True, "code": "ok"}
    first = calls.posted[0][2]
    calls.posted.clear()

    def at(state, used, printed):
        calls.status = dict(
            _fixture("status_printing.json"), state=state,
            usedMaterialLength="%f" % used, printJobTime=printed,
        )

    def items():
        return [
            item
            for path, _token, payload in calls.posted if path.endswith("usage-batches")
            for event in payload["events"] for item in event["items"]
        ]

    return SimpleNamespace(
        plugin=plugin, calls=calls, at=at, items=items, first=first,
        runtime=plugin.CrealityWatchRuntime(), stored=Path(plugin.CREALITY_CONFIG_FILE),
    )


def test_linking_reports_the_printer_and_keeps_no_address(linked):
    assert linked.first["provider"] == "creality"
    assert linked.first["capabilities"] == ["read", "presence", "consumption"]
    assert len(linked.first["slots"]) == 5 and linked.first["slot_topology_complete"] is True
    identity = linked.first["device_identity"]
    assert identity["kind"] == "creality_mac" and len(identity["token"]) == 64
    stored = linked.stored.read_text(encoding="utf-8")
    assert MAC in stored and "192.168.1.50" not in stored


def test_a_print_is_charged_to_the_spool_in_the_selected_slot(linked):
    for state, used, printed in [(1, 100.0, 10), (1, 700.0, 400), (2, 1000.0, 500)]:
        linked.at(state, used, printed)
        linked.runtime.watch_once()

    assert [(item["spool_id"], item["usage_route_proof"]) for item in linked.items()] == [
        (31, "proof-slot-2"), (31, "proof-slot-2"),
    ]
    assert sum(item["used_length_mm"] for item in linked.items()) == pytest.approx(900.0)
    # The printer counted this length itself: it is not marked as an estimate.
    assert all("consumption_kind" not in item for item in linked.items())


def test_an_idle_printer_costs_the_site_nothing(linked):
    linked.runtime.watch_once()
    linked.calls.posted.clear()

    linked.runtime.watch_once()

    assert linked.calls.posted == [] and linked.calls.desired == 0


def test_another_printer_that_took_the_address_is_not_charged(linked):
    linked.at(1, 100.0, 10)
    linked.runtime.watch_once()
    # The address now answers under another name: it is someone else's print.
    linked.at(1, 900.0, 400)
    linked.calls.status["hostname"] = "K2-9999"
    linked.calls.mac = "AABBCCDDEEFF"
    linked.runtime.watch_once()
    linked.runtime.watch_once()

    assert linked.items() == []


def test_a_link_the_site_revoked_is_dropped_by_the_watcher(linked, monkeypatch):
    linked.at(1, 100.0, 10)
    monkeypatch.setattr(linked.plugin, "http_get_bridge_json", lambda path, token: (401, b""))

    linked.runtime.watch_once()

    assert linked.plugin._load_creality_bindings() == []
    assert linked.runtime.watch_once() is None
