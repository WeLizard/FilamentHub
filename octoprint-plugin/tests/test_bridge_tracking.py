import logging

from octoprint.events import Events
from octoprint_filamenthub_bridge import (
    BridgeRequestError,
    RETRY_MAX_SECONDS,
    STARTUP_JITTER_MAX_SECONDS,
    FilamentHubBridgePlugin,
    _retry_delay,
)


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
    assert outbox[0]["outcome"] == "cancelled"
    assert outbox[0]["items"][0]["used_length_mm"] == 12.0


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
            plugin._settings.set(["outbox"], [first, second])
        return 200, {}, {"accepted": True}

    plugin._request = request
    plugin._flush_outbox()

    assert sent == [first, second]
    assert plugin._settings.get(["outbox"]) == []


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
