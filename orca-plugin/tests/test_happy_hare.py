"""Happy Hare discovery, observation and delivery contracts."""

from .filamenthub_plugin_test_support import (
    hashlib,
    hmac,
    _immediate_commit,
    _immediate_device,
    json,
    pytest,
    SimpleNamespace,
    threading,
)


def test_bambu_candidates_use_only_the_current_profile_as_unbound_fallback(
    plugin_module,
):
    observations = [
        {
            "preset_name": "Not selected",
            "print_host": "192.168.1.60",
            "is_current": False,
        },
        {
            "preset_name": "Selected P2S",
            "print_host": "p2s.local:8883",
            "is_current": True,
        },
        {
            "preset_name": "Unsafe",
            "print_host": "https://user@192.168.1.61/private",
            "is_current": True,
        },
    ]

    assert plugin_module.bambu_host_candidates(observations, {}, 7) == [
        {"host": "p2s.local", "label": "Selected P2S"}
    ]

def test_printer_endpoint_sync_is_local_only_until_opt_in(plugin_module):
    observations = [
        {
            "connection_ref": "orca-local-v1:account:machine",
            "print_host": "192.168.1.21:7125",
            "host_type": "moonraker",
        }
    ]

    private = plugin_module._observations_for_sync(observations)
    shared = plugin_module._observations_for_sync(
        observations, share_endpoints=True
    )

    assert private[0]["connection_ref"] == observations[0]["connection_ref"]
    assert private[0]["print_host"] == ""
    assert shared[0]["print_host"] == "192.168.1.21:7125"
    assert observations[0]["print_host"] == "192.168.1.21:7125"

@pytest.mark.parametrize("host,canonical", [
    ("PRINTER.local./", "moonraker|http|printer.local|80|"),
    ("http://printer.local:80", "moonraker|http|printer.local|80|"),
    ("https://printer.local/moonraker/", "moonraker|https|printer.local|443|/moonraker"),
    ("http://[fd00::1]:7125", "moonraker|http|fd00::1|7125|"),
])
def test_printer_endpoint_evidence_has_a_stable_cross_client_format(plugin_module, host, canonical):
    key = "ab" * 32
    expected = hmac.new(bytes.fromhex(key), ("endpoint\0" + canonical).encode(), hashlib.sha256).hexdigest()
    assert plugin_module._connection_endpoint_token(key, host, "moonraker") == expected

def test_device_probe_is_bounded_private_and_off_the_calling_thread(plugin_module, monkeypatch):
    caller = threading.get_ident()
    calls = []
    def probe(connection, path, timeout=None):
        assert threading.get_ident() != caller
        assert timeout == 3
        assert path == "/server/database/item?namespace=moonraker&key=instance_id"
        calls.append(path)
        return 200, {"result": {"value": "33B71C40-C780-44BA-BD4C-0F3F340C1CC8"}}, ""
    monkeypatch.setattr(plugin_module, "_moonraker_json", probe)
    host = "192.168.1.21:7125"
    observations = [{"print_host": host, "host_type": "moonraker", "connection_ref": ref}
                    for ref in ("first", "second")]
    result = plugin_module._observations_for_sync(observations, discovery_key="ab" * 32,
                                                 local_connections=[{"print_host": host, "api_key": "secret"}])
    assert len(calls) == 1
    assert result[0]["device_identity"] == result[1]["device_identity"]
    assert result[0]["device_identity"]["kind"] == "moonraker_instance"
    assert host not in json.dumps(result) and "secret" not in json.dumps(result)
    assert "33b71c40" not in json.dumps(result)

def test_failed_probe_does_not_invent_identity_and_empty_snapshot_is_sent(plugin_module, monkeypatch):
    monkeypatch.setattr(plugin_module, "_moonraker_json", lambda *a, **k: (404, {}, ""))
    result = plugin_module._observations_for_sync([{"print_host": "printer:7125", "host_type": "moonraker"}],
        discovery_key="ab" * 32, local_connections=[{"print_host": "printer:7125"}])
    assert "device_identity" not in result[0] and result[0]["endpoint_token"]
    posted = []
    monkeypatch.setattr(plugin_module, "http_post_json", lambda path, token, body: (posted.append(body) or 200, b'{}'))
    empty = plugin_module.PrinterObservationSnapshot()
    plugin_module.send_printer_observations("token", plugin_module._observations_for_sync(empty), "source")
    assert posted[0]["observations"] == [] and posted[0]["snapshot_complete"] is False
    empty.complete = True
    plugin_module.send_printer_observations("token", empty, "source")
    assert posted[1]["snapshot_complete"] is True

def test_moonraker_api_key_stays_in_local_connection_scan(plugin_module, monkeypatch):
    values = {
        "printer_settings_id": "Workshop Voron",
        "printer_model": "Voron 2.4 350",
        "print_host": "192.168.1.21:7125",
        "host_type": "moonraker",
        "printhost_apikey": "local-secret",
        "nozzle_diameter": ["0.4"],
    }

    class Preset:
        name = "Workshop Voron"
        bundle_id = "user"
        file = ""

        @staticmethod
        def is_user():
            return True

        @staticmethod
        def config_keys():
            return list(values)

        @staticmethod
        def config_value(key):
            return values.get(key)

    preset = Preset()
    collection = SimpleNamespace(
        size=lambda: 1,
        preset=lambda _index: preset,
        find_preset=lambda _name: None,
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(
            printers=collection,
            current_printer_preset=lambda: preset,
        ),
        raising=False,
    )

    observations = plugin_module.observe_printer_presets()
    local = plugin_module.observe_local_moonraker_connections(observations)

    assert len(local) == 1
    assert local[0]["api_key"] == "local-secret"
    assert "api_key" not in observations[0]
    assert "printhost_apikey" not in observations[0]
    assert "local-secret" not in json.dumps(
        plugin_module._observations_for_sync(observations)
    )

def test_happy_hare_snapshot_requires_one_exact_topology(plugin_module, monkeypatch):
    def moonraker(_connection, path, payload=None):
        if path == "/printer/info":
            return 200, {"result": {"hostname": "voron"}}, ""
        if path == "/server/config":
            return 200, {"result": {"config": {}}}, ""
        assert payload is not None
        return 200, {
            "result": {
                "status": {
                    "mmu": {
                        "num_gates": 2,
                        "gate_status": [2, 1],
                        "gate_material": ["PLA"],
                        "gate_color": ["ff0000", "00ff00"],
                        "gate_temperature": [210, 220],
                        "gate_spool_id": [41, -1],
                        "spoolman_support": "pull",
                    },
                    "print_stats": {"state": "standby"},
                }
            }
        }, ""

    monkeypatch.setattr(plugin_module, "_moonraker_json", moonraker)

    with pytest.raises(ValueError, match="disagree"):
        plugin_module.read_happy_hare_snapshot({"print_host": "voron:7125"})

def test_happy_hare_v3_can_report_exact_count_before_gate_arrays(
    plugin_module, monkeypatch
):
    def moonraker(_connection, path, payload=None):
        if path == "/server/config":
            return 200, {"result": {"config": {}}}, ""
        if path == "/printer/info":
            return 200, {"result": {"hostname": "voron"}}, ""
        assert payload is not None
        return 200, {
            "result": {
                "status": {
                    "mmu": {"num_gates": 8, "spoolman_support": "off"},
                    "print_stats": {"state": "standby"},
                }
            }
        }, ""

    monkeypatch.setattr(plugin_module, "_moonraker_json", moonraker)

    snapshot = plugin_module.read_happy_hare_snapshot(
        {"print_host": "voron:7125"}
    )

    assert snapshot["gate_count"] == 8
    assert len(snapshot["gates"]) == 8
    assert snapshot["actual_spool_ids"] == [None] * 8
    assert snapshot["spool_ids_known"] is False
    assert snapshot["spoolman_support"] == "off"
    assert snapshot["has_bypass"] is None
    assert snapshot["bypass"] is None

def test_happy_hare_snapshot_reports_selected_bypass_without_a_fake_gate(
    plugin_module, monkeypatch
):
    requested_mmu_fields = []

    def moonraker(_connection, path, payload=None):
        if path == "/server/config":
            return 200, {"result": {"config": {}}}, ""
        if path == "/printer/info":
            return 200, {"result": {"hostname": "voron"}}, ""
        requested_mmu_fields.extend(payload["objects"]["mmu"])
        return 200, {
            "result": {
                "status": {
                    "mmu": {
                        "num_gates": 2,
                        "gate_status": [1, 0],
                        "gate_spool_id": [41, -1],
                        "spoolman_support": "pull",
                        "has_bypass": True,
                        "tool": -2,
                        "filament_pos": 10,
                    },
                    "print_stats": {"state": "standby"},
                }
            }
        }, ""

    monkeypatch.setattr(plugin_module, "_moonraker_json", moonraker)

    snapshot = plugin_module.read_happy_hare_snapshot(
        {"print_host": "voron:7125"}
    )

    assert {"has_bypass", "tool", "filament_pos"} <= set(requested_mmu_fields)
    assert snapshot["gate_count"] == 2
    assert [item["gate"] for item in snapshot["gates"]] == [0, 1]
    assert snapshot["actual_spool_ids"] == [41, None]
    assert snapshot["has_bypass"] is True
    assert snapshot["bypass"] == {"selected": True, "present": True}

def test_happy_hare_snapshot_and_upload_preserve_generic_tag_evidence(
    plugin_module, monkeypatch
):
    requested_mmu_fields = []

    def moonraker(_connection, path, payload=None):
        if path == "/server/config":
            return 200, {"result": {"config": {}}}, ""
        if path == "/printer/info":
            return 200, {"result": {"hostname": "voron"}}, ""
        requested_mmu_fields.extend(payload["objects"]["mmu"])
        return 200, {
            "result": {
                "status": {
                    "mmu": {
                        "num_gates": 2,
                        "gate_status": [1, 1],
                        "gate_spool_rfid": ["04A1B2C3", "not-a-tag"],
                        "spoolman_support": "off",
                    },
                    "print_stats": {"state": "standby"},
                }
            }
        }, ""

    monkeypatch.setattr(plugin_module, "_moonraker_json", moonraker)
    snapshot = plugin_module.read_happy_hare_snapshot(
        {"print_host": "voron:7125"}
    )

    assert "gate_spool_rfid" in requested_mmu_fields
    assert snapshot["tag_read_capable"] is True
    assert snapshot["gates"][0]["rfid_uid"] == "04A1B2C3"
    assert "rfid_uid" not in snapshot["gates"][1]

    sent = {}

    def post(path, token, payload):
        sent.update({"path": path, "token": token, "payload": payload})
        return 200, b"{}"

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    status, _ = plugin_module.upload_happy_hare_snapshot(
        "plugin-token", 17, snapshot
    )

    assert status == 200
    assert sent["payload"]["tag_read_capable"] is True
    assert sent["payload"]["gates"][0]["rfid_uid"] == "04A1B2C3"

def test_happy_hare_snapshot_keeps_unselected_bypass_presence_unknown(
    plugin_module, monkeypatch
):
    def moonraker(_connection, path, payload=None):
        if path == "/printer/info":
            return 200, {"result": {"hostname": "voron"}}, ""
        return 200, {
            "result": {
                "status": {
                    "mmu": {
                        "num_gates": 1,
                        "has_bypass": True,
                        "tool": 0,
                        "filament_pos": 0,
                    },
                    "print_stats": {"state": "standby"},
                }
            }
        }, ""

    monkeypatch.setattr(plugin_module, "_moonraker_json", moonraker)

    snapshot = plugin_module.read_happy_hare_snapshot(
        {"print_host": "voron:7125"}
    )

    assert snapshot["bypass"] == {"selected": False, "present": None}

def test_happy_hare_upload_includes_bypass_as_separate_route_observation(
    plugin_module, monkeypatch
):
    sent = {}

    def post(path, token, payload):
        sent.update({"path": path, "token": token, "payload": payload})
        return 200, b"{}"

    monkeypatch.setattr(plugin_module, "http_post_json", post)

    status, _ = plugin_module.upload_happy_hare_snapshot(
        "plugin-token",
        17,
        {
            "gate_count": 1,
            "gates": [{"gate": 0, "status": 1}],
            "has_bypass": True,
            "bypass": {"selected": True, "present": False},
        },
    )

    assert status == 200
    assert sent["path"] == "/orcaslicer/preset-slot-sync/hh/snapshot"
    assert sent["payload"]["physical_printer_id"] == 17
    assert sent["payload"]["gates"] == [{"gate": 0, "status": 1}]
    assert sent["payload"]["has_bypass"] is True
    assert sent["payload"]["bypass"] == {"selected": True, "present": False}

def test_happy_hare_preview_allows_server_validated_import_without_pull(
    plugin_module, monkeypatch
):
    snapshot = {
        "gate_count": 8,
        "gates": [],
        "actual_spool_ids": [None] * 8,
        "spool_ids_known": False,
        "spoolman_support": "off",
        "print_state": "standby",
        "printer_hostname": "voron",
    }
    connection = {"print_host": "voron:7125", "connection_ref": "fh-ref"}
    monkeypatch.setattr(
        plugin_module,
        "resolve_happy_hare_connection",
        lambda *_args, **_kwargs: (
            connection,
            snapshot,
            {
                "id": 3,
                "material_systems": [{
                    "id": 7,
                    "provider": "happy_hare",
                    "slots": [],
                }],
            },
            None,
        ),
    )
    monkeypatch.setattr(
        plugin_module,
        "upload_happy_hare_snapshot",
        lambda *_args, **_kwargs: (200, {}),
    )
    monkeypatch.setattr(
        plugin_module,
        "request_happy_hare_reconciliation",
        lambda *_args, **_kwargs: (
            200,
            {
                "changes": [],
                "importChanges": [{
                    "gate": 0,
                    "proposedSpoolId": 11,
                    "desiredSpoolId": None,
                    "source": "provider",
                }],
                "unresolved": [],
                "desiredAssignments": [
                    {"gate": gate, "spool_id": None} for gate in range(8)
                ],
            },
        ),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_happy_hare_result",
        lambda request_id, result: delivered.append((request_id, result)),
    )

    catalog._do_happy_hare_action("request-1", "preview", 3, 7, "token", [connection])

    assert delivered[0][1]["ok"] is True
    assert delivered[0][1]["importChanges"][0]["proposedSpoolId"] == 11
    assert delivered[0][1]["gateCount"] == 8

@pytest.mark.parametrize("proof", [None, "0" * 64])
def test_happy_hare_wrong_inventory_cannot_reconcile_or_send_commands(plugin_module, monkeypatch, proof):
    snapshot = {"inventory_key_digest": proof}
    monkeypatch.setattr(plugin_module, "resolve_happy_hare_connection", lambda *args: (
        {"print_host": "printer.local"}, snapshot, {"inventory_key_digest": "1" * 64}, None,
    ))
    monkeypatch.setattr(plugin_module, "upload_happy_hare_snapshot", lambda *args: (200, {}))
    def forbidden(*args, **kwargs):
        pytest.fail("unverified inventory must not be reconciled or written")
    monkeypatch.setattr(plugin_module, "request_happy_hare_reconciliation", forbidden)
    monkeypatch.setattr(plugin_module, "_moonraker_json", forbidden)
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver_happy_hare_result", lambda request, result: delivered.append(result))
    catalog._do_happy_hare_action("unverified", "apply", 3, 7, "token", [])
    assert delivered[0]["ok"] is False
    assert delivered[0]["code"] == "inventory_not_connected"

def test_happy_hare_apply_waits_for_allowlisted_refresh_to_converge(
    plugin_module, monkeypatch
):
    before = {
        "gate_count": 2,
        "gates": [],
        "actual_spool_ids": [None, 22],
        "spool_ids_known": True,
        "spoolman_support": "pull",
        "print_state": "standby",
        "printer_hostname": "voron",
    }
    after = {**before, "actual_spool_ids": [11, None]}
    connection = {
        "print_host": "voron:7125",
        "api_key": "secret",
        "connection_ref": "fh-ref",
    }
    monkeypatch.setattr(
        plugin_module,
        "resolve_happy_hare_connection",
        lambda *_args, **_kwargs: (
            connection,
            before,
            {
                "id": 3,
                "material_systems": [{
                    "id": 7,
                    "provider": "happy_hare",
                    "slots": [
                        # The context GET can race a browser edit; the scoped
                        # server preview below is the state the user confirms.
                        {"provider_index": 0, "spool_id": 99},
                        {"provider_index": 1, "spool_id": None},
                    ],
                }],
            },
            None,
        ),
    )
    monkeypatch.setattr(
        plugin_module,
        "upload_happy_hare_snapshot",
        lambda *_args, **_kwargs: (200, {}),
    )
    expected = [
        {"gate": 0, "spool_id": 11},
        {"gate": 1, "spool_id": None},
    ]
    monkeypatch.setattr(
        plugin_module,
        "request_happy_hare_reconciliation",
        lambda *_args, **_kwargs: (
            200,
            {
                "changes": [
                    {"gate": 0, "actualSpoolId": None, "desiredSpoolId": 11},
                    {"gate": 1, "actualSpoolId": 22, "desiredSpoolId": None},
                ],
                "importChanges": [],
                "unresolved": [],
                "desiredAssignments": expected,
            },
        ),
    )
    command_calls = []
    monkeypatch.setattr(
        plugin_module,
        "_moonraker_json",
        lambda _connection, path, payload=None: (
            command_calls.append((path, payload)) or (200, {"result": "ok"}, "")
        ),
    )
    snapshots = iter([before, before, after])
    monkeypatch.setattr(
        plugin_module,
        "read_happy_hare_snapshot",
        lambda _connection: next(snapshots),
    )
    sleep_calls = []
    monkeypatch.setattr(
        plugin_module.time,
        "sleep",
        lambda seconds: sleep_calls.append(seconds),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_happy_hare_result",
        lambda request_id, result: delivered.append((request_id, result)),
    )

    catalog._do_happy_hare_action(
        "request-1", "apply", 3, 7, "token", [connection], expected
    )

    assert command_calls == [
        ("/printer/gcode/script", {"script": "MMU_SPOOLMAN REFRESH=1"})
    ]
    assert sleep_calls == [0.5, 1.0, 2.0]
    assert delivered[0][1]["ok"] is True
    assert delivered[0][1]["remainingChanges"] == []

def test_happy_hare_reconciliation_sends_local_ids_only_to_scoped_backend(
    plugin_module, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        plugin_module, "plugin_source_instance_id", lambda: "orca-instance-123456"
    )

    def post(path, token, payload):
        calls.append((path, token, payload))
        return 200, json.dumps({
            "printer_changes": [],
            "import_changes": [{
                "gate": 0,
                "proposed_spool_id": 11,
                "desired_spool_id": None,
                "source": "provider",
            }],
            "unresolved": [],
            "desired_assignments": [{"gate": 0, "spool_id": None}],
            "adopted_gates": 0,
        }).encode()

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    status, result = plugin_module.request_happy_hare_reconciliation(
        "plugin-token",
        "preview",
        3,
        7,
        {
            "connection_ref": "fh-ref-1",
            "print_host": "http://192.168.1.2:7125",
            "api_key": "moonraker-secret",
        },
        {
            "gate_count": 1,
            "spool_ids_known": True,
            "actual_spool_ids": [11],
            "gates": [{"gate": 0, "status": 1}],
        },
    )

    assert status == 200
    assert result["importChanges"][0]["proposedSpoolId"] == 11
    payload = calls[0][2]
    assert payload["connection_ref"] == "fh-ref-1"
    assert payload["gates"] == [{"gate": 0, "status": 1, "spool_id": 11}]
    assert "print_host" not in str(payload)
    assert "moonraker-secret" not in str(payload)

def test_happy_hare_adopt_restores_last_known_map_then_verifies_printer(
    plugin_module, monkeypatch
):
    before = {
        "gate_count": 1,
        "gates": [{"gate": 0, "status": 1}],
        "actual_spool_ids": [None],
        "spool_ids_known": True,
        "spoolman_support": "pull",
        "print_state": "standby",
        "printer_hostname": "voron",
    }
    after = {**before, "actual_spool_ids": [11]}
    expected = [{"gate": 0, "spool_id": None}]
    connection = {
        "connection_ref": "fh-ref-1",
        "print_host": "voron:7125",
        "api_key": "secret",
    }
    monkeypatch.setattr(
        plugin_module,
        "resolve_happy_hare_connection",
        lambda *_args, **_kwargs: (
            connection,
            before,
            {
                "id": 3,
                "material_systems": [{
                    "id": 7,
                    "provider": "happy_hare",
                    "slots": [{"provider_index": 0, "spool_id": None}],
                }],
            },
            None,
        ),
    )
    monkeypatch.setattr(
        plugin_module,
        "upload_happy_hare_snapshot",
        lambda *_args, **_kwargs: (200, {}),
    )

    def reconcile(_token, operation, *_args, **_kwargs):
        common = {
            "changes": [],
            "importChanges": [{
                "gate": 0,
                "proposedSpoolId": 11,
                "desiredSpoolId": None,
                "source": "last_known",
            }],
            "unresolved": [],
            "desiredAssignments": expected,
        }
        return 200, {**common, "adoptedGates": 1 if operation == "adopt" else 0}

    monkeypatch.setattr(
        plugin_module, "request_happy_hare_reconciliation", reconcile
    )
    commands = []
    monkeypatch.setattr(
        plugin_module,
        "_moonraker_json",
        lambda _connection, path, payload=None: (
            commands.append((path, payload)) or (200, {"result": "ok"}, "")
        ),
    )
    snapshots = iter([before, after])
    monkeypatch.setattr(
        plugin_module,
        "read_happy_hare_snapshot",
        lambda _connection: next(snapshots),
    )
    monkeypatch.setattr(plugin_module.time, "sleep", lambda _seconds: None)
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_happy_hare_result",
        lambda request_id, result: delivered.append((request_id, result)),
    )

    catalog._do_happy_hare_action(
        "request-1", "adopt", 3, 7, "token", [connection], expected
    )

    assert commands == [
        ("/printer/gcode/script", {"script": "MMU_SPOOLMAN REFRESH=1"})
    ]
    assert delivered[0][1]["ok"] is True
    assert delivered[0][1]["adopted"] is True
    assert delivered[0][1]["remainingChanges"] == []

def test_happy_hare_context_uses_one_scoped_endpoint(plugin_module, monkeypatch):
    calls = []
    monkeypatch.setattr(
        plugin_module, "plugin_source_instance_id", lambda: "orca-instance-123456"
    )

    def get_json(path, token):
        calls.append((path, token))
        return 200, {
            "source_instance_id": "orca-instance-123456",
            "printers": [],
        }

    monkeypatch.setattr(plugin_module, "_filamenthub_json_get", get_json)

    inventory, error = plugin_module._happy_hare_server_inventory("plugin-token")

    assert error is None
    assert inventory == {
        "source_instance_id": "orca-instance-123456",
        "printers": [],
    }
    assert calls == [(
        "/orcaslicer/preset-slot-sync/plugin-context?source_instance_id="
        "orca-instance-123456",
        "plugin-token",
    )]

def test_happy_hare_immediate_assignment_pulls_fresh_map_and_preserves_other_gate(
    plugin_module, monkeypatch
):
    commit = _immediate_commit(provider_index=0)
    device = _immediate_device(provider="happy_hare", provider_index=0)
    device["material_systems"][0]["slots"].append({
        "material_slot_id": 72,
        "provider_index": 1,
        "assignment_revision": 8,
        "preset_id": 42,
        "spool_id": 22,
        "source_ts": "2026-09-05T11:00:00Z",
    })
    latest_device = json.loads(json.dumps(device))
    latest_device["material_systems"][0]["slots"][1].update({
        "assignment_revision": 9,
        "spool_id": 99,
        "source_ts": "2026-09-05T12:02:00Z",
    })
    before = {
        "gate_count": 2,
        "gates": [{"gate": 0}, {"gate": 1}],
        "actual_spool_ids": [None, 22],
        "spool_ids_known": True,
        "spoolman_support": "pull",
        "print_state": "standby",
        "inventory_key_digest": "a" * 64,
    }
    after = {**before, "actual_spool_ids": [301, 99]}
    connection = {"connection_ref": "fh-ref", "print_host": "voron"}
    monkeypatch.setattr(plugin_module, "verified_local_setup_connections", lambda *_args: [])
    inventories = iter([device, device, latest_device])
    monkeypatch.setattr(
        plugin_module, "_plugin_material_server_inventory",
        lambda *_args, **_kwargs: ({"printers": [next(inventories)]}, None),
    )
    monkeypatch.setattr(
        plugin_module, "resolve_happy_hare_connection",
        lambda *_args, **_kwargs: (connection, before, device, None),
    )
    commands = []
    monkeypatch.setattr(
        plugin_module, "_moonraker_json",
        lambda _connection, path, payload=None: (
            commands.append((path, payload)) or (200, {"result": "ok"}, "")
        ),
    )
    monkeypatch.setattr(plugin_module, "read_happy_hare_snapshot", lambda *_args: after)
    monkeypatch.setattr(plugin_module.time, "sleep", lambda *_args: None)
    uploads = []
    monkeypatch.setattr(
        plugin_module, "upload_happy_hare_snapshot",
        lambda _token, _printer_id, snapshot: (
            uploads.append(snapshot) or (200, {})
        ),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_happy_hare_result",
        lambda _request_id, result: delivered.append(result),
    )

    catalog._do_happy_hare_material_immediate(
        "assign", "assign", 3, 7, "token", [connection], commit,
        plugin_module.time.monotonic() + 20,
    )

    assert commands == [
        ("/printer/gcode/script", {"script": "MMU_SPOOLMAN REFRESH=1"})
    ]
    assert uploads == [after]
    assert after["actual_spool_ids"][1] == 99
    assert delivered[0]["ok"] is True
    assert delivered[0]["applied"] is True
    assert delivered[0]["observationUploaded"] is True

def test_happy_hare_immediate_stale_commit_stops_before_moonraker(
    plugin_module, monkeypatch
):
    device = _immediate_device(provider="happy_hare", revision=5)
    monkeypatch.setattr(plugin_module, "verified_local_setup_connections", lambda *_args: [])
    monkeypatch.setattr(
        plugin_module, "_plugin_material_server_inventory",
        lambda *_args, **_kwargs: ({"printers": [device]}, None),
    )
    monkeypatch.setattr(
        plugin_module, "resolve_happy_hare_connection",
        lambda *_args, **_kwargs: pytest.fail("stale assignment must stop before Moonraker"),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_happy_hare_result",
        lambda _request_id, result: delivered.append(result),
    )

    catalog._do_happy_hare_material_immediate(
        "stale", "assign", 3, 7, "token", [], _immediate_commit(),
        plugin_module.time.monotonic() + 20,
    )

    assert delivered[0]["code"] == "stale_assignment"
    assert delivered[0]["applied"] is False

def test_happy_hare_deadline_is_rechecked_after_final_server_read(
    plugin_module, monkeypatch
):
    commit = _immediate_commit(provider_index=0)
    device = _immediate_device(provider="happy_hare", provider_index=0)
    snapshot = {
        "gate_count": 1,
        "gates": [{"gate": 0}],
        "actual_spool_ids": [None],
        "spool_ids_known": True,
        "spoolman_support": "pull",
        "print_state": "standby",
        "inventory_key_digest": "a" * 64,
    }
    clock = [10.0]
    context_reads = [0]

    def current_context(*_args):
        context_reads[0] += 1
        if context_reads[0] == 2:
            clock[0] = 21.0
        return device, device["material_systems"][0], \
            device["material_systems"][0]["slots"][0], None

    monkeypatch.setattr(plugin_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(plugin_module, "verified_local_setup_connections", lambda *_args: [])
    monkeypatch.setattr(
        plugin_module, "_plugin_material_server_inventory",
        lambda *_args, **_kwargs: ({"printers": [device]}, None),
    )
    monkeypatch.setattr(plugin_module, "_material_commit_context", current_context)
    monkeypatch.setattr(
        plugin_module, "resolve_happy_hare_connection",
        lambda *_args, **_kwargs: ({"connection_ref": "fh-ref"}, snapshot, device, None),
    )
    monkeypatch.setattr(
        plugin_module, "_moonraker_json",
        lambda *_args: pytest.fail("expired final context must not execute command"),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_happy_hare_result",
        lambda _request_id, result: delivered.append(result),
    )

    catalog._do_happy_hare_material_immediate(
        "deadline", "assign", 3, 7, "token", [], commit, 20.0
    )

    assert context_reads[0] == 2
    assert delivered[0]["code"] == "expired"

def test_happy_hare_refresh_reads_and_uploads_without_command(
    plugin_module, monkeypatch
):
    device = _immediate_device(provider="happy_hare")
    snapshot = {
        "gate_count": 1,
        "gates": [{"gate": 0}],
        "actual_spool_ids": [301],
        "spool_ids_known": True,
        "spoolman_support": "pull",
        "print_state": "standby",
        "inventory_key_digest": "a" * 64,
    }
    monkeypatch.setattr(plugin_module, "verified_local_setup_connections", lambda *_args: [])
    monkeypatch.setattr(
        plugin_module, "_plugin_material_server_inventory",
        lambda *_args, **_kwargs: ({"printers": [device]}, None),
    )
    monkeypatch.setattr(
        plugin_module, "resolve_happy_hare_connection",
        lambda *_args, **_kwargs: ({"connection_ref": "fh-ref"}, snapshot, device, None),
    )
    uploads = []
    monkeypatch.setattr(
        plugin_module, "upload_happy_hare_snapshot",
        lambda *_args: (uploads.append(_args[-1]) or (200, {})),
    )
    monkeypatch.setattr(
        plugin_module, "_moonraker_json",
        lambda *_args: pytest.fail("refresh must not send a printer command"),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_happy_hare_result",
        lambda _request_id, result: delivered.append(result),
    )

    catalog._do_happy_hare_material_immediate(
        "refresh", "refresh", 3, 7, "token", [], None,
        plugin_module.time.monotonic() + 20,
    )

    assert uploads == [snapshot]
    assert delivered[0]["ok"] is True
    assert delivered[0]["applied"] is False
    assert delivered[0]["observationUploaded"] is True

def test_immediate_material_request_replay_returns_cached_result_without_resubmit(
    plugin_module, monkeypatch
):
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_bambu_material_result",
        lambda request_id, result: delivered.append((request_id, result)),
    )
    result = {"ok": False, "code": "write_failed", "operation": "assign"}
    fingerprint = ("assign", 3, 7, '{"assignmentRevision":4}')

    assert catalog._begin_immediate_material_request(
        "bambu", "same-request", fingerprint
    ) is True
    catalog._finish_immediate_material_request("bambu", "same-request", result)
    assert catalog._begin_immediate_material_request(
        "bambu", "same-request", fingerprint
    ) is False

    assert delivered == [
        ("same-request", result),
        ("same-request", result),
    ]

def test_immediate_material_request_rejects_altered_replay(
    plugin_module, monkeypatch
):
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_bambu_material_result",
        lambda request_id, result: delivered.append((request_id, result)),
    )
    first = ("assign", 3, 7, '{"assignmentRevision":4}')
    altered = ("assign", 3, 8, '{"assignmentRevision":4}')

    assert catalog._begin_immediate_material_request(
        "bambu", "same-request", first
    ) is True
    assert catalog._begin_immediate_material_request(
        "bambu", "same-request", altered
    ) is False

    assert delivered == [("same-request", {
        "ok": False,
        "code": "replay_mismatch",
        "operation": "assign",
        "physicalPrinterId": 3,
        "materialSystemId": 8,
        "applied": False,
        "observationUploaded": False,
    })]

@pytest.mark.parametrize(
    ("status", "error"),
    [(401, "auth"), (403, "access"), (500, "server")],
)
def test_happy_hare_context_reports_authorization_separately_from_server_errors(
    plugin_module, monkeypatch, status, error
):
    monkeypatch.setattr(
        plugin_module, "plugin_source_instance_id", lambda: "orca-instance-123456"
    )
    monkeypatch.setattr(
        plugin_module,
        "_filamenthub_json_get",
        lambda *_args, **_kwargs: (status, None),
    )

    assert plugin_module._happy_hare_server_inventory("token") == (None, error)

def test_happy_hare_resolves_only_the_bound_connection_ref(
    plugin_module, monkeypatch
):
    wanted = {"connection_ref": "fh-ref-1", "print_host": "voron:7125"}
    other = {"connection_ref": "fh-ref-2", "print_host": "other:7125"}
    snapshot = {"gate_count": 8}
    monkeypatch.setattr(
        plugin_module,
        "read_happy_hare_snapshot",
        lambda connection: snapshot if connection is wanted else pytest.fail(
            "an unbound connection was queried"
        ),
    )
    inventory = {
        "source_instance_id": "orca-instance-123456",
        "printers": [{
            "id": 3,
            "connection_refs": ["fh-ref-1"],
            "material_systems": [],
        }],
    }

    connection, result, printer, error = plugin_module.resolve_happy_hare_connection(
        "token", [other, wanted], 3, inventory=inventory
    )

    assert error is None
    assert connection is wanted
    assert result is snapshot
    assert printer["id"] == 3
