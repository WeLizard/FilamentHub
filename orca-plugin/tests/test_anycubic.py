"""Anycubic Kobra 3 / S1 / X printers read over their LAN handshake and MQTT broker."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from .filamenthub_plugin_test_support import PLUGIN_ROOT

# The fixtures are shared with FH Edge, which will read the same printers.
FIXTURES = PLUGIN_ROOT.parent / "edge-agent" / "tests" / "fixtures" / "anycubic"
DISCOVERY_KEY = "cd" * 32
SERIAL = "KS1SN0000000001"
MODEL_ID = "20025"
DEVICE_ID = "d0e1f2a3b4c5d6e7f8091a2b3c4d5e6f"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _connection(label="Anycubic Kobra S1 0.4 nozzle", host="192.168.1.60"):
    return {"label": label, "host": host}


# --------------------------------------------------------------------------- #
# The block cipher and the handshake
# --------------------------------------------------------------------------- #


def test_the_block_cipher_matches_the_published_test_vectors():
    # The rounds are private to the adapter module, so it is imported as it is.
    import filamenthub_anycubic as plugin

    # FIPS-197 appendix C.1.
    keys = plugin._anycubic_round_keys(bytes(range(16)))
    assert plugin._anycubic_decrypt_block(
        bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a"), keys
    ) == bytes.fromhex("00112233445566778899aabbccddeeff")
    # NIST SP 800-38A F.2.2, CBC-AES128.Decrypt, all four blocks; the last
    # plaintext block happens not to be valid padding, so the blocks are
    # chained here by hand.
    keys = plugin._anycubic_round_keys(bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c"))
    cipher = bytes.fromhex(
        "7649abac8119b246cee98e9b12e9197d5086cb9b507219ee95db113a917678b2"
        "73bed6b8e3c1743b7116e69e222295163ff1caa1681fac09120eca307586e1a7"
    )
    previous, plain = bytes.fromhex("000102030405060708090a0b0c0d0e0f"), b""
    for offset in range(0, len(cipher), 16):
        block = cipher[offset:offset + 16]
        plain += bytes(a ^ b for a, b in zip(plugin._anycubic_decrypt_block(block, keys), previous))
        previous = block
    assert plain == bytes.fromhex(
        "6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e51"
        "30c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710"
    )
    assert plugin.anycubic_aes_cbc_decrypt(bytes(16), bytes(16), b"short") is None


def test_info_names_the_printer_and_where_its_login_is_asked_for(plugin_module):
    plugin = plugin_module
    info, failure = plugin.anycubic_info(_fixture("info_lan_s1.json"))

    assert failure is None
    assert (info["serial"], info["model_id"], info["model_name"]) == (
        SERIAL, MODEL_ID, "Anycubic Kobra S1",
    )
    url = plugin.anycubic_ctrl_url("192.168.1.60", info, 1764240000000, "a1b2c3", "D" * 32)
    # The signature is md5(md5(token[:16]) + timestamp + nonce).
    assert url == (
        "http://192.168.1.60:18910/ctrl?ts=1764240000000&nonce=a1b2c3"
        "&sign=213ba5354c8e59e3dbb10499aa7a2e0b&did=" + "D" * 32
    )


def test_the_signed_request_goes_to_the_printer_whatever_info_names(plugin_module):
    plugin = plugin_module
    answer = dict(_fixture("info_lan_s1.json"), ctrlInfoUrl="http://203.0.113.9:8080/ctrl")
    info, _failure = plugin.anycubic_info(answer)

    url = plugin.anycubic_ctrl_url("192.168.1.60", info, 1, "n", "d")

    assert url.startswith("http://192.168.1.60:8080/ctrl?") and "203.0.113.9" not in url


@pytest.mark.parametrize(("change", "expected"), [
    # LAN mode is off: the printer still says who it is.
    ({"ctrlType": "cloud"}, "lan_mode"),
    # The Kobra 2 generation answers without the handshake.
    ({"token": None}, "unsupported"),
    ({"ctrlInfoUrl": ""}, "unsupported"),
    ({"token": "too short"}, "invalid"),
    ({"cn": "../../etc"}, "invalid"),
    ({"ctrlInfoUrl": "ftp://192.168.1.60/ctrl"}, "invalid"),
    ({"ctrlInfoUrl": "http://192.168.1.60:port/ctrl"}, "invalid"),
])
def test_an_info_answer_that_does_not_allow_a_handshake_says_why(plugin_module, change, expected):
    info, failure = plugin_module.anycubic_info(dict(_fixture("info_lan_s1.json"), **change))

    assert failure == expected
    if expected == "lan_mode":
        assert info == {"serial": SERIAL}
    else:
        assert info is None


def test_the_sealed_answer_opens_to_the_broker_login(plugin_module):
    plugin = plugin_module
    info, _failure = plugin.anycubic_info(_fixture("info_lan_s1.json"))
    expected = _fixture("ctrl_session.json")

    session, failure = plugin.anycubic_session(_fixture("ctrl_answer.json"), info)

    assert failure is None
    assert session == {
        "port": 9883, "username": expected["username"], "password": expected["password"],
        "device_id": DEVICE_ID,
    }
    wrong = dict(info, token="X" * 32)
    assert plugin.anycubic_session(_fixture("ctrl_answer.json"), wrong) == (None, "invalid")
    assert plugin.anycubic_session({"code": 401, "message": "sign error"}, info) == (
        None, "refused",
    )


# --------------------------------------------------------------------------- #
# What the reports say
# --------------------------------------------------------------------------- #


def test_a_printing_report_fills_the_printer_card(plugin_module):
    printer = plugin_module.anycubic_printer(_fixture("info_printing_s1.json")["data"])

    assert printer == {
        "state": "printing",
        "job_name": "bracket_PLA_0.2.gcode.3mf",
        "progress_percent": 37,
        # The printer counts minutes.
        "remaining_seconds": 52 * 60,
        "current_layer": 48,
        "total_layers": 130,
        "nozzle_temperature": 219.6,
        "nozzle_target_temperature": 220.0,
        "bed_temperature": 60.0,
        "bed_target_temperature": 60.0,
        "chamber_temperature": 34.0,
    }


def test_an_idle_printer_shows_the_job_it_finished(plugin_module):
    printer = plugin_module.anycubic_printer(_fixture("info_idle_kobra3.json")["data"])

    assert (printer["state"], printer["job_name"], printer["progress_percent"]) == (
        "finished", "cube.gcode", 100,
    )
    assert "remaining_seconds" not in printer and "chamber_temperature" not in printer


@pytest.mark.parametrize(("raw", "phase", "pause", "expected"), [
    ("busy", "preheating", 0, "preparing"),
    ("busy", "auto_leveling", 0, "preparing"),
    ("busy", "printing", 1, "paused"),
    ("busy", "pausing", 2, "paused"),
    ("busy", "resumed", 0, "printing"),
    ("busy", "stoped", 4, "failed"),
    ("busy", "drying", 0, "unknown"),
    # A free printer has no job, whatever its last project still says.
    ("free", "paused", 1, "idle"),
    ("rebooting", "printing", 0, "unknown"),
])
def test_job_phases_become_bridge_states(plugin_module, raw, phase, pause, expected):
    data = {"state": raw, "project": {"state": phase, "pause": pause, "filename": "a.gcode"}}

    assert plugin_module.anycubic_printer(data)["state"] == expected


def test_ace_slots_say_what_is_loaded_and_which_one_feeds(plugin_module):
    slots, complete = plugin_module.anycubic_slots(_fixture("multicolorbox_ace_pro.json")["data"])

    assert complete is True
    assert [slot["provider_index"] for slot in slots] == [0, 1, 2, 3]
    assert [slot["label"] for slot in slots][2] == "ACE 1 slot 3"
    assert [slot["present"] for slot in slots] == [True, False, True, True]
    assert [slot["active_feed"] for slot in slots] == [False, False, True, False]
    assert (slots[2]["material"], slots[2]["color_hex"], slots[2]["remaining_percent"]) == (
        "PETG", "1A73E8", 55,
    )
    assert "material" not in slots[1] and "remaining_percent" not in slots[1]
    assert all(slot["spool_identity_known"] is False for slot in slots)


def test_a_partial_report_is_merged_and_not_taken_for_the_whole_unit(plugin_module):
    plugin = plugin_module
    partial = _fixture("multicolorbox_partial.json")["data"]

    slots, complete = plugin.anycubic_slots(partial)
    assert complete is False and [slot["present"] for slot in slots] == [None, True, None, None]

    merged = plugin.anycubic_merge_boxes(_fixture("multicolorbox_ace_pro.json")["data"], partial)
    slots, complete = plugin.anycubic_slots(merged)
    assert complete is True
    # The later report loaded slot 2 and unloaded the head; the rest is kept.
    assert slots[1]["material"] == "TPU" and slots[2]["material"] == "PETG"
    assert [slot["active_feed"] for slot in slots] == [False, False, False, False]


def test_the_spool_holder_answer_keeps_its_material_but_not_its_presence(plugin_module):
    holder = _fixture("extfilbox_answer.json")["data"]

    slots, complete = plugin_module.anycubic_slots(None, holder)

    assert complete is False
    assert slots == [{
        "provider_index": 255, "label": "External spool", "kind": "external",
        "present": None, "spool_identity_known": False,
        "material": "PLA", "color_hex": "FFA500",
    }]
    pushed = dict(holder, loaded=1, status_type=3, current_status=10)
    assert plugin_module.anycubic_slots(None, pushed)[0][0]["present"] is True


def test_only_reports_of_this_printer_are_read(plugin_module):
    plugin = plugin_module
    message = json.dumps(_fixture("info_printing_s1.json")).encode("utf-8")
    topic = "anycubic/anycubicCloud/v1/printer/public/%s/%s/info/report" % (MODEL_ID, DEVICE_ID)

    assert plugin.anycubic_report(topic, message, MODEL_ID, DEVICE_ID)[0] == "info"
    assert plugin.anycubic_report(topic.replace(DEVICE_ID, "other0000"), message, MODEL_ID,
                                  DEVICE_ID) is None
    assert plugin.anycubic_report(topic.replace("info/report", "response"), message, MODEL_ID,
                                  DEVICE_ID) is None
    echoed = json.dumps({"type": "info", "action": "query", "data": None}).encode("utf-8")
    assert plugin.anycubic_report(topic, echoed, MODEL_ID, DEVICE_ID) is None
    assert plugin.anycubic_report(topic, b"not json", MODEL_ID, DEVICE_ID) is None


@pytest.mark.parametrize(("model", "expected"), [
    ("Anycubic Kobra S1", True),
    ("Anycubic Kobra S1 Max", True),
    ("Anycubic Kobra 3", True),
    ("Anycubic Kobra 3 V2", True),
    ("Anycubic Kobra 3 Max V2", True),
    ("Anycubic Kobra X", True),
    ("Anycubic Kobra 2 Pro", False),
    ("Anycubic Kobra Neo", False),
    ("Anycubic Kobra 30", False),
    ("", False),
])
def test_profiles_of_the_lan_generation_are_recognised_by_their_model(plugin_module, model,
                                                                      expected):
    assert plugin_module.anycubic_profile(model) is expected


# --------------------------------------------------------------------------- #
# One reading over the network
# --------------------------------------------------------------------------- #


def _mqtt_string(text):
    data = text.encode("utf-8")
    return struct.pack("!H", len(data)) + data


def _mqtt_packet(kind, body):
    length, encoded = len(body), bytearray()
    while True:
        digit, length = length & 0x7F, length >> 7
        encoded.append(digit | (0x80 if length else 0))
        if not length:
            return bytes([kind]) + bytes(encoded) + body


def _mqtt_split(buffer):
    """Whole client packets from ``buffer``: ``([(header, body)], rest)``."""
    packets = []
    while len(buffer) >= 2:
        length, multiplier, offset = 0, 1, 1
        while True:
            if offset >= len(buffer):
                return packets, buffer
            digit = buffer[offset]
            length += (digit & 0x7F) * multiplier
            multiplier *= 128
            offset += 1
            if not digit & 0x80:
                break
        if len(buffer) < offset + length:
            break
        packets.append((buffer[0], buffer[offset:offset + length]))
        buffer = buffer[offset + length:]
    return packets, buffer


class _FakeBroker:
    """A socket that answers like the printer's broker."""

    def __init__(self, answers):
        self.answers = answers
        self.incoming = b""
        self.outgoing = b""
        self.login = None
        self.subscribed = None
        self.published = []
        self.disconnected = False
        self.closed = False

    def settimeout(self, _seconds):
        pass

    def connect(self, _address):
        pass

    def close(self):
        self.closed = True

    def sendall(self, data):
        self.incoming += data
        packets, self.incoming = _mqtt_split(self.incoming)
        for header, body in packets:
            kind = header & 0xF0
            if kind == 0x10:
                offset = 2 + 4 + 1 + 1 + 2
                fields = []
                while offset < len(body):
                    size = struct.unpack("!H", body[offset:offset + 2])[0]
                    fields.append(body[offset + 2:offset + 2 + size].decode("utf-8"))
                    offset += 2 + size
                self.login = (fields[1], fields[2])
                self.outgoing += _mqtt_packet(0x20, b"\x00\x00")
            elif kind == 0x80:
                size = struct.unpack("!H", body[2:4])[0]
                self.subscribed = body[4:4 + size].decode("utf-8")
                self.outgoing += _mqtt_packet(0x90, body[:2] + b"\x00")
            elif kind == 0x30:
                size = struct.unpack("!H", body[:2])[0]
                topic = body[2:2 + size].decode("utf-8")
                message = json.loads(body[2 + size:])
                self.published.append((topic, message))
                for answer in self.answers.get(message["type"], []):
                    report = "anycubic/anycubicCloud/v1/printer/public/%s/%s/%s/report" % (
                        MODEL_ID, DEVICE_ID, message["type"],
                    )
                    self.outgoing += _mqtt_packet(
                        0x30, _mqtt_string(report) + json.dumps(answer).encode("utf-8")
                    )
            elif kind == 0xE0:
                self.disconnected = True

    def recv(self, size):
        if not self.outgoing:
            raise TimeoutError("nothing more from the broker")
        chunk, self.outgoing = self.outgoing[:size], self.outgoing[size:]
        return chunk


@pytest.fixture
def wire(plugin_module, monkeypatch):
    plugin = plugin_module
    asked = []
    monkeypatch.setattr(
        plugin, "_resolved_lan_address", lambda host, port, error="": (2, 1, 6, (host, port))
    )
    monkeypatch.setattr(plugin, "_ANYCUBIC_KNOWN_HOSTS", {})
    monkeypatch.setattr(plugin, "ANYCUBIC_REPLY_SECONDS", 0.5)
    monkeypatch.setattr(plugin, "ANYCUBIC_AFTER_INFO_SECONDS", 0.2)
    monkeypatch.setattr(plugin, "_anycubic_tls_context", lambda: SimpleNamespace(
        wrap_socket=lambda raw, server_hostname=None: raw,
    ))
    state = SimpleNamespace(info=_fixture("info_lan_s1.json"))

    def http(url, method="GET"):
        asked.append((method, url.split("?", 1)[0]))
        if url.endswith(":18910/info"):
            return state.info, None
        return _fixture("ctrl_answer.json"), None

    monkeypatch.setattr(plugin, "_anycubic_http_json", http)

    def use(broker):
        monkeypatch.setattr(plugin.socket, "socket", lambda *_args: broker)
        return broker

    return SimpleNamespace(plugin=plugin, use=use, asked=asked, state=state)


def test_one_reading_logs_in_with_the_session_and_only_asks(wire):
    broker = wire.use(_FakeBroker({
        "info": [_fixture("info_printing_s1.json")],
        "multiColorBox": [_fixture("multicolorbox_ace_pro.json")],
    }))

    reading, failure = wire.plugin.read_anycubic_status(_connection())

    assert failure is None
    assert (reading["serial"], reading["model_id"]) == (SERIAL, MODEL_ID)
    assert reading["info"]["project"]["progress"] == 37
    assert len(reading["boxes"]["multi_color_box"][0]["slots"]) == 4
    session = _fixture("ctrl_session.json")
    assert broker.login == (session["username"], session["password"])
    assert broker.subscribed == "anycubic/anycubicCloud/v1/printer/public/%s/%s/#" % (
        MODEL_ID, DEVICE_ID,
    )
    # Three read-only requests, and nothing that changes the printer.
    assert [(topic.rsplit("/", 1)[-1], message["action"], message["data"])
            for topic, message in broker.published] == [
        ("info", "query", None), ("multiColorBox", "getInfo", None),
        ("extfilbox", "reportInfo", None),
    ]
    assert all("/web/printer/%s/%s/" % (MODEL_ID, DEVICE_ID) in topic
               for topic, _message in broker.published)
    assert broker.disconnected and broker.closed
    assert wire.asked == [
        ("GET", "http://192.168.1.60:18910/info"), ("POST", "http://192.168.1.60:18910/ctrl"),
    ]


def test_a_printer_without_an_ace_is_read_with_its_spool_holder(wire):
    wire.use(_FakeBroker({
        "info": [_fixture("info_idle_kobra3.json")],
        "extfilbox": [_fixture("extfilbox_answer.json")],
    }))

    reading, failure = wire.plugin.read_anycubic_status(_connection())

    assert failure is None and reading["boxes"] is None
    assert reading["holder"]["type"] == "PLA"


def test_a_printer_that_never_reports_its_state_is_not_read(wire):
    wire.use(_FakeBroker({"multiColorBox": [_fixture("multicolorbox_ace_pro.json")]}))

    assert wire.plugin.read_anycubic_status(_connection()) == (None, "invalid")


def test_another_printer_at_the_address_is_not_asked_for_its_login(wire):
    wire.use(_FakeBroker({}))

    assert wire.plugin.read_anycubic_status(_connection(), "OTHERSERIAL1") == (None, "other")
    assert [method for method, _url in wire.asked] == ["GET"]


def test_lan_mode_off_is_said_and_no_login_is_asked(wire):
    wire.state.info = _fixture("info_cloud_s1.json")

    assert wire.plugin.read_anycubic_status(_connection(), SERIAL) == (None, "lan_mode")
    assert [method for method, _url in wire.asked] == ["GET"]


# --------------------------------------------------------------------------- #
# Linking, reporting and the setup list
# --------------------------------------------------------------------------- #


@pytest.fixture
def linked(plugin_module, monkeypatch, tmp_path):
    """A linked printer, its connection copied from OrcaSlicer, and a watcher driven by hand."""
    plugin = plugin_module
    calls = SimpleNamespace(posted=[], revoked=[], info=_fixture("info_printing_s1.json"),
                            failure=None, serial=SERIAL)
    monkeypatch.setattr(plugin, "ANYCUBIC_CONFIG_FILE", str(tmp_path / ".fh_anycubic.json"))
    monkeypatch.setattr(plugin, "_ANYCUBIC_KNOWN_HOSTS", {})
    monkeypatch.setattr(plugin, "plugin_source_instance_id", lambda: "desktop-source-instance")
    monkeypatch.setattr(plugin, "USAGE_WATCH_SNAPSHOT_MIN_SECONDS", 0.0)
    monkeypatch.setitem(plugin._ANYCUBIC_CONNECTIONS, "items", [_connection()])

    def status(connection, serial=""):
        if calls.failure:
            return None, calls.failure
        if serial and serial != calls.serial:
            return None, "other"
        return {
            "serial": calls.serial, "model_id": MODEL_ID, "model_name": "Anycubic Kobra S1",
            "info": calls.info["data"],
            "boxes": _fixture("multicolorbox_ace_pro.json")["data"], "holder": None,
        }, None

    def pair(path, token, payload):
        calls.pair = payload
        return 200, json.dumps({
            "bridge_token": "fhpb_" + "c" * 40, "physical_printer_id": 7,
            "material_system_id": 9, "printer_discovery_key": DISCOVERY_KEY,
        }).encode("utf-8")

    def post(path, token, payload):
        calls.posted.append((path, token, payload))
        return 200, b"{}", None

    monkeypatch.setattr(plugin, "read_anycubic_status", status)
    # The watcher asks the site which spools are in the slots; nothing is assigned.
    monkeypatch.setattr(plugin, "http_get_bridge_json", lambda *_args: (200, b'{"slots": []}'))
    monkeypatch.setattr(plugin, "http_post_json", pair)
    monkeypatch.setattr(plugin, "http_post_bridge_json", post)
    monkeypatch.setattr(plugin, "revoke_fresh_bridge_token", calls.revoked.append)

    result = plugin.configure_anycubic_bridge(7, 9, "FH-AAAAA-BBBBB", "", [_connection()])
    assert result == {"ok": True, "code": "ok"}
    first = calls.posted[0][2]
    calls.posted.clear()
    return SimpleNamespace(
        plugin=plugin, calls=calls, first=first,
        runtime=plugin.AnycubicWatchRuntime(), stored=Path(plugin.ANYCUBIC_CONFIG_FILE),
    )


def test_linking_reports_the_printer_and_keeps_no_address_or_login(linked):
    assert linked.calls.pair["provider"] == "anycubic"
    assert linked.calls.pair["capabilities"] == ["read", "presence", "consumption"]
    assert linked.first["provider"] == "anycubic"
    assert linked.first["transport"] == "orca_plugin_lan"
    assert linked.first["printer"]["state"] == "printing"
    assert len(linked.first["slots"]) == 4 and linked.first["slot_topology_complete"] is True
    identity = linked.first["device_identity"]
    assert identity["kind"] == "anycubic_serial" and len(identity["token"]) == 64
    stored = linked.stored.read_text(encoding="utf-8")
    password = _fixture("ctrl_session.json")["password"]
    assert SERIAL in stored and "192.168.1.60" not in stored and password not in stored


def test_the_watcher_reports_changes_and_follows_a_print_more_often(linked):
    plugin = linked.plugin

    assert linked.runtime.watch_once() == plugin.USAGE_WATCH_PRINTING_SECONDS
    assert [path for path, _token, _payload in linked.calls.posted] == ["/printer-bridge/snapshot"]
    linked.calls.posted.clear()

    # Nothing changed: the site is not told again.
    linked.runtime.watch_once()
    assert linked.calls.posted == []

    linked.calls.info = _fixture("info_idle_kobra3.json")
    assert linked.runtime.watch_once() == plugin.USAGE_WATCH_IDLE_SECONDS
    assert linked.calls.posted[-1][2]["printer"]["state"] == "finished"


def test_a_printer_that_left_lan_mode_is_reported_unreachable(linked):
    linked.calls.failure = "lan_mode"

    code = linked.plugin.observe_anycubic_bindings([_connection()], 7, 9)

    assert code == {7: "lan_mode"}
    path, _token, payload = linked.calls.posted[-1]
    assert path == "/printer-bridge/heartbeat" and payload["provider_reachable"] is False


def test_another_printer_at_the_address_is_not_reported_as_this_one(linked):
    linked.calls.serial = "OTHERSERIAL1"

    assert linked.plugin.observe_anycubic_bindings([_connection()], 7, 9) == {7: "credentials"}
    assert all(path != "/printer-bridge/snapshot" for path, _t, _p in linked.calls.posted)


def test_a_link_the_site_revoked_is_dropped(linked, monkeypatch):
    monkeypatch.setattr(linked.plugin, "http_post_bridge_json", lambda *_args: (401, b"", None))

    assert linked.plugin.observe_anycubic_bindings([_connection()], 7, 9) == {7: "unpaired"}
    assert linked.plugin._load_anycubic_bindings() == []
    assert linked.runtime.watch_once() is None


def test_a_second_card_cannot_take_a_linked_printer(linked):
    result = linked.plugin.configure_anycubic_bridge(8, 10, "FH-CCCCC-DDDDD", "", [_connection()])

    assert result == {"ok": False, "code": "linked"}


def test_several_printers_are_offered_by_reference_not_by_address(linked):
    connections = [_connection(), _connection("Kobra 3", "192.168.1.61")]

    result = linked.plugin.configure_anycubic_bridge(8, 10, "FH-CCCCC-DDDDD", "", connections)

    assert result["code"] == "choose" and len(result["candidates"]) == 2
    assert "192.168" not in json.dumps(result)


def test_profiles_of_kobra_printers_are_offered_at_printer_setup(setup_flow, monkeypatch):
    plugin, catalog, _context, results, _uploads = setup_flow
    presets = [
        ("Anycubic Kobra S1 0.4 nozzle", "Anycubic Kobra S1", "192.168.1.60", "octoprint"),
        ("Kobra 3 workshop", "Anycubic Kobra 3 V2", "http://192.168.1.61:80/", "moonraker"),
        ("Kobra 2", "Anycubic Kobra 2 Pro", "192.168.1.62", "octoprint"),
        ("Kobra X", "Anycubic Kobra X", "", "octoprint"),
    ]

    class Preset:
        def __init__(self, name, model, host, host_type):
            self.name = name
            self._values = {"printer_model": model, "print_host": host, "host_type": host_type}

        @staticmethod
        def is_user():
            return True

        def config_value(self, key):
            return self._values.get(key)

    items = [Preset(*preset) for preset in presets]
    collection = type("Collection", (), {"size": lambda self: len(items),
                                         "preset": lambda self, index: items[index]})()
    monkeypatch.setattr(plugin.orca.host, "preset_bundle",
                        lambda: type("Bundle", (), {"printers": collection})(), raising=False)
    connections = plugin._snapshot_local_anycubic_connections()
    assert [(item["label"], item["host"]) for item in connections] == [
        ("Anycubic Kobra S1 0.4 nozzle", "192.168.1.60"), ("Kobra 3 workshop", "192.168.1.61"),
    ]

    catalog._do_printer_setup(
        {"operation": "list", "requestId": "list", "anycubic": connections}, "token", []
    )

    listed = [item for item in results[-1]["candidates"] if item["provider"] == "anycubic"]
    assert [item["label"] for item in listed] == ["Anycubic Kobra S1 0.4 nozzle", "Kobra 3 workshop"]
    assert all(item["source"] == "profile" and item["physicalPrinterId"] is None for item in listed)
    assert "192.168" not in json.dumps(results[-1])
