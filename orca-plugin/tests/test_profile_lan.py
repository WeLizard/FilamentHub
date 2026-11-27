"""SDCP printers and Elegoo's MQTT API, linked through OrcaSlicer's own connection settings."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from .filamenthub_plugin_test_support import PLUGIN_ROOT, set_host_attr

# The fixtures are shared with FH Edge, which is to read the same printers.
FIXTURES = PLUGIN_ROOT.parent / "edge-agent" / "tests" / "fixtures"
DISCOVERY_KEY = "cd" * 32
MAINBOARD_ID = "1c7319d30105041800009c0000000000"
SERIAL = "CC2A1B2C3D4E5F"
ACCESS_CODE = "246810"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _status(name):
    return _fixture(name)["Status"]


def _sdcp(host="192.168.1.139", route="known"):
    return {"label": "Elegoo Centauri Carbon 0.4 nozzle", "host": host, "route": route}


def _mqtt(host="192.168.1.140", access_code=ACCESS_CODE):
    return {"label": "Elegoo Centauri Carbon 2 0.4 nozzle", "host": host, "access_code": access_code}


# --------------------------------------------------------------------------- #
# Which protocol an OrcaSlicer profile reaches
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("host_type", "printer_model", "sdcp", "mqtt"), [
    ("elegoolink", "Elegoo Centauri Carbon", "known", False),
    ("elegoolink", "Elegoo Centauri Carbon 2", "", True),
    ("elegoolink", "Elegoo Centauri Carbon 2 ", "", True),
    # Set up with another host type: the printer's answer decides.
    ("moonraker", "Elegoo Centauri Carbon", "probe", False),
    ("octoprint", "Elegoo Centauri Carbon", "probe", False),
    ("octoprint", "Elegoo Centauri Carbon 2", "", True),
    # A custom ElegooLink profile may speak SDCP; OrcaSlicer tries Moonraker first.
    ("elegoolink", "My printer", "probe", False),
    ("elegoolink", "Elegoo Neptune 4 Pro", "probe", False),
    # Klipper printers under their own host type are not ours.
    ("moonraker", "Elegoo Neptune 4 Pro", "", False),
    ("prusalink", "Elegoo Centauri Carbon", "", False),
])
def test_profiles_are_routed_as_orcaslicer_routes_them(
    plugin_module, host_type, printer_model, sdcp, mqtt
):
    assert plugin_module.sdcp_profile_route(host_type, printer_model) == sdcp
    assert plugin_module.elegoo_mqtt_profile(host_type, printer_model) is mqtt


# --------------------------------------------------------------------------- #
# SDCP readings
# --------------------------------------------------------------------------- #
def test_an_idle_printer_with_the_last_jobs_totals_reads_as_idle(plugin_module):
    # A real V1.4.49 capture: Status 8 and 125 layers left over from the last print.
    printer = plugin_module.sdcp_printer(_status("sdcp/status_idle.json"))

    assert printer == {
        "state": "idle",
        "nozzle_temperature": 95.8,
        "nozzle_target_temperature": 0.0,
        "bed_temperature": 65.0,
        "bed_target_temperature": 0.0,
        "chamber_temperature": 22.4,
    }


def test_a_printing_sdcp_printer_fills_the_printer_card(plugin_module):
    printer = plugin_module.sdcp_printer(_status("sdcp/status_printing.json"))

    assert printer["state"] == "printing"
    assert (printer["job_name"], printer["progress_percent"]) == ("benchy_PLA.gcode", 28)
    assert (printer["current_layer"], printer["total_layers"]) == (17, 125)
    # FDM firmware counts ticks in seconds and reports no remaining time itself.
    assert printer["remaining_seconds"] == 4692


@pytest.mark.parametrize(("machine", "code", "expected"), [
    ([1], 13, "printing"),
    ([1], 18, "printing"),
    ([1], 12, "printing"),
    ([1], 6, "paused"),
    ([1], 5, "paused"),
    ([1], 9, "finished"),
    ([1], 8, "failed"),
    ([1], 14, "failed"),
    ([1], 16, "preparing"),
    ([1], 1, "preparing"),
    # A file transfer gives way to the next machine status.
    ([2, 1], 13, "printing"),
    ([2], 0, "preparing"),
    # Homing outside a job is still part of the named one.
    ([9], 1, "preparing"),
    ([0], 0, "idle"),
])
def test_sdcp_states_follow_elegoos_own_table(plugin_module, machine, code, expected):
    status = _status("sdcp/status_printing.json")
    status["CurrentStatus"] = machine
    status["PrintInfo"]["Status"] = code

    assert plugin_module.sdcp_printer(status)["state"] == expected


@pytest.mark.parametrize(("version", "supported"), [
    ("V1.4.49", True), ("V1.2.0", True), ("2.0.1", True), ("V1.1.9", False), ("", False), (None, False),
])
def test_canvas_is_asked_for_only_on_firmware_that_has_it(plugin_module, version, supported):
    assert plugin_module.sdcp_canvas_supported({"FirmwareVersion": version}) is supported


def test_identifiers_and_access_codes_are_read_strictly(plugin_module):
    assert plugin_module.sdcp_mainboard_id(MAINBOARD_ID.upper()) == MAINBOARD_ID
    assert plugin_module.sdcp_mainboard_id("0" * 32) == ""
    assert plugin_module.elegoo_mqtt_serial("CC2/../#") == ""
    assert plugin_module.elegoo_mqtt_system_info(
        json.dumps(_fixture("elegoo_mqtt/system_info.json")).encode("utf-8")
    ) == (SERIAL, None)
    assert plugin_module.elegoo_mqtt_system_info(b'{"error_code":1000}') == ("", "auth")
    # OrcaSlicer and Elegoo's library fall back to the printer's default code.
    assert plugin_module.elegoo_mqtt_access_code("") == "123456"
    assert plugin_module.elegoo_mqtt_access_code("bad code") == ""


# --------------------------------------------------------------------------- #
# CANVAS slots, the same over both protocols
# --------------------------------------------------------------------------- #
def test_canvas_slots_show_material_colour_and_the_loaded_one(plugin_module):
    slots, complete = plugin_module.canvas_slots(_fixture("elegoo_mqtt/canvas.json")["canvas_info"])

    assert complete is True
    assert [slot["provider_index"] for slot in slots] == [0, 1, 2, 3]
    assert slots[1]["label"] == "CANVAS 1 slot 2"
    assert [slot["present"] for slot in slots] == [True, True, False, True]
    # The tray whose filament is in the toolhead feeds; the others merely wait.
    assert [slot["active_feed"] for slot in slots] == [False, True, False, False]
    assert (slots[1]["material"], slots[1]["color_hex"]) == ("PETG", "1F6FB2")
    assert slots[3]["color_hex"] == "C0392B"
    assert "material" not in slots[2]


def test_trays_numbered_from_one_land_in_the_same_slots(plugin_module):
    info = _fixture("elegoo_mqtt/canvas.json")["canvas_info"]
    for tray in info["canvas_list"][0]["tray_list"]:
        tray["tray_id"] += 1

    assert plugin_module.canvas_slots(info) == plugin_module.canvas_slots(
        _fixture("elegoo_mqtt/canvas.json")["canvas_info"]
    )


def test_an_unrecognised_spool_has_no_material(plugin_module):
    data = _fixture("sdcp/canvas_response.json")["Data"]["Data"]
    slots, _complete = plugin_module.canvas_slots(data)

    assert (slots[0]["material"], slots[0]["active_feed"]) == ("PLA", True)
    assert slots[2]["present"] is True and "material" not in slots[2]


# --------------------------------------------------------------------------- #
# Elegoo MQTT readings
# --------------------------------------------------------------------------- #
def test_a_printing_centauri_carbon_2_fills_the_printer_card(plugin_module):
    printer = plugin_module.elegoo_mqtt_printer(_fixture("elegoo_mqtt/status_printing.json"))

    assert printer == {
        "state": "printing",
        "job_name": "cube_4colors.gcode",
        "progress_percent": 42,
        "remaining_seconds": 1890,
        "current_layer": 58,
        "total_layers": 200,
        "nozzle_temperature": 219.8,
        "nozzle_target_temperature": 220.0,
        "bed_temperature": 60.1,
        "bed_target_temperature": 60.0,
        "chamber_temperature": 33.5,
    }


@pytest.mark.parametrize(("status", "sub_status", "expected"), [
    (2, 2502, "paused"),
    (2, 2505, "paused"),
    (2, 2504, "failed"),
    (2, 2077, "finished"),
    (2, 1405, "preparing"),
    (2, 1082, "preparing"),
    (2, 2401, "printing"),
    (15, 0, "paused"),
    (14, 0, "failed"),
    (1, 0, "idle"),
    (5, 0, "unknown"),
])
def test_centauri_carbon_2_states_follow_elegoos_own_table(plugin_module, status, sub_status, expected):
    result = _fixture("elegoo_mqtt/status_printing.json")
    result["machine_status"].update(status=status, sub_status=sub_status)
    printer = plugin_module.elegoo_mqtt_printer(result)

    assert printer["state"] == expected
    assert ("remaining_seconds" in printer) == (expected in {"printing", "paused", "preparing"})


@pytest.mark.parametrize(("provider", "reading", "expected"), [
    # SDCP firmware without multi-colour support is never asked: one spool.
    ("sdcp", {"canvas": None, "canvas_asked": False}, ([255], True)),
    # Asked, and the printer did not answer in time: nothing is claimed.
    ("sdcp", {"canvas": None, "canvas_asked": True}, ([], False)),
    ("sdcp", {"canvas": {"canvas_list": []}, "canvas_asked": True}, ([255], True)),
    ("elegoo_mqtt", {"canvas": None, "mono": None}, ([], False)),
    ("elegoo_mqtt", {"canvas": {"canvas_list": []}, "mono": None}, ([255], True)),
])
def test_without_canvas_the_printer_feeds_its_own_spool(plugin_module, provider, reading, expected):
    reading = dict(reading, status=(
        _status("sdcp/status_idle.json") if provider == "sdcp" else _fixture("elegoo_mqtt/status_printing.json")
    ))
    _printer, slots, complete = plugin_module.profile_lan_observation(provider, reading)

    assert ([slot["provider_index"] for slot in slots], complete) == expected


@pytest.fixture
def edge_providers(monkeypatch):
    """FH Edge's readers of the same protocols, imported from its source tree."""
    import importlib
    import sys

    monkeypatch.syspath_prepend(str(PLUGIN_ROOT.parent / "edge-agent" / "src"))
    for name in [name for name in sys.modules if name.startswith("filamenthub_edge")]:
        monkeypatch.delitem(sys.modules, name)
    return SimpleNamespace(
        sdcp=importlib.import_module("filamenthub_edge.providers.sdcp"),
        mqtt=importlib.import_module("filamenthub_edge.providers.elegoo_mqtt"),
        canvas=importlib.import_module("filamenthub_edge.providers._canvas"),
    )


def _states(status, edits):
    for machine, code in edits:
        changed = json.loads(json.dumps(status))
        changed["CurrentStatus"] = machine
        changed["PrintInfo"]["Status"] = code
        yield changed


def test_the_plugin_and_edge_read_the_shared_fixtures_alike(plugin_module, edge_providers):
    """One printer must look the same on the site whichever of the two reads it."""
    sdcp_statuses = [_status("sdcp/status_idle.json"), _status("sdcp/status_printing.json")]
    sdcp_statuses += list(_states(_status("sdcp/status_printing.json"), [
        ([1], code) for code in range(0, 30)
    ]))
    sdcp_statuses += list(_states(_status("sdcp/status_printing.json"), [
        ([2, 1], 13), ([2], 0), ([9], 1), ([0], 0), ([], 0),
    ]))
    for status in sdcp_statuses:
        assert plugin_module.sdcp_printer(status) == edge_providers.sdcp.build_printer(status)

    cc2 = _fixture("elegoo_mqtt/status_printing.json")
    for code, sub_status in [(1, 0), (2, 2075), (2, 2501), (2, 2077), (14, 0), (15, 0), (3, 0)]:
        changed = json.loads(json.dumps(cc2))
        changed["machine_status"].update(status=code, sub_status=sub_status)
        assert plugin_module.elegoo_mqtt_printer(changed) == edge_providers.mqtt.build_printer(changed)

    for info in (
        _fixture("elegoo_mqtt/canvas.json")["canvas_info"],
        _fixture("sdcp/canvas_response.json")["Data"]["Data"],
        {"canvas_list": []},
        None,
    ):
        assert plugin_module.canvas_slots(info) == edge_providers.canvas.canvas_slots(info)
    mono = _fixture("elegoo_mqtt/mono_filament.json")["mono_filament_info"]
    for value in (mono, None):
        assert plugin_module.canvas_single_spool(value) == edge_providers.canvas.single_spool(value)


def test_the_single_spool_says_the_material_set_on_the_printer(plugin_module):
    reading = {
        "status": _fixture("elegoo_mqtt/status_printing.json"),
        "canvas": {"canvas_list": [{"canvas_id": 0, "connected": 0, "tray_list": []}]},
        "mono": _fixture("elegoo_mqtt/mono_filament.json")["mono_filament_info"],
    }

    _printer, slots, complete = plugin_module.profile_lan_observation("elegoo_mqtt", reading)

    assert complete is True
    assert slots == [{
        "provider_index": 255, "label": "Spool holder", "kind": "external", "present": None,
        "spool_identity_known": False, "material": "PLA", "color_hex": "FFD400",
    }]


# --------------------------------------------------------------------------- #
# OrcaSlicer profiles and the setup list
# --------------------------------------------------------------------------- #
def test_connections_come_from_the_presets_a_protocol_can_reach(plugin_module, monkeypatch):
    def preset(name, user, **config):
        return SimpleNamespace(
            name=name, is_user=lambda: user, config_value=lambda key: config.get(key)
        )

    presets = [
        preset("CC 0.4", True, host_type="elegoolink", printer_model="Elegoo Centauri Carbon",
               print_host="http://192.168.1.139"),
        preset("CC2 0.4", True, host_type="elegoolink", printer_model="Elegoo Centauri Carbon 2",
               print_host="192.168.1.140", printhost_apikey=""),
        preset("CC as Moonraker", True, host_type="moonraker",
               printer_model="Elegoo Centauri Carbon", print_host="192.168.1.143"),
        preset("Neptune 4", True, host_type="moonraker", printer_model="Elegoo Neptune 4",
               print_host="192.168.1.141"),
        preset("CC stock", False, host_type="elegoolink", printer_model="Elegoo Centauri Carbon",
               print_host="192.168.1.142"),
    ]
    printers = SimpleNamespace(size=lambda: len(presets), preset=lambda index: presets[index])
    set_host_attr(
        monkeypatch, plugin_module.orca.host, "preset_bundle",
        lambda: SimpleNamespace(printers=printers),
    )

    assert plugin_module._snapshot_profile_lan_connections() == {
        "sdcp": [
            {"label": "CC 0.4", "host": "192.168.1.139", "route": "known"},
            {"label": "CC as Moonraker", "host": "192.168.1.143", "route": "probe"},
        ],
        "elegoo_mqtt": [
            {"label": "CC2 0.4", "host": "192.168.1.140", "access_code": "123456"},
        ],
    }


def test_adding_a_printer_offers_what_answers_sdcp(setup_flow, monkeypatch):
    plugin, catalog, _context, results, _uploads = setup_flow
    probed = []

    def probe(connection, probe=False):
        probed.append((connection["host"], probe))
        if connection["host"] == "192.168.1.150":
            return {"device_id": MAINBOARD_ID}, None
        return None, "unreachable"

    monkeypatch.setattr(plugin, "read_sdcp", probe)
    snapshot = {
        "sdcp": [
            _sdcp(), _sdcp(),
            # Set up as Moonraker but speaking SDCP, and one that does not.
            _sdcp("192.168.1.150", "probe"), _sdcp("192.168.1.151", "probe"),
        ],
        "elegoo_mqtt": [_mqtt()],
    }

    catalog._do_printer_setup(
        {"operation": "list", "requestId": "list", "profile_lan": snapshot}, "token", []
    )

    offered = [
        (item["provider"], item["label"]) for item in results[-1]["candidates"]
        if item["provider"] in ("sdcp", "elegoo_mqtt")
    ]
    # Nozzle variants of one printer are offered once; a known model is not probed.
    assert offered == [("sdcp", _sdcp()["label"])] * 2 + [("elegoo_mqtt", _mqtt()["label"])]
    assert sorted(probed) == [("192.168.1.150", True), ("192.168.1.151", True)]
    assert "192.168" not in json.dumps(results[-1]["candidates"])


# --------------------------------------------------------------------------- #
# The wire: only read commands reach the printer
# --------------------------------------------------------------------------- #
def _server_ws_frame(payload, opcode=1):
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    if len(data) < 126:
        return struct.pack("!BB", 0x80 | opcode, len(data)) + data
    return struct.pack("!BBH", 0x80 | opcode, 126, len(data)) + data


class _FakeSdcpPrinter:
    """A socket that answers like a Centauri Carbon on V1.4.49."""

    def __init__(self, plugin, firmware="V1.4.49", canvas=True):
        self.plugin = plugin
        self.attributes = _fixture("sdcp/attributes.json")
        self.attributes["Attributes"]["FirmwareVersion"] = firmware
        self.canvas = canvas
        self.incoming = b""
        self.outgoing = []
        self.requests = []
        self.path = None
        self.closed = False

    def settimeout(self, _seconds):
        pass

    def connect(self, _address):
        pass

    def close(self):
        self.closed = True

    def sendall(self, data):
        if self.path is None:
            self.path = data.split(b" ", 2)[1].decode("ascii")
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
            )
            return
        self.incoming += data
        frames, self.incoming = self.plugin.creality_ws_frames(self.incoming)
        for _final, opcode, payload in frames:
            if opcode != 1:
                continue
            request = json.loads(payload.decode("utf-8"))
            self.requests.append(request["Data"])
            command = request["Data"]["Cmd"]
            if command == 1:
                self.outgoing.append(_server_ws_frame(json.dumps(self.attributes)))
            elif command == 0:
                self.outgoing.append(_server_ws_frame(json.dumps(_fixture("sdcp/status_printing.json"))))
            elif command == 324 and self.canvas:
                answer = _fixture("sdcp/canvas_response.json")
                answer["Data"]["RequestID"] = request["Data"]["RequestID"]
                self.outgoing.append(_server_ws_frame(json.dumps(answer)))

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
    monkeypatch.setattr(plugin, "PROFILE_LAN_REPLY_SECONDS", 0.3)
    monkeypatch.setattr(plugin, "PROFILE_LAN_READ_TIMEOUT", 2.0)

    def use(printer):
        monkeypatch.setattr(plugin.socket, "socket", lambda *_args: printer)
        return printer

    return plugin, use


def test_an_sdcp_printer_is_asked_only_to_read(wire):
    plugin, use = wire
    printer = use(_FakeSdcpPrinter(plugin))

    reading, failure = plugin.read_sdcp(_sdcp())

    assert failure is None and reading["device_id"] == MAINBOARD_ID
    assert reading["status"]["PrintInfo"]["Filename"] == "/local/benchy_PLA.gcode"
    assert printer.path == "/websocket"
    # An unknown command can stop a print: attributes, status and the CANVAS slots only.
    assert [request["Cmd"] for request in printer.requests] == [1, 0, 324]
    assert all(request["Data"] == {} and request["From"] == 1 for request in printer.requests)
    assert printer.requests[2]["MainboardID"] == MAINBOARD_ID
    assert printer.closed is True
    _printer, slots, complete = plugin.profile_lan_observation("sdcp", reading)
    assert complete is True and [slot["provider_index"] for slot in slots] == [0, 1, 2, 3]


def test_older_firmware_is_not_asked_about_canvas(wire):
    plugin, use = wire
    printer = use(_FakeSdcpPrinter(plugin, firmware="V1.1.3"))

    reading, failure = plugin.read_sdcp(_sdcp())

    assert failure is None
    assert [request["Cmd"] for request in printer.requests] == [1, 0]
    _printer, slots, _complete = plugin.profile_lan_observation("sdcp", reading)
    assert [slot["provider_index"] for slot in slots] == [255]


def test_a_probe_asks_only_for_the_attributes(wire):
    plugin, use = wire
    printer = use(_FakeSdcpPrinter(plugin))

    reading, failure = plugin.read_sdcp(_sdcp(route="probe"), probe=True)

    assert failure is None and reading["device_id"] == MAINBOARD_ID
    assert [request["Cmd"] for request in printer.requests] == [1]


def test_something_else_at_the_address_is_not_taken_for_an_sdcp_printer(wire):
    plugin, use = wire
    stranger = _FakeSdcpPrinter(plugin)
    stranger.sendall = lambda data: stranger.outgoing.append(b"HTTP/1.1 200 OK\r\n\r\n")
    use(stranger)

    assert plugin.read_sdcp(_sdcp()) == (None, "invalid")


class _FakeBroker:
    """A socket that answers like a Centauri Carbon 2's MQTT broker."""

    def __init__(self, access_code=ACCESS_CODE, canvas="elegoo_mqtt/canvas.json", register="ok"):
        self.access_code = access_code
        self.canvas = _fixture(canvas)
        self.register = register
        self.incoming = b""
        self.outgoing = bytearray()
        self.login = None
        self.subscribed = []
        self.published = []
        self.disconnected = False
        self.closed = False

    def settimeout(self, _seconds):
        pass

    def connect(self, _address):
        pass

    def close(self):
        self.closed = True

    def _publish(self, topic, payload):
        body = struct.pack("!H", len(topic)) + topic.encode("utf-8") + json.dumps(payload).encode()
        self.outgoing += b"\x30" + _length(len(body)) + body

    def sendall(self, data):
        self.incoming += data
        while self.incoming:
            kind, body, self.incoming = _split_packet(self.incoming)
            if kind == 0x10:
                fields = _fields(body[10:])
                self.login = (fields[0], fields[1], fields[2])
                code = 0 if fields[2] == self.access_code else 5
                self.outgoing += bytes([0x20, 2, 0, code])
            elif kind == 0x82:
                self.subscribed = _fields(body[2:], qos=True)
                self.outgoing += bytes([0x90, 2 + len(self.subscribed)]) + body[:2] + bytes(
                    len(self.subscribed)
                )
            elif kind == 0x30:
                size = struct.unpack("!H", body[:2])[0]
                topic = body[2:2 + size].decode("utf-8")
                message = json.loads(body[2 + size:])
                self.published.append((topic, message))
                if topic.endswith("/api_register"):
                    self._publish(
                        topic.replace("api_register", message["request_id"] + "/register_response"),
                        {"client_id": message["client_id"], "error": self.register},
                    )
                elif topic.endswith("/api_request"):
                    result = {
                        1002: _fixture("elegoo_mqtt/status_printing.json"),
                        2005: self.canvas,
                        1061: _fixture("elegoo_mqtt/mono_filament.json"),
                    }[message["method"]]
                    self._publish(
                        topic.replace("api_request", "api_response"),
                        {"id": message["id"], "method": message["method"], "result": result},
                    )
            elif kind == 0xE0:
                self.disconnected = True

    def recv(self, size):
        if not self.outgoing:
            raise TimeoutError("nothing more from the broker")
        chunk = bytes(self.outgoing[:size])
        del self.outgoing[:size]
        return chunk


def _length(value):
    encoded = bytearray()
    while True:
        digit, value = value & 0x7F, value >> 7
        encoded.append(digit | (0x80 if value else 0))
        if not value:
            return bytes(encoded)


def _split_packet(data):
    length, multiplier, offset = 0, 1, 1
    while True:
        digit = data[offset]
        offset += 1
        length += (digit & 0x7F) * multiplier
        multiplier *= 128
        if not digit & 0x80:
            break
    return data[0], data[offset:offset + length], data[offset + length:]


def _fields(data, qos=False):
    fields = []
    while data:
        size = struct.unpack("!H", data[:2])[0]
        fields.append(data[2:2 + size].decode("utf-8"))
        data = data[2 + size + (1 if qos else 0):]
    return fields


@pytest.fixture
def mqtt_wire(wire, monkeypatch):
    plugin, use = wire
    asked = []

    def system_info(connection, _sockaddr):
        asked.append(connection["access_code"])
        return SERIAL, None

    monkeypatch.setattr(plugin, "read_elegoo_mqtt_serial", system_info)
    return plugin, use, asked


def test_a_centauri_carbon_2_is_read_after_registering_with_its_access_code(mqtt_wire):
    plugin, use, asked = mqtt_wire
    broker = use(_FakeBroker())

    reading, failure = plugin.read_elegoo_mqtt(_mqtt())

    assert failure is None and asked == [ACCESS_CODE]
    client, user, password = broker.login
    assert (user, password) == ("elegoo", ACCESS_CODE) and client.startswith("1_PC_")
    assert broker.subscribed == [
        "elegoo/%s/%s_req/register_response" % (SERIAL, client),
        "elegoo/%s/%s/api_response" % (SERIAL, client),
    ]
    assert broker.published[0][1] == {"client_id": client, "request_id": client + "_req"}
    # Registration, then reads only: status and the CANVAS slots.
    assert [message.get("method") for _topic, message in broker.published[1:]] == [1002, 2005]
    assert broker.disconnected is True and broker.closed is True
    assert reading["device_id"] == SERIAL
    _printer, slots, complete = plugin.profile_lan_observation("elegoo_mqtt", reading)
    assert complete is True and len(slots) == 4
    # The next reading registers the same client again, as Elegoo's library does.
    again = use(_FakeBroker())
    assert plugin.read_elegoo_mqtt(_mqtt())[1] is None
    assert again.login[0] == client


def test_without_canvas_the_centauri_carbon_2_is_asked_for_its_single_spool(mqtt_wire):
    plugin, use, _asked = mqtt_wire
    broker = _FakeBroker()
    broker.canvas["canvas_info"]["canvas_list"][0]["connected"] = 0
    use(broker)

    reading, failure = plugin.read_elegoo_mqtt(_mqtt())

    assert failure is None
    assert [message.get("method") for _topic, message in broker.published[1:]] == [
        1002, 2005, 1061,
    ]
    assert reading["mono"]["filament_type"] == "PLA"


@pytest.mark.parametrize(("broker", "expected"), [
    (lambda: _FakeBroker(access_code="000000"), "auth"),
    (lambda: _FakeBroker(register="too many clients"), "busy"),
])
def test_a_refusing_centauri_carbon_2_says_why(mqtt_wire, broker, expected):
    plugin, use, _asked = mqtt_wire
    use(broker())

    assert plugin.read_elegoo_mqtt(_mqtt()) == (None, expected)


def test_an_unusable_access_code_is_not_sent_anywhere(mqtt_wire):
    plugin, _use, asked = mqtt_wire

    assert plugin.read_elegoo_mqtt(_mqtt(access_code="")) == (None, "access_code")
    assert asked == []


def test_the_serial_number_is_asked_with_the_access_code(plugin_module, monkeypatch):
    seen = {}

    class _Answer:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(_fixture("elegoo_mqtt/system_info.json")).encode("utf-8")

    def urlopen(request, _timeout):
        seen["url"] = request.full_url
        seen["token"] = request.get_header("X-token")
        return _Answer()

    monkeypatch.setattr(plugin_module, "_urlopen_authorized", urlopen)

    assert plugin_module.read_elegoo_mqtt_serial(_mqtt(), ("192.168.1.140", 80)) == (SERIAL, None)
    assert seen == {
        "url": "http://192.168.1.140:80/system/info?X-Token=%s" % ACCESS_CODE, "token": ACCESS_CODE,
    }
    # The code is a credential: it is not passed on to another host after a redirect.
    assert "x-token" in plugin_module._CREDENTIAL_HEADERS


# --------------------------------------------------------------------------- #
# Linking a printer to its card
# --------------------------------------------------------------------------- #
@pytest.fixture(params=["sdcp", "elegoo_mqtt"])
def linked(request, plugin_module, monkeypatch, tmp_path):
    """A linked printer of each protocol whose readings are set by hand."""
    plugin = plugin_module
    provider = request.param
    device_id = MAINBOARD_ID if provider == "sdcp" else SERIAL
    connection = _sdcp() if provider == "sdcp" else _mqtt()
    calls = SimpleNamespace(posted=[], revoked=[], device_id=device_id, failure=None)
    monkeypatch.setattr(plugin, "SDCP_CONFIG_FILE", str(tmp_path / ".fh_sdcp.json"))
    monkeypatch.setattr(plugin, "ELEGOO_MQTT_CONFIG_FILE", str(tmp_path / ".fh_elegoo_mqtt.json"))
    monkeypatch.setattr(plugin, "_PROFILE_LAN_KNOWN_HOSTS", {})
    monkeypatch.setattr(plugin, "plugin_source_instance_id", lambda: "desktop-source-instance")

    def status(kind, _connection):
        assert kind == provider
        if calls.failure:
            return None, calls.failure
        if provider == "sdcp":
            canvas = _fixture("sdcp/canvas_response.json")["Data"]["Data"]
            return {
                "device_id": calls.device_id, "status": _status("sdcp/status_printing.json"),
                "canvas": canvas, "canvas_asked": True,
            }, None
        return {
            "device_id": calls.device_id, "status": _fixture("elegoo_mqtt/status_printing.json"),
            "canvas": _fixture("elegoo_mqtt/canvas.json")["canvas_info"], "canvas_asked": True, "mono": None,
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

    monkeypatch.setattr(plugin, "read_profile_lan_status", status)
    monkeypatch.setattr(plugin, "http_post_json", pair)
    monkeypatch.setattr(plugin, "http_post_bridge_json", post)
    monkeypatch.setattr(plugin, "revoke_fresh_bridge_token", calls.revoked.append)

    result = plugin.configure_profile_lan_bridge(provider, 7, 9, "FH-AAAAA-BBBBB", "", [connection])
    assert result == {"ok": True, "code": "ok"}
    stored = Path(plugin.SDCP_CONFIG_FILE if provider == "sdcp" else plugin.ELEGOO_MQTT_CONFIG_FILE)
    return SimpleNamespace(
        plugin=plugin, provider=provider, connection=connection, calls=calls, stored=stored,
    )


def test_linking_reports_the_printer_and_keeps_no_address_or_access_code(linked):
    path, _token, snapshot = linked.calls.posted[0]

    assert path == "/printer-bridge/snapshot"
    assert (linked.calls.pair["provider"], linked.calls.pair["capabilities"]) == (
        linked.provider, ["read", "presence"],
    )
    assert (snapshot["provider"], snapshot["transport"]) == (linked.provider, "orca_plugin_lan")
    assert snapshot["printer"]["state"] == "printing"
    assert len(snapshot["slots"]) == 4 and snapshot["slot_topology_complete"] is True
    identity = snapshot["device_identity"]
    assert identity["kind"] == ("sdcp_mainboard" if linked.provider == "sdcp" else "elegoo_serial")
    assert len(identity["token"]) == 64
    stored = linked.stored.read_text(encoding="utf-8")
    assert linked.calls.device_id in stored
    assert linked.connection["host"] not in stored and ACCESS_CODE not in stored


def test_a_refresh_reports_the_linked_printer_again(linked):
    linked.calls.posted.clear()

    assert linked.plugin.observe_profile_lan_bindings(
        linked.provider, [linked.connection], 7, 9
    ) == {7: "ok"}
    assert [path for path, _token, _payload in linked.calls.posted] == ["/printer-bridge/snapshot"]


def test_another_printer_that_took_the_address_is_not_reported(linked):
    linked.calls.posted.clear()
    linked.calls.device_id = "ffffffffffffffff" if linked.provider == "sdcp" else "CC2FFFFFFFFFFF"

    assert linked.plugin.observe_profile_lan_bindings(
        linked.provider, [linked.connection], 7, 9
    ) == {7: "credentials"}
    # The site only hears that the printer did not answer.
    assert [path for path, _token, _payload in linked.calls.posted] == ["/printer-bridge/heartbeat"]


def test_a_link_the_site_revoked_is_dropped(linked, monkeypatch):
    monkeypatch.setattr(linked.plugin, "http_post_bridge_json", lambda *_args: (401, b"", None))

    assert linked.plugin.observe_profile_lan_bindings(
        linked.provider, [linked.connection], 7, 9
    ) == {7: "unpaired"}
    assert linked.plugin._load_profile_lan_bindings(linked.provider) == []
