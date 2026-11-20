"""Prevent unsafe async map application and false refresh acknowledgement."""

from __future__ import annotations

import ast
import configparser
import hashlib
import shlex
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import jinja2
import pytest

from filamenthub_edge.providers.moonraker import MoonrakerProvider
from filamenthub_edge.refresh import map_matches, refresh_happy_hare

IDENTITY = ("moonraker_instance", "ab" * 16)
TARGET = {
    "revision": "ab" * 32, "physical_printer_id": 10, "material_system_id": 20,
    "inventory_key_digest": hashlib.sha256(b"printer-key").hexdigest(),
    "printer_hostname": "voron", "gates": [{
        "index": 0, "spool_id": 12, "name": "PLA", "material": "PLA", "vendor": "Brand",
        "color": "aabbcc", "temperature": 180, "initial_weight": 1000, "rfids": "04AB,04CD",
    }],
}


def status():
    return {
        "mmu": {"enabled": True, "spoolman_support": "pull", "print_state": "standby",
                "is_paused": False,
                "num_gates": 1, "gate_spool_id": [12], "gate_filament_name": ["PLA"],
                "gate_material": ["PLA"], "gate_vendor": ["Brand"], "gate_color": ["aabbcc"],
                "gate_temperature": [200], "gate_initial_weight": [1000]},
        "print_stats": {"state": "standby"}, "pause_resume": {"is_paused": False},
        "idle_timeout": {"state": "Ready"},
        "gcode_macro FH_EDGE_REFRESH": {"guard_version": 1, "applied": 0, "requested": 0,
                                       "deferred": 0, "last_map": ""},
        "gcode_macro MMU_GATE_MAP": {"guard_version": 1},
        "configfile": {"settings": {"mmu": {"default_extruder_temp": "200"},
                                    "gcode_macro mmu_gate_map": {
                                        "rename_existing": "_FH_ORIGINAL_MMU_GATE_MAP"}}},
    }


class Http:
    def __init__(self):
        self.status = status()
        self.commands = []
        self.hostname = "voron"
        self.key = "printer-key"
        self.requests = []

    def request(self, method, path, **kwargs):
        self.requests.append((path, deepcopy(kwargs)))
        if path == "/server/config":
            data = {"config": {"spoolman": {
                "server": "https://filamenthub.ru/api/v1/spool_compat/" + self.key}}}
        elif path == "/printer/info":
            data = {"hostname": self.hostname}
        elif "database" in path:
            data = {"value": IDENTITY[1]}
        elif path == "/printer/objects/query":
            data = {"status": deepcopy(self.status)}
        else:
            self.commands.append(kwargs["payload"]["script"])
            data = "ok"
        return 200, {"result": data}, {}


def provider(*, auto_refresh=True):
    http = Http()
    return MoonrakerProvider("http://printer", api_key=None, material_provider="happy_hare",
                             timeout=2, http_client=http, auto_refresh=auto_refresh), http


def test_false_http_success_retains_pending_then_ack_stops_commands():
    p, http = provider()
    assert refresh_happy_hare(p, TARGET, IDENTITY) == "pending:verification"
    assert refresh_happy_hare(p, TARGET, IDENTITY) == "pending:verification"
    assert http.commands == ["FH_EDGE_REFRESH"]
    http.status["gcode_macro FH_EDGE_REFRESH"]["last_map"] = repr({0: {
        "spool_id": 12, "rfids": "04CD,04AB"}})
    assert refresh_happy_hare(p, TARGET, IDENTITY) == "applied"
    assert refresh_happy_hare(p, TARGET, IDENTITY) == "applied"
    assert http.commands == ["FH_EDGE_REFRESH"]
    # A restarted provider re-verifies the map; persisted success is unnecessary.
    restarted, _ = provider()
    restarted.http = http
    assert refresh_happy_hare(restarted, TARGET, IDENTITY) == "applied"
    http.status["mmu"]["gate_material"] = ["PETG"]
    assert not map_matches(TARGET, http.status, 200)


@pytest.mark.parametrize("object_name,key,value,reason", [
    ("print_stats", "state", "printing", "deferred"),
    ("print_stats", "state", "paused", "deferred"),
    ("print_stats", "state", "unknown", "deferred"),
    ("pause_resume", "is_paused", True, "deferred"),
    ("idle_timeout", "state", "Printing", "deferred"),
    ("idle_timeout", "state", "unknown", "deferred"),
    ("mmu", "spoolman_support", "push", "blocked"),
    ("gcode_macro FH_EDGE_REFRESH", "guard_version", 0, "blocked"),
    ("gcode_macro MMU_GATE_MAP", "guard_version", 0, "blocked"),
])
def test_busy_unknown_push_and_missing_guard_never_send(object_name, key, value, reason):
    p, http = provider()
    http.status[object_name][key] = value
    assert refresh_happy_hare(p, TARGET, IDENTITY).startswith(reason)
    assert not http.commands


def test_fresh_identity_foreign_key_and_hostname_fail_closed():
    for mutate in (lambda h: setattr(h, "key", "foreign"),
                   lambda h: setattr(h, "hostname", "other")):
        p, http = provider()
        mutate(http)
        assert refresh_happy_hare(p, TARGET, IDENTITY).startswith("blocked")
        assert not http.commands
    p, http = provider()
    p._identity = IDENTITY  # Even a recent cache is not trusted for commands.
    with patch.object(p, "_device_identity", return_value=None):
        assert refresh_happy_hare(p, TARGET, IDENTITY) == "blocked:printer_identity"
    assert not http.commands


@pytest.mark.parametrize("field,value", [
    ("gate_initial_weight", None), ("gate_spool_id", [True]),
    ("gate_spool_id", []), ("gate_filament_name", [42]),
    ("gate_material", "PLA"), ("gate_vendor", None),
    ("gate_color", [None]), ("gate_temperature", [float("nan")]),
    ("num_gates", 2), ("num_gates", True),
])
def test_incomplete_provider_prerequisites_block_without_command(field, value):
    p, http = provider()
    if value is None:
        del http.status["mmu"][field]
    else:
        http.status["mmu"][field] = value
    assert refresh_happy_hare(p, TARGET, IDENTITY) == "blocked:incomplete_map_fields"
    assert not http.commands
    assert "local_command" not in p.capabilities()


@pytest.mark.parametrize("value", [None, "invalid", float("nan"), True, 0])
def test_missing_or_malformed_default_temperature_blocks_without_command(value):
    p, http = provider()
    http.status["configfile"]["settings"]["mmu"]["default_extruder_temp"] = value
    assert refresh_happy_hare(p, TARGET, IDENTITY).startswith("blocked:")
    assert not http.commands
    assert "local_command" not in p.capabilities()


def test_capability_requires_opt_in_and_verified_prerequisites():
    off, http = provider(auto_refresh=False)
    off.set_refresh_ready(True)
    assert "local_command" not in off.capabilities()
    assert refresh_happy_hare(off, TARGET, IDENTITY) == "blocked:unsupported_provider"
    assert not http.commands
    on, http = provider()
    assert "local_command" not in on.capabilities()
    assert refresh_happy_hare(on, TARGET, IDENTITY) == "pending:verification"
    assert "local_command" in on.capabilities()
    http.status["mmu"]["enabled"] = False
    assert refresh_happy_hare(on, TARGET, IDENTITY) == "blocked:mmu_disabled"
    assert "local_command" not in on.capabilities()
    assert http.commands == ["FH_EDGE_REFRESH"]
    # Even a prior recorded callback cannot ACK aliases while MMU is disabled.
    http.status["gcode_macro FH_EDGE_REFRESH"]["last_map"] = repr({0: {
        "spool_id": 12, "rfids": "04AB,04CD"}})
    assert refresh_happy_hare(on, TARGET, IDENTITY) == "blocked:mmu_disabled"


def test_disabled_late_callback_preserves_previous_ack_and_map():
    data = status()
    guard = data["gcode_macro FH_EDGE_REFRESH"]
    guard["applied"] = 8
    guard["last_map"] = "{0: {'spool_id': 1, 'rfids': '04AA'}}"
    assert apply_commands(render("gcode_macro FH_EDGE_REFRESH", data), data) == [
        "MMU_SPOOLMAN REFRESH=1"]
    data["mmu"]["enabled"] = False
    script = render("gcode_macro MMU_GATE_MAP", data,
                    params={"MAP": "{0: {'spool_id': 1, 'rfids': '04BB'}}", "REPLACE": "1",
                            "FROM_SPOOLMAN": "1"}, rawparams="MAP=test")
    assert not apply_commands(script, data)
    assert guard["applied"] == 8
    assert guard["last_map"] == "{0: {'spool_id': 1, 'rfids': '04AA'}}"


def cfg():
    parser = configparser.RawConfigParser()
    parser.read(Path(__file__).parents[1] /
                "src/filamenthub_edge/templates/happy_hare_refresh.cfg", encoding="utf-8")
    return parser


def render(section, data, *, params=None, rawparams=""):
    # Exactly Klipper's Jinja delimiters and extended G-Code shell parser.
    env = jinja2.Environment("{%", "%}", "{", "}")
    values = {"printer": data, "params": params or {}, "rawparams": rawparams,
              "action_respond_info": lambda text: ""}
    values.update(data["gcode_macro FH_EDGE_REFRESH"])
    return env.from_string(cfg()[section]["gcode"]).render(**values)


def apply_commands(script, data):
    forwarded = []
    for line in script.splitlines():
        tokens = shlex.split(line, comments=True, posix=True)
        if not tokens:
            continue
        if tokens[0] == "SET_GCODE_VARIABLE":
            params = dict(token.split("=", 1) for token in tokens[1:])
            value = ast.literal_eval(params["VALUE"])
            data["gcode_macro FH_EDGE_REFRESH"][params["VARIABLE"]] = value
        else:
            forwarded.append(line.strip())
    return forwarded


@pytest.mark.parametrize("phase", ["request", "callback"])
@pytest.mark.parametrize("change", ["printing", "paused", "unknown", "push", "disabled"])
def test_races_are_guarded_at_request_and_async_apply(phase, change):
    data = status()
    if change == "push":
        data["mmu"]["spoolman_support"] = "push"
    elif change == "disabled":
        data["mmu"]["enabled"] = False
    else:
        data["print_stats"]["state"] = change
    if phase == "request":
        script = render("gcode_macro FH_EDGE_REFRESH", data)
    else:
        script = render("gcode_macro MMU_GATE_MAP", data,
                        params={"MAP": "{0: {'spool_id': 12}}", "REPLACE": "1",
                                "FROM_SPOOLMAN": "1"}, rawparams="MAP=test")
    assert not apply_commands(script, data)
    assert data["gcode_macro FH_EDGE_REFRESH"]["deferred"] == 1
    assert data["gcode_macro FH_EDGE_REFRESH"]["applied"] == 0


def test_real_template_serialization_preserves_hostile_map_and_other_forms():
    data = status()
    native = repr({0: {"spool_id": 12, "rfids": "04AB,04CD",
                       "name": "'double\" \\ ;#\r\n 中文 MMU_GATE_MAP"}})
    raw = "MAP=" + shlex.quote(native) + " REPLACE=1 FROM_SPOOLMAN=1"
    script = render("gcode_macro MMU_GATE_MAP", data,
                    params={"MAP": native, "REPLACE": "1", "FROM_SPOOLMAN": "1"}, rawparams=raw)
    forwarded = apply_commands(script, data)
    assert forwarded == ["_FH_ORIGINAL_MMU_GATE_MAP " + raw]
    assert data["gcode_macro FH_EDGE_REFRESH"]["last_map"] == native
    assert data["gcode_macro FH_EDGE_REFRESH"]["applied"] == 1
    assert ast.literal_eval(native)[0]["name"].endswith("MMU_GATE_MAP")
    data["print_stats"]["state"] = "printing"
    for params, raw in [({"RFID": "04AB", "GATE": "0"}, "GATE=0 RFID=04AB"),
                        ({"BYPASS": "1"}, "BYPASS=1"),
                        ({"MAP": "{}", "REPLACE": "0"}, "MAP='{}' REPLACE=0")]:
        assert apply_commands(render("gcode_macro MMU_GATE_MAP", data, params=params,
                                     rawparams=raw), data) == ["_FH_ORIGINAL_MMU_GATE_MAP " + raw]


def test_runtime_durable_latest_target_cloud_freshness_and_binding(tmp_path):
    from test_runtime import EdgeRuntimeTest, FakeCloud

    from filamenthub_edge.cloud import DesiredResult
    from filamenthub_edge.errors import AuthenticationError, HttpRequestError
    from filamenthub_edge.runtime import EdgeRuntime
    from filamenthub_edge.state import StateStore

    class Cloud(FakeCloud):
        target = deepcopy(TARGET)
        error = None
        unchanged = False

        def desired_snapshot(self, **kwargs):
            if self.error:
                raise self.error
            return DesiredResult(not self.unchanged, '"etag"', {
                "physical_printer_id": 10, "material_system_id": 20,
                "slots": [], "happy_hare_refresh": deepcopy(self.target),
            })

    store = StateStore(tmp_path / "state.json")
    config = replace(EdgeRuntimeTest()._config(store.path), auto_refresh=True)
    p, http = provider()
    cloud = Cloud()
    cloud.fail_upload = False
    state = store.load()
    state.bridge_token = "fhpb_fixture"
    state.physical_printer_id, state.material_system_id = 10, 20
    state.printer_discovery_key = "ab" * 32
    runtime = EdgeRuntime(config=config, provider=p, cloud=cloud, store=store, state=state)
    with patch("filamenthub_edge.runtime.refresh_happy_hare", return_value="deferred:busy") as act:
        runtime.run_cycle()
        assert store.load().pending_refresh["revision"] == TARGET["revision"]
        assert act.call_count == 1
        cloud.target["revision"] = "cd" * 32
        runtime.run_cycle()
        assert store.load().pending_refresh["revision"] == "cd" * 32
        cloud.error = HttpRequestError("offline")
        with pytest.raises(HttpRequestError):
            runtime.run_cycle()
        assert act.call_count == 2
        assert store.load().refresh_reason == "cloud_unavailable"
        cloud.error = AuthenticationError("revoked")
        with pytest.raises(AuthenticationError):
            runtime.run_cycle()
        assert act.call_count == 2
        cloud.error = None
        cloud.unchanged = True
        runtime = EdgeRuntime(config=config, provider=p, cloud=cloud,
                              store=store, state=store.load())
        act.return_value = "applied"
        p.set_refresh_ready(True)
        runtime.run_cycle()
        assert act.call_count == 3
        assert store.load().applied_refresh_revision == "cd" * 32
        assert store.load().pending_refresh is None
        # Ordinary desired pulls + observations continue, extra refresh preflight stops.
        http.requests.clear()
        runtime.run_cycle()
        assert act.call_count == 3
        assert not any(path == "/printer/info" for path, _ in http.requests)
        queries = [request.get("payload", {}).get("objects", {}) for _, request in http.requests]
        assert not any("gcode_macro FH_EDGE_REFRESH" in query for query in queries)
        cloud.unchanged = False
        cloud.target["physical_printer_id"] = 999
        runtime.run_cycle()
        assert act.call_count == 3
        assert store.load().refresh_reason == "binding_mismatch"
