import logging
from pathlib import Path

import octoprint_filamenthub_bridge
from octoprint.events import Events
from octoprint_filamenthub_bridge import (
    BridgeRequestError,
    CAPABILITIES,
    RETRY_MAX_SECONDS,
    STARTUP_JITTER_MAX_SECONDS,
    USAGE_CHECKPOINT_INTERVAL_SECONDS,
    FilamentHubBridgePlugin,
    _retry_delay,
)


def test_declares_only_capabilities_the_bridge_actually_provides():
    assert CAPABILITIES == ["read", "write", "spool_identity", "consumption"]


class FakeSettings:
    def __init__(self):
        self.save_count = 0
        self.values = {
            "server_url": "https://filamenthub.ru",
            "bridge_token": "existing-token",
            "instance_id": "existing-instance",
            "snapshot": {
                "slots": [
                    {
                        "material_slot_id": 17,
                        "index": 0,
                        "assignment_revision": 3,
                        "spool": {"id": 41},
                    }
                ]
            },
            "active_slot": 0,
            "map_tools_to_slots": False,
            "tool_slot_map": {},
            "routing_revision": 0,
            "outbox": [],
        }

    def get(self, path):
        return self.values.get(path[0])

    def get_boolean(self, path):
        return bool(self.get(path))

    def set(self, path, value):
        self.values[path[0]] = value

    def set_boolean(self, path, value):
        self.set(path, bool(value))

    def save(self):
        self.save_count += 1


class FakePrinter:
    def get_current_job(self):
        return {"file": {"name": "short.gcode", "path": "short.gcode"}}


class PrintingComm:
    def isPrinting(self):
        return True


class IdleComm:
    def isPrinting(self):
        return False


def test_tool_selected_before_print_seeds_physical_tool_tracking():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._settings.set_boolean(["map_tools_to_slots"], True)
    plugin._settings.set(["tool_slot_map"], {"1": 0})
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")

    plugin.on_gcode_sent(IdleComm(), "sent", "T1", None, "T")
    plugin._begin_print({"name": "physical-tool.gcode"})
    plugin.on_gcode_sent(PrintingComm(), "sent", "M83", None, "M83")
    plugin.on_gcode_sent(PrintingComm(), "sent", "G1 E7", None, "G1")

    assert plugin._selected_tool == 1
    assert plugin._tracker.active_tool == 1
    assert plugin._tracker.used_length_by_slot == {0: 7.0}


def test_sent_gcode_starts_tracking_before_delayed_print_started_event():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    comm = PrintingComm()

    plugin.on_gcode_sent(comm, "sent", "M82", None, "M82")
    plugin.on_gcode_sent(comm, "sent", "G92 E0", None, "G92")
    plugin.on_gcode_sent(comm, "sent", "G1 X1 E200", None, "G1")

    assert plugin._tracker.used_length_by_slot == {0: 200.0}

    # OctoPrint dispatches PrintStarted asynchronously. It must not erase the
    # commands already observed by the synchronous sent-G-code hook.
    plugin._begin_print({"name": "short.gcode"})
    assert plugin._tracker.used_length_by_slot == {0: 200.0}

    plugin._finish_print("completed", {"time": 1.0})
    outbox = plugin._settings.get(["outbox"])
    assert len(outbox) == 1
    assert outbox[0]["event_type"] == "terminal"
    assert outbox[0]["reasons"] == ["terminal"]
    assert outbox[0]["items"] == [
        {"slot_index": 0, "spool_id": 41, "used_length_mm": 200.0}
    ]


def test_print_cancelled_queues_usage_as_cancelled():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    comm = PrintingComm()

    plugin.on_gcode_sent(comm, "sent", "M83", None, "M83")
    plugin.on_gcode_sent(comm, "sent", "G1 E12", None, "G1")
    plugin.on_event(Events.PRINT_CANCELLED, {"time": 3.0})

    outbox = plugin._settings.get(["outbox"])
    assert len(outbox) == 1
    assert outbox[0]["event_type"] == "terminal"
    assert outbox[0]["outcome"] == "cancelled"
    assert outbox[0]["items"][0]["used_length_mm"] == 12.0


def test_terminal_event_closes_a_print_even_without_new_usage():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")

    plugin._begin_print({"name": "empty-terminal.gcode"})
    plugin._finish_print("failed", {"time": 2.0})

    outbox = plugin._settings.get(["outbox"])
    assert len(outbox) == 1
    assert outbox[0]["event_type"] == "terminal"
    assert outbox[0]["outcome"] == "failed"
    assert outbox[0]["items"] == []


def test_tool_and_spool_boundaries_keep_exact_spool_identity():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._settings.set(
        ["snapshot"],
        {
            "slots": [
                {"material_slot_id": 17, "index": 0, "spool": {"id": 41}},
                {"material_slot_id": 18, "index": 1, "spool": {"id": 42}},
            ]
        },
    )
    plugin._settings.set_boolean(["map_tools_to_slots"], True)
    plugin._settings.set(["tool_slot_map"], {"0": 0, "1": 1})
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    comm = PrintingComm()

    plugin._begin_print({"name": "two-spools.gcode"})
    plugin.on_gcode_sent(comm, "sent", "M83", None, "M83")
    plugin.on_gcode_sent(comm, "sent", "G1 E10", None, "G1")
    plugin.on_gcode_sent(comm, "sent", "T1", None, "T")
    plugin.on_gcode_sent(comm, "sent", "G1 E5", None, "G1")
    plugin._apply_snapshot(
        {
            "slots": [
                {"material_slot_id": 17, "index": 0, "spool": {"id": 41}},
                {"material_slot_id": 18, "index": 1, "spool": {"id": 99}},
            ]
        },
        '"changed"',
    )

    checkpoint = plugin._settings.get(["outbox"])[0]
    assert checkpoint["event_type"] == "checkpoint"
    assert checkpoint["reasons"] == ["tool_change", "spool_change"]
    assert checkpoint["items"] == [
        {"slot_index": 0, "spool_id": 41, "used_length_mm": 10.0},
        {"slot_index": 1, "spool_id": 42, "used_length_mm": 5.0},
    ]

    plugin.on_gcode_sent(comm, "sent", "G1 E2", None, "G1")
    plugin._finish_print("completed", {"time": 20.0})

    terminal = plugin._settings.get(["outbox"])[1]
    assert terminal["items"] == [
        {"slot_index": 1, "spool_id": 99, "used_length_mm": 2.0}
    ]


def test_filament_change_is_not_mislabeled_as_runout():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    comm = PrintingComm()

    plugin._begin_print({"name": "m600.gcode"})
    plugin.on_gcode_sent(comm, "sent", "M83", None, "M83")
    plugin.on_gcode_sent(comm, "sent", "G1 E8", None, "G1")
    plugin.on_event(Events.FILAMENT_CHANGE, {"gcode": "M600"})

    checkpoint = plugin._settings.get(["outbox"])[0]
    assert checkpoint["reasons"] == ["filament_change"]
    assert "runout" not in checkpoint["reasons"]


def test_frequent_extrusion_waits_for_one_periodic_checkpoint(monkeypatch):
    monotonic_now = [100.0]
    monkeypatch.setattr(
        "octoprint_filamenthub_bridge.time.monotonic",
        lambda: monotonic_now[0],
    )
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    plugin._identifier = "filamenthub_bridge"
    plugin._last_snapshot_monotonic = monotonic_now[0]
    plugin._plugin_manager = type(
        "PluginManager",
        (),
        {"send_plugin_message": lambda *args: None},
    )()
    requests = []

    def request(method, path, payload=None, **kwargs):
        requests.append((method, path, payload))
        return 200, {}, {}

    plugin._request = request
    plugin._begin_print({"name": "storm.gcode"})
    plugin.on_gcode_sent(PrintingComm(), "sent", "M83", None, "M83")
    for _ in range(100):
        plugin.on_gcode_sent(PrintingComm(), "sent", "G1 E2", None, "G1")

    assert requests == []
    assert plugin._settings.get(["outbox"]) == []

    monotonic_now[0] += USAGE_CHECKPOINT_INTERVAL_SECONDS
    assert plugin._sync_once() is True

    usage_requests = [request for request in requests if request[1] == "/usage"]
    assert len(usage_requests) == 1
    assert usage_requests[0][2]["reasons"] == ["periodic"]
    assert usage_requests[0][2]["items"] == [
        {"slot_index": 0, "spool_id": 41, "used_length_mm": 200.0}
    ]
    assert plugin._settings.get(["outbox"]) == []


def test_outbox_flush_preserves_event_appended_during_request():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    first = {"event_id": "first", "items": [{"spool_id": 41}]}
    second = {"event_id": "second", "items": [{"spool_id": 42}]}
    plugin._settings.set(["outbox"], [first])
    sent = []

    def request(method, path, payload):
        sent.append(payload)
        if payload == first:
            current = list(plugin._settings.get(["outbox"]) or [])
            current.append(second)
            plugin._settings.set(["outbox"], current)
        return 200, {}, {"accepted": True}

    plugin._request = request
    plugin._flush_outbox()

    assert sent == [first, second]
    assert plugin._settings.get(["outbox"]) == []


def test_failed_send_seals_event_before_network_and_prevents_mutation():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    comm = PrintingComm()

    plugin._begin_print({"name": "lost-ack.gcode"})
    plugin.on_gcode_sent(comm, "sent", "M83", None, "M83")
    plugin.on_gcode_sent(comm, "sent", "G1 E10", None, "G1")
    plugin._checkpoint_usage("periodic")
    sent = []

    def fail_after_send(method, path, payload):
        sent.append(payload)
        raise RuntimeError("acknowledgement lost")

    plugin._request = fail_after_send
    try:
        plugin._flush_outbox()
    except RuntimeError as exc:
        assert str(exc) == "acknowledgement lost"
    else:
        raise AssertionError("A lost acknowledgement must leave the event pending")

    sealed = plugin._settings.get(["outbox"])[0]
    assert sealed["_sealed"] is True
    assert "_sealed" not in sent[0]
    first_event_id = sealed["event_id"]

    plugin.on_gcode_sent(comm, "sent", "G1 E5", None, "G1")
    plugin._checkpoint_usage("tool_change")

    outbox = plugin._settings.get(["outbox"])
    assert len(outbox) == 2
    assert outbox[0]["event_id"] == first_event_id
    assert outbox[0]["items"][0]["used_length_mm"] == 10.0
    assert outbox[1]["event_id"] != first_event_id
    assert outbox[1]["items"][0]["used_length_mm"] == 5.0


def test_sealed_outbox_event_survives_plugin_recreation_and_replays_once():
    settings = FakeSettings()
    first_plugin = FilamentHubBridgePlugin()
    first_plugin._settings = settings
    first_plugin._printer = FakePrinter()
    first_plugin._logger = logging.getLogger("filamenthub-bridge-test")

    first_plugin._begin_print({"name": "restart.gcode"})
    first_plugin.on_gcode_sent(PrintingComm(), "sent", "M83", None, "M83")
    first_plugin.on_gcode_sent(PrintingComm(), "sent", "G1 E10", None, "G1")
    first_plugin._checkpoint_usage("periodic")

    attempted = []

    def lose_ack(method, path, payload):
        attempted.append(payload)
        raise RuntimeError("acknowledgement lost")

    first_plugin._request = lose_ack
    try:
        first_plugin._flush_outbox()
    except RuntimeError:
        pass
    else:
        raise AssertionError("The first plugin instance must retain the event")

    restarted_plugin = FilamentHubBridgePlugin()
    restarted_plugin._settings = settings
    delivered = []

    def accept(method, path, payload):
        delivered.append(payload)
        return 200, {}, {"accepted": True}

    restarted_plugin._request = accept
    restarted_plugin._flush_outbox()
    restarted_plugin._flush_outbox()

    assert delivered == attempted
    assert settings.get(["outbox"]) == []


def test_public_state_keeps_legacy_current_tool_but_labels_it_as_commanded():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._settings.set_boolean(["map_tools_to_slots"], True)
    plugin._settings.set(["tool_slot_map"], {"7": 0})
    plugin._printing = True
    plugin._tracker.active_tool = 7

    state = plugin._public_state()

    assert state["manual_slot"] == 0
    assert state["active_slot"] == 0
    assert state["commanded_tool"] == 7
    assert state["current_tool"] == 7


def test_manual_public_state_does_not_present_a_stale_tool_command():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._printing = True
    plugin._tracker.active_tool = 7

    state = plugin._public_state()

    assert state["manual_slot"] == 0
    assert state["active_slot"] == 0
    assert state["commanded_tool"] is None
    assert state["current_tool"] is None


def test_failed_pairing_preserves_existing_connection():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")

    def failed_request(*args, **kwargs):
        raise RuntimeError("pairing failed")

    plugin._request = failed_request

    try:
        plugin._pair("https://other.example", "FH-FAILED")
    except RuntimeError as exc:
        assert str(exc) == "pairing failed"
    else:
        raise AssertionError("Pairing must fail in this test")

    assert plugin._settings.get(["server_url"]) == "https://filamenthub.ru"
    assert plugin._settings.get(["bridge_token"]) == "existing-token"
    assert plugin._settings.get(["instance_id"]) == "existing-instance"


def test_successful_pairing_replaces_connection_atomically():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    calls = []

    def successful_request(method, path, payload, **kwargs):
        calls.append((method, path, payload, kwargs))
        return 200, {}, {"bridge_token": "replacement-token"}

    plugin._request = successful_request
    plugin._pair("https://new.example/", "  fh-success  ")

    assert calls[0][2]["pairing_code"] == "FH-SUCCESS"
    assert calls[0][3] == {
        "server_url": "https://new.example",
        "include_token": False,
    }
    assert plugin._settings.get(["server_url"]) == "https://new.example"
    assert plugin._settings.get(["bridge_token"]) == "replacement-token"
    assert plugin._settings.get(["instance_id"]) == "existing-instance"


def test_empty_pairing_code_is_rejected_before_network_request():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    plugin._request = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Empty pairing code must not reach the network")
    )

    try:
        plugin._pair("https://filamenthub.ru", "   ")
    except ValueError as exc:
        assert str(exc) == "Enter the FilamentHub pairing code."
    else:
        raise AssertionError("Empty pairing code must be rejected")


def test_unpair_revokes_remote_connection_before_clearing_local_credentials():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    calls = []

    def successful_request(method, path):
        calls.append((method, path))
        return 204, {}, None

    plugin._request = successful_request
    plugin._unpair()

    assert calls == [("DELETE", "/connection")]
    assert plugin._settings.get(["bridge_token"]) is None
    assert plugin._settings.get(["snapshot"]) == {}
    assert plugin._settings.get(["active_slot"]) is None
    assert plugin._settings.get(["map_tools_to_slots"]) is False
    assert plugin._settings.get(["tool_slot_map"]) == {}
    assert plugin._settings.get(["routing_revision"]) == 0


def test_failed_remote_revocation_preserves_local_connection():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    plugin._request = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("server unavailable")
    )

    try:
        plugin._unpair()
    except RuntimeError as exc:
        assert str(exc) == "server unavailable"
    else:
        raise AssertionError("A failed remote revocation must fail the command")

    assert plugin._settings.get(["bridge_token"]) == "existing-token"
    assert plugin._settings.get(["snapshot"]) is not None
    assert plugin._settings.get(["active_slot"]) == 0


def test_retry_delay_grows_but_stays_bounded(monkeypatch):
    monkeypatch.setattr(
        "octoprint_filamenthub_bridge.random.uniform",
        lambda low, high: high,
    )

    assert _retry_delay(1, None) == 6.0
    assert _retry_delay(2, 30.0) == 30.0
    assert _retry_delay(20, 600.0) == RETRY_MAX_SECONDS


def test_worker_spreads_first_automatic_contact(monkeypatch):
    plugin = FilamentHubBridgePlugin()
    waits = []

    class WakeEvent:
        def wait(self, timeout):
            waits.append(timeout)
            plugin._stop_worker.set()
            return False

        def clear(self):
            return None

    plugin._wake_worker = WakeEvent()
    monkeypatch.setattr(
        "octoprint_filamenthub_bridge.random.uniform",
        lambda low, high: high,
    )

    plugin._worker_loop()

    assert waits == [STARTUP_JITTER_MAX_SECONDS]


def test_plugin_registers_shared_tab_and_sidebar_view_model_surfaces():
    plugin = FilamentHubBridgePlugin()

    configs = plugin.get_template_configs()

    assert configs == [
        {
            "type": "tab",
            "name": "FilamentHub",
            "custom_bindings": True,
        },
        {
            "type": "sidebar",
            "name": "FilamentHub",
            "icon": "fas fa-layer-group",
            "custom_bindings": True,
            "data_bind": "visible: paired",
        },
    ]


def test_plugin_ui_separates_declared_slot_from_last_gcode_tool_command():
    package_root = Path(octoprint_filamenthub_bridge.__file__).resolve().parent
    javascript = (package_root / "static/js/filamenthub_bridge.js").read_text(
        encoding="utf-8"
    )
    tab = (package_root / "templates/filamenthub_bridge_tab.jinja2").read_text(
        encoding="utf-8"
    )
    sidebar = (
        package_root / "templates/filamenthub_bridge_sidebar.jinja2"
    ).read_text(encoding="utf-8")

    assert "state.commanded_tool" in javascript
    assert "state.current_tool" in javascript
    assert "Last G-code tool command" in javascript
    assert "Declared loaded slot" in javascript
    assert "Usage route" in tab
    assert "commandedToolText" in sidebar
    assert "manualSlotText" in sidebar


def test_explicit_tool_routing_accepts_virtual_tools_independent_of_slot_number():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    calls = []

    def update_routing(method, path, payload):
        calls.append((method, path, payload))
        return (
            200,
            {},
            {
                "mode": "tools",
                "tool_slot_map": [{"tool_index": 3, "slot_index": 0}],
                "revision": 1,
                "applied_revision": 0,
            },
        )

    plugin._request = update_routing

    plugin._save_routing(enabled=True, mapping={3: 0})

    assert calls == [
        (
            "PUT",
            "/routing",
            {
                "mode": "tools",
                "tool_slot_map": [{"tool_index": 3, "slot_index": 0}],
                "expected_revision": 0,
            },
        )
    ]
    assert plugin._settings.get(["map_tools_to_slots"]) is True
    assert plugin._settings.get(["tool_slot_map"]) == {"3": 0}
    assert plugin._settings.get(["routing_revision"]) == 1
    assert plugin._tool_slot_map() == {3: 0}


def test_heartbeat_applies_routing_changed_on_filamenthub():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    sent = []

    def heartbeat(method, path, payload):
        sent.append((method, path, payload))
        return (
            200,
            {},
            {
                "routing": {
                    "mode": "tools",
                    "tool_slot_map": [
                        {"tool_index": 0, "slot_index": 0},
                        {"tool_index": 7, "slot_index": 0},
                    ],
                    "revision": 4,
                    "applied_revision": 0,
                }
            },
        )

    plugin._request = heartbeat
    plugin._send_heartbeat()

    assert sent[0][2]["routing_mode"] == "manual"
    assert sent[0][2]["tool_slot_map"] == []
    assert sent[0][2]["routing_revision"] == 0
    assert plugin._settings.get(["map_tools_to_slots"]) is True
    assert plugin._settings.get(["tool_slot_map"]) == {"0": 0, "7": 0}
    assert plugin._settings.get(["routing_revision"]) == 4


def test_heartbeat_does_not_rewrite_unchanged_routing_settings():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._settings.set_boolean(["map_tools_to_slots"], True)
    plugin._settings.set(["tool_slot_map"], {"0": 0, "7": 0})
    plugin._settings.set(["routing_revision"], 4)

    plugin._apply_server_routing(
        {
            "mode": "tools",
            "tool_slot_map": [
                {"tool_index": 0, "slot_index": 0},
                {"tool_index": 7, "slot_index": 0},
            ],
            "revision": 4,
            "applied_revision": 4,
        }
    )

    assert plugin._settings.save_count == 0


def test_failed_server_routing_update_preserves_applied_local_configuration():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._settings.set(["routing_revision"], 3)

    def conflict(*args, **kwargs):
        raise RuntimeError("routing revision conflict")

    plugin._request = conflict

    try:
        plugin._save_routing(enabled=True, mapping={0: 0})
    except RuntimeError as exc:
        assert str(exc) == "routing revision conflict"
    else:
        raise AssertionError("A stale local edit must not overwrite shared routing")

    assert plugin._settings.get(["map_tools_to_slots"]) is False
    assert plugin._settings.get(["tool_slot_map"]) == {}
    assert plugin._settings.get(["routing_revision"]) == 3


def test_tool_routing_rejects_a_slot_missing_from_the_snapshot():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()

    try:
        plugin._save_routing(enabled=True, mapping={0: 6})
    except ValueError as exc:
        assert str(exc) == "Unknown FilamentHub slot(s): 7."
    else:
        raise AssertionError("A missing slot must not be accepted")


def test_legacy_identity_mapping_is_preserved_after_upgrade():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._settings.set(["map_tools_to_slots"], True)
    plugin._settings.set(["tool_slot_map"], {})

    assert plugin._tool_slot_map() == {0: 0}


def test_sensitive_settings_are_never_exposed_by_settings_api():
    plugin = FilamentHubBridgePlugin()

    assert plugin.get_settings_restricted_paths() == {
        "never": [
            ["bridge_token"],
            ["snapshot"],
            ["outbox"],
        ]
    }


def test_spool_search_is_bounded_and_url_encoded():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    calls = []

    def request(method, path):
        calls.append((method, path))
        return 200, {}, {"items": [{"id": 52}], "next_offset": 50}

    plugin._request = request

    response = plugin._search_spools("PETG Blue", 25)

    assert calls == [("GET", "/spools?query=PETG+Blue&limit=25&offset=25")]
    assert response == {"items": [{"id": 52}], "next_offset": 50}


def test_explicit_spool_assignment_uses_snapshot_revision_and_applies_ack():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    calls = []
    accepted_snapshot = {
        "revision": "accepted-revision",
        "system_name": "OctoPrint",
        "slots": [
            {
                "material_slot_id": 17,
                "index": 0,
                "assignment_revision": 4,
                "spool": {"id": 52},
            }
        ],
    }

    def request(method, path, payload):
        calls.append((method, path, payload))
        return 200, {}, accepted_snapshot

    plugin._request = request
    plugin._assign_spool(17, 52)

    assert calls == [
        (
            "PATCH",
            "/material-slots/17",
            {
                "expected_revision": 3,
                "expected_spool_id": 41,
                "spool_id": 52,
            },
        )
    ]
    assert plugin._settings.get(["snapshot"]) == accepted_snapshot
    assert plugin._settings.get(["snapshot_etag"]) == '"accepted-revision"'
    assert plugin._settings.get(["last_error"]) is None


def test_assignment_conflict_refreshes_snapshot_without_retrying_write():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    calls = []
    fresh_snapshot = {
        "revision": "fresh-revision",
        "slots": [
            {
                "material_slot_id": 17,
                "index": 0,
                "assignment_revision": 4,
                "spool": {"id": 77},
            }
        ],
    }

    def request(method, path, payload=None, extra_headers=None):
        calls.append((method, path, payload, extra_headers))
        if method == "PATCH":
            raise BridgeRequestError("stale", status_code=409)
        return 200, {"ETag": '"fresh-revision"'}, fresh_snapshot

    plugin._request = request

    try:
        plugin._assign_spool(17, 52)
    except BridgeRequestError as exc:
        assert exc.status_code == 409
        assert "latest state was loaded" in str(exc)
    else:
        raise AssertionError("A stale assignment must remain a conflict")

    assert [call[0] for call in calls] == ["PATCH", "GET"]
    assert plugin._settings.get(["snapshot"]) == fresh_snapshot
    assert plugin._settings.get(["snapshot_etag"]) == '"fresh-revision"'
