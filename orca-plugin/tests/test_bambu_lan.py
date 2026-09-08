"""Bambu LAN observation, delivery and recovery contracts."""

from .filamenthub_plugin_test_support import (
    _active_revoke_scheduler,
    _bambu_material_target,
    _bambu_mqtt_packet,
    _bambu_mqtt_report,
    _bambu_report,
    _bambu_snapshot_socket,
    _BambuMqttSocket,
    _immediate_commit,
    _immediate_device,
    json,
    Path,
    pytest,
    threading,
    time,
    urllib,
)


def test_bambu_bridge_declares_exact_runtime_capabilities(plugin_module):
    assert plugin_module._bambu_capabilities({}) == ["read", "write", "presence"]
    assert plugin_module._bambu_capabilities(_bambu_report()) == [
        "read",
        "write",
        "presence",
        "tag_read",
    ]

def test_bambu_feed_reports_only_what_the_printer_measured(plugin_module):
    feed = plugin_module.parse_bambu_feed(_bambu_report())

    by_index = {slot["index"]: slot for slot in feed["slots"]}
    assert feed["active_index"] == 1
    assert by_index[0]["material"] == "PLA"
    assert by_index[0]["color_hex"] == "FF6A13"
    assert by_index[0]["remaining_g"] == 812
    assert by_index[0]["provider_uid"] == "D1E2F3"

    # A third-party spool sits in the tray and the printer says so, but it cannot
    # weigh it. Reporting 0 here would read as an empty slot.
    assert by_index[1]["material"] == "PETG"
    assert by_index[1]["remaining_pct"] is None
    assert by_index[1]["remaining_g"] is None
    assert by_index[1]["provider_uid"] is None

def test_bambu_empty_tray_is_neither_coloured_nor_present(plugin_module):
    feed = plugin_module.parse_bambu_feed(_bambu_report())
    empty = next(slot for slot in feed["slots"] if slot["index"] == 2)

    assert empty["present"] is False
    assert empty["material"] is None
    assert empty["color_hex"] is None

def test_bambu_partial_push_does_not_erase_the_feed(plugin_module):
    assert plugin_module.parse_bambu_feed({"nozzle_temper": 218.5}) is None
    assert plugin_module.parse_bambu_feed({}) is None
    assert plugin_module.parse_bambu_feed(None) is None

@pytest.mark.parametrize("configured_serial", ["SERIAL-2", ""], ids=["configured", "discovered"])
def test_bambu_snapshot_preserves_useful_partial_report_on_read_timeout(
    plugin_module, monkeypatch, configured_serial
):
    serial = "SERIAL-2"
    partial_report = {"print": {"gcode_state": "IDLE", "nozzle_temper": 24}}
    report_packet = _bambu_mqtt_report(
        plugin_module,
        serial,
        json.dumps(partial_report).encode("utf-8"),
    )
    sock = _bambu_snapshot_socket(plugin_module, report_packet)
    monkeypatch.setattr(plugin_module, "_open_bambu_mqtt", lambda *_args: sock)

    observed_serial, report = plugin_module.read_bambu_lan_snapshot(
        {
            "host": "printer.local",
            "access_code": "local-secret",
            "serial": configured_serial,
            "material_system_id": 12,
        },
        timeout=1,
    )

    assert observed_serial == serial
    assert report == partial_report["print"]
    assert plugin_module.parse_bambu_feed(report) is None
    snapshot = plugin_module.build_bambu_bridge_snapshot(
        {"material_system_id": 12}, "fixture-plugin-instance-0001", report
    )
    assert snapshot["printer"]["state"] == "idle"
    assert snapshot["printer"]["nozzle_temperature"] == 24.0
    assert snapshot["slots"] == []
    assert snapshot["slot_topology_complete"] is False
    assert sock.timeouts and max(sock.timeouts) <= 1
    assert sock.sent[-1] == b"\xE0\x00"
    assert sock.closed is True

def test_bambu_snapshot_prefers_complete_report_after_partial_report(
    plugin_module, monkeypatch
):
    serial = "SERIAL-2"
    partial = {"print": {"gcode_state": "IDLE", "nozzle_temper": 24}}
    complete = {"print": _bambu_report(gcode_state="IDLE", nozzle_temper=25)}
    sock = _bambu_snapshot_socket(
        plugin_module,
        _bambu_mqtt_report(
            plugin_module, serial, json.dumps(partial).encode("utf-8")
        ),
        _bambu_mqtt_report(
            plugin_module, serial, json.dumps(complete).encode("utf-8")
        ),
    )
    monkeypatch.setattr(plugin_module, "_open_bambu_mqtt", lambda *_args: sock)

    observed_serial, report = plugin_module.read_bambu_lan_snapshot(
        {"host": "printer.local", "access_code": "local-secret", "serial": serial},
        timeout=1,
    )

    assert observed_serial == serial
    assert report == complete["print"]
    assert plugin_module.parse_bambu_feed(report) is not None
    assert sock.closed is True

@pytest.mark.parametrize(
    "report_packet",
    [
        None,
        ("report", b'{"print":{}}'),
        ("report", b'{"print":'),
        ("request", b'{"print":{"gcode_state":"IDLE"}}'),
    ],
    ids=["no-report", "empty-print", "malformed-json", "wrong-topic"],
)
def test_bambu_snapshot_timeout_without_useful_telemetry_stays_a_failure(
    plugin_module, monkeypatch, report_packet
):
    serial = "SERIAL-2"
    reports = []
    if report_packet is not None:
        topic_suffix, payload = report_packet
        reports.append(
            _bambu_mqtt_report(plugin_module, serial, payload, topic_suffix=topic_suffix)
        )
    sock = _bambu_snapshot_socket(plugin_module, *reports)
    monkeypatch.setattr(plugin_module, "_open_bambu_mqtt", lambda *_args: sock)

    with pytest.raises(TimeoutError, match="inert Bambu socket"):
        plugin_module.read_bambu_lan_snapshot(
            {"host": "printer.local", "access_code": "local-secret", "serial": serial},
            timeout=1,
        )

    assert sock.sent[-1] == b"\xE0\x00"
    assert sock.closed is True

def test_bambu_snapshot_does_not_hide_transport_failure_after_partial_report(
    plugin_module, monkeypatch
):
    serial = "SERIAL-2"
    report_packet = _bambu_mqtt_report(
        plugin_module,
        serial,
        b'{"print":{"gcode_state":"IDLE","nozzle_temper":24}}',
    )
    sock = _bambu_snapshot_socket(
        plugin_module,
        report_packet,
        terminal_error=ConnectionError("Bambu connection reset"),
    )
    monkeypatch.setattr(plugin_module, "_open_bambu_mqtt", lambda *_args: sock)

    with pytest.raises(ConnectionError, match="connection reset"):
        plugin_module.read_bambu_lan_snapshot(
            {"host": "printer.local", "access_code": "local-secret", "serial": serial},
            timeout=1,
        )

    assert sock.closed is True

def test_bambu_snapshot_keeps_authentication_rejection_truthful(plugin_module, monkeypatch):
    sock = _bambu_snapshot_socket(plugin_module, connack_code=5)
    monkeypatch.setattr(plugin_module, "_open_bambu_mqtt", lambda *_args: sock)

    with pytest.raises(PermissionError, match="authentication rejected"):
        plugin_module.read_bambu_lan_snapshot(
            {
                "host": "printer.local",
                "access_code": "wrong-local-secret",
                "serial": "SERIAL-2",
            },
            timeout=1,
        )

    assert sock.closed is True

def test_bambu_explicit_no_ams_report_is_complete_empty_topology(plugin_module):
    report = {"gcode_state": "IDLE", "ams": {"ams": []}}

    feed = plugin_module.parse_bambu_feed(report)
    snapshot = plugin_module.build_bambu_bridge_snapshot(
        {"material_system_id": 12}, "fixture-plugin-instance-0001", report
    )

    assert feed == {"slots": [], "active_index": None}
    assert snapshot["slots"] == []
    assert snapshot["slot_topology_complete"] is True

def test_bambu_slot_numbers_stay_the_printers_own(plugin_module):
    assert plugin_module.bambu_slot_index(0, 3) == 3
    assert plugin_module.bambu_slot_index(2, 1) == 9
    # The external holders and single-slot units carry their own flat number.
    assert plugin_module.bambu_slot_index(plugin_module.BAMBU_EXTERNAL_TRAY_MAIN, 0) == 255
    assert plugin_module.bambu_slot_index(plugin_module.BAMBU_WIDE_UNIT_BASE, 0) == 128

def test_bambu_external_spool_holder_becomes_a_slot(plugin_module):
    report = _bambu_report(
        vt_tray={
            "id": "255",
            "tray_type": "ABS",
            "tray_color": "1A1A1AFF",
            "remain": -1,
        }
    )
    feed = plugin_module.parse_bambu_feed(report)
    external = next(slot for slot in feed["slots"] if slot["index"] == 255)

    assert external["present"] is True
    assert external["material"] == "ABS"
    assert external["color_hex"] == "1A1A1A"

def test_bambu_feed_without_any_ams_still_reads_the_holder(plugin_module):
    feed = plugin_module.parse_bambu_feed(
        {"vt_tray": {"id": "255", "tray_type": "PLA", "tray_color": "FFFFFFFF"}}
    )

    assert [slot["index"] for slot in feed["slots"]] == [255]
    assert feed["active_index"] is None

def test_bambu_ht_presence_uses_bit_position_without_renumbering_identity(plugin_module):
    report = {
        "ams": {
            "tray_now": "128",
            "tray_exist_bits": "10000",
            "ams": [
                {
                    "id": "128",
                    "info": "4",
                    "tray": [
                        {
                            "id": "0",
                            "tray_type": "PA6-CF",
                            "tray_color": "111111FF",
                            "remain_g": "315",
                        }
                    ],
                }
            ],
        }
    }

    feed = plugin_module.parse_bambu_feed(report)

    assert feed["active_index"] == 128
    assert feed["slots"][0]["index"] == 128
    assert feed["slots"][0]["present"] is True

def test_bambu_snapshot_reports_tag_evidence_without_provider_specific_fields(plugin_module):
    report = _bambu_report(
        gcode_state="RUNNING",
        mc_percent="42",
        mc_remaining_time="60",
        layer_num="17",
        total_layer_num="80",
        subtask_name="fixture.3mf",
        nozzle_temper="220.5",
        bed_temper=60,
        wifi_signal="-52dBm",
    )
    config = {"physical_printer_id": 9, "material_system_id": 12}

    snapshot = plugin_module.build_bambu_bridge_snapshot(
        config, "fixture-plugin-instance-0001", report
    )

    assert snapshot["printer"]["state"] == "printing"
    assert snapshot["printer"]["remaining_seconds"] == 3600
    assert snapshot["printer"]["current_layer"] == 17
    assert snapshot["slot_topology_complete"] is True
    assert snapshot["slots"][0]["remaining_grams"] == 812
    assert snapshot["slots"][0]["tag_uid"] == "D1E2F3"
    assert snapshot["slots"][0]["tag_technology"] == "unknown"
    assert "tag_read" in snapshot["capabilities"]
    serialized = json.dumps(snapshot)
    assert "provider_uid" not in serialized
    assert "access_code" not in serialized
    assert "serial" not in serialized

def test_bambu_material_command_matches_vendor_slot_addressing(plugin_module):
    target = _bambu_material_target()

    regular = plugin_module._bambu_material_command(
        {"ams_id": 2, "slot_id": 1}, target
    )["print"]
    external = plugin_module._bambu_material_command(
        {"ams_id": plugin_module.BAMBU_EXTERNAL_TRAY_MAIN, "slot_id": 0},
        target,
    )["print"]

    assert regular == {
        **regular,
        "command": "ams_filament_setting",
        "ams_id": 2,
        "slot_id": 1,
        "tray_id": 1,
        "tray_info_idx": "GFL99",
        "setting_id": "GFSL99_01",
        "tray_color": "3366CCFF",
        "nozzle_temp_min": 190,
        "nozzle_temp_max": 230,
        "tray_type": "PLA",
    }
    assert external["ams_id"] == plugin_module.BAMBU_EXTERNAL_TRAY_MAIN
    assert external["slot_id"] == 0
    assert external["tray_id"] == plugin_module.BAMBU_EXTERNAL_TRAY_DEPUTY

def test_bambu_material_write_refuses_busy_or_rfid_slots(
    plugin_module, monkeypatch
):
    published = []
    reports = iter(
        [
            ("SERIAL-1", _bambu_report(gcode_state="RUNNING")),
            ("SERIAL-1", _bambu_report(gcode_state="IDLE")),
        ]
    )
    monkeypatch.setattr(
        plugin_module, "read_bambu_lan_snapshot", lambda *_args, **_kwargs: next(reports)
    )
    monkeypatch.setattr(
        plugin_module,
        "_publish_bambu_json",
        lambda *_args, **_kwargs: published.append(_args),
    )

    busy = plugin_module.apply_bambu_material_targets(
        {"host": "printer.local", "access_code": "fixture"},
        {1: _bambu_material_target()},
        settle_delay=0,
    )
    rfid = plugin_module.apply_bambu_material_targets(
        {"host": "printer.local", "access_code": "fixture"},
        {0: _bambu_material_target()},
        settle_delay=0,
    )

    assert busy["code"] == "printer_busy"
    assert rfid["code"] == "rfid_managed"
    assert published == []

def test_bambu_material_deadline_is_rechecked_after_lan_preflight(
    plugin_module, monkeypatch
):
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda *_args, **_kwargs: ("SERIAL-1", _bambu_report(gcode_state="IDLE")),
    )
    monkeypatch.setattr(plugin_module.time, "monotonic", lambda: 20.0)
    monkeypatch.setattr(
        plugin_module,
        "_publish_bambu_json",
        lambda *_args, **_kwargs: pytest.fail("expired preflight must not publish"),
    )

    result = plugin_module.apply_bambu_material_targets(
        {"host": "printer.local", "access_code": "fixture"},
        {1: _bambu_material_target()},
        settle_delay=0,
        absolute_deadline=20.0,
    )

    assert result["ok"] is False
    assert result["code"] == "expired"

def test_bambu_publish_refuses_command_when_connack_crosses_host_deadline(
    plugin_module, monkeypatch
):
    clock = [19.0]
    opened_with = []

    class CrossingConnackSocket(_BambuMqttSocket):
        def __init__(self):
            super().__init__([
                _bambu_mqtt_packet(plugin_module, 0x20, b"\x00\x00")
            ])
            self.recv_count = 0

        def recv(self, length):
            chunk = super().recv(length)
            self.recv_count += 1
            if self.recv_count == 3:
                clock[0] = 20.0
            return chunk

    sock = CrossingConnackSocket()
    monkeypatch.setattr(plugin_module.time, "monotonic", lambda: clock[0])

    def open_socket(_host, _access_code, timeout):
        opened_with.append(timeout)
        return sock

    monkeypatch.setattr(plugin_module, "_open_bambu_mqtt", open_socket)

    with pytest.raises(plugin_module._BambuCommandDeadlineExpired):
        plugin_module._publish_bambu_json(
            {"host": "printer.local", "access_code": "fixture"},
            "SERIAL-1",
            {"print": {"command": "ams_filament_setting"}},
            timeout=12,
            absolute_deadline=20.0,
        )

    assert opened_with == [pytest.approx(1.0)]
    assert sock.sent[0][0] == 0x10
    assert all(packet[0] != 0x30 for packet in sock.sent)
    assert sock.closed is True

def test_bambu_material_write_is_confirmed_by_a_fresh_printer_snapshot(
    plugin_module, monkeypatch
):
    before = _bambu_report(gcode_state="IDLE")
    after = _bambu_report(gcode_state="IDLE")
    after["ams"]["ams"][0]["tray"][1].update(
        {
            "tray_info_idx": "GFL99",
            "setting_id": "GFSL99_01",
            "tray_type": "PLA",
            "tray_color": "3366CCFF",
            "nozzle_temp_min": 190,
            "nozzle_temp_max": 230,
        }
    )
    reports = iter([("SERIAL-1", before), ("SERIAL-1", after)])
    published = []
    monkeypatch.setattr(
        plugin_module, "read_bambu_lan_snapshot", lambda *_args, **_kwargs: next(reports)
    )
    monkeypatch.setattr(
        plugin_module,
        "_publish_bambu_json",
        lambda _config, serial, payload, **_kwargs: published.append(
            (serial, payload)
        ),
    )

    result = plugin_module.apply_bambu_material_targets(
        {"host": "printer.local", "access_code": "fixture"},
        {1: _bambu_material_target()},
        settle_delay=0,
    )

    assert result["ok"] is True
    assert result["remaining"] == []
    assert len(published) == 1
    assert published[0][0] == "SERIAL-1"
    assert published[0][1]["print"]["command"] == "ams_filament_setting"

def test_bambu_material_write_never_reports_success_without_confirmation(
    plugin_module, monkeypatch
):
    unchanged = _bambu_report(gcode_state="IDLE")
    reports = iter([("SERIAL-1", unchanged)] * 4)
    monkeypatch.setattr(
        plugin_module, "read_bambu_lan_snapshot", lambda *_args, **_kwargs: next(reports)
    )
    monkeypatch.setattr(plugin_module, "_publish_bambu_json", lambda *_args, **_kwargs: None)

    result = plugin_module.apply_bambu_material_targets(
        {"host": "printer.local", "access_code": "fixture", "serial": "SERIAL-1"},
        {1: _bambu_material_target()},
        settle_delay=0,
    )

    assert result["ok"] is False
    assert result["code"] == "verification_failed"
    assert result["remaining"] == [1]

def test_bambu_material_write_contains_a_partial_mqtt_failure(
    plugin_module, monkeypatch
):
    before = _bambu_report(gcode_state="IDLE")
    before["ams"]["ams"][0]["tray"][0]["tray_uuid"] = "00000000"
    after_first = json.loads(json.dumps(before))
    after_first["ams"]["ams"][0]["tray"][0].update(
        {
            "tray_info_idx": "GFL99",
            "setting_id": "GFSL99_01",
            "tray_type": "PLA",
            "tray_color": "3366CCFF",
            "nozzle_temp_min": 190,
            "nozzle_temp_max": 230,
        }
    )
    reports = iter([("SERIAL-1", before), ("SERIAL-1", after_first)])
    publish_count = 0

    def publish(*_args, **_kwargs):
        nonlocal publish_count
        publish_count += 1
        if publish_count == 2:
            raise ConnectionError("fixture disconnect")

    monkeypatch.setattr(
        plugin_module, "read_bambu_lan_snapshot", lambda *_args, **_kwargs: next(reports)
    )
    monkeypatch.setattr(plugin_module, "_publish_bambu_json", publish)

    result = plugin_module.apply_bambu_material_targets(
        {"host": "printer.local", "access_code": "fixture", "serial": "SERIAL-1"},
        {0: _bambu_material_target(), 1: _bambu_material_target()},
        settle_delay=0,
    )

    assert publish_count == 2
    assert result["ok"] is False
    assert result["code"] == "write_failed"
    assert plugin_module.parse_bambu_feed(result["report"])["slots"][0][
        "filament_id"
    ] == "GFL99"

def test_bambu_material_apply_rejects_a_stale_server_assignment(
    plugin_module, monkeypatch
):
    local = {"source_instance_id": "fixture-instance-123456"}
    binding = {
        "physical_printer_id": 3,
        "material_system_id": 7,
        "bridge_token": "fhpb_fixture",
    }
    monkeypatch.setattr(
        plugin_module, "_bambu_local_binding", lambda *_args: (local, binding)
    )
    monkeypatch.setattr(
        plugin_module,
        "_plugin_material_server_inventory",
        lambda _token, source_instance_id=None: (
            {
                "printers": [
                    {
                        "id": 3,
                        "material_systems": [
                            {
                                "id": 7,
                                "provider": "bambu",
                                "slots": [
                                    {
                                        "provider_index": 1,
                                        "preset_id": 42,
                                        "spool_id": 302,
                                        "source_ts": "2026-08-14T01:00:00Z",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            None,
        ),
    )
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda *_args, **_kwargs: pytest.fail("stale preview must not reach the LAN"),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_bambu_material_result",
        lambda request_id, result: delivered.append((request_id, result)),
    )

    catalog._do_bambu_material_action(
        "request-1",
        "apply",
        3,
        7,
        "plugin-token",
        {},
        [
            {
                "slot": 1,
                "preset_id": 41,
                "spool_id": 301,
                "source_ts": "2026-08-14T00:00:00Z",
            }
        ],
    )

    assert delivered[0][1]["ok"] is False
    assert delivered[0][1]["code"] == "stale_preview"

@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (lambda device: device.update(id=99), "connection_not_found"),
        (lambda device: device["material_systems"][0].update(id=99),
         "material_system_not_found"),
        (lambda device: device["material_systems"][0]["slots"][0].update(
            material_slot_id=99), "slot_not_found"),
        (lambda device: device["material_systems"][0]["slots"][0].update(
            provider_index=2), "stale_assignment"),
        (lambda device: device["material_systems"][0]["slots"][0].update(
            assignment_revision=5), "stale_assignment"),
        (lambda device: device["material_systems"][0]["slots"][0].update(
            preset_id=42), "stale_assignment"),
        (lambda device: device["material_systems"][0]["slots"][0].update(
            spool_id=302), "stale_assignment"),
        (lambda device: device["material_systems"][0]["slots"][0].update(
            source_ts="2026-09-05T12:00:01Z"), "stale_assignment"),
    ],
)
def test_material_commit_context_rejects_every_addressing_mismatch(
    plugin_module, monkeypatch, mutate, expected_error
):
    device = _immediate_device()
    mutate(device)
    sources = []
    monkeypatch.setattr(
        plugin_module,
        "_plugin_material_server_inventory",
        lambda _token, source_instance_id=None: (
            sources.append(source_instance_id)
            or ({"printers": [device]}, None)
        ),
    )

    _device, _system, _slot, error = plugin_module._material_commit_context(
        "account-token",
        "bound-source-123456",
        "bambu",
        3,
        7,
        _immediate_commit(),
    )

    assert error == expected_error
    assert sources == ["bound-source-123456"]

def test_material_commit_context_stops_on_account_access_failure(
    plugin_module, monkeypatch
):
    monkeypatch.setattr(
        plugin_module,
        "_plugin_material_server_inventory",
        lambda *_args, **_kwargs: (None, "access"),
    )

    result = plugin_module._material_commit_context(
        "other-account-token", "bound-source-123456", "bambu", 3, 7,
        _immediate_commit(),
    )

    assert result == (None, None, None, "access")

def test_bambu_immediate_assignment_uses_spool_color_and_exactly_one_slot(
    plugin_module, monkeypatch
):
    commit = _immediate_commit(provider_index=5)
    local = {"source_instance_id": "fixture-instance-123456"}
    binding = {
        "physical_printer_id": 3,
        "material_system_id": 7,
        "bridge_token": "fhpb_fixture",
    }
    device = _immediate_device(provider_index=5)
    device["material_systems"][0]["slots"].append({
        "material_slot_id": 72,
        "provider_index": 6,
        "assignment_revision": 1,
        "preset_id": 42,
        "spool_id": 302,
        "source_ts": "2026-09-05T11:00:00Z",
    })
    device_after_other_slot_change = json.loads(json.dumps(device))
    device_after_other_slot_change["material_systems"][0]["slots"][1].update({
        "assignment_revision": 2,
        "spool_id": 999,
        "source_ts": "2026-09-05T12:01:00Z",
    })
    monkeypatch.setattr(
        plugin_module, "_bambu_local_binding", lambda *_args: (local, binding)
    )
    inventories = iter([device, device_after_other_slot_change])
    monkeypatch.setattr(
        plugin_module,
        "_plugin_material_server_inventory",
        lambda *_args, **_kwargs: ({"printers": [next(inventories)]}, None),
    )
    desired_snapshot = {
        "physical_printer_id": 3,
        "material_system_id": 7,
        "slots": [{
            "material_slot_id": 71,
            "index": 5,
            "assignment_revision": 4,
            "preset": {"id": 41, "name": "PLA preset"},
            "spool": {"id": 301, "material_type": "PLA", "color_hex": "#12AB34"},
        }],
    }
    monkeypatch.setattr(
        plugin_module,
        "http_get_bridge_json",
        lambda *_args: (200, json.dumps(desired_snapshot).encode()),
    )
    captured_targets = []
    monkeypatch.setattr(
        plugin_module,
        "apply_bambu_material_targets",
        lambda _binding, targets, **_kwargs: (
            captured_targets.append(targets)
            or {"ok": True, "report": {"gcode_state": "IDLE"}}
        ),
    )
    monkeypatch.setattr(
        plugin_module,
        "build_bambu_bridge_snapshot",
        lambda *_args: {"snapshot": True},
    )
    monkeypatch.setattr(
        plugin_module,
        "http_post_bridge_json",
        lambda *_args: (200, b"{}", None),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_bambu_material_result",
        lambda request_id, result: delivered.append((request_id, result)),
    )
    host_profiles = {41: {
        "name": "Loaded PLA",
        "filament_id": "GFL99",
        "setting_id": "GFSL99_01",
        "filament_type": "PLA",
        # The printer target must use the physical spool color below.
        "filament_colour": "#FF0000",
        "nozzle_temperature_range_low": "190",
        "nozzle_temperature_range_high": "230",
    }}

    catalog._do_bambu_material_immediate(
        "request-1", "assign", 3, 7, "token", host_profiles,
        commit, plugin_module.time.monotonic() + 20,
    )

    assert list(captured_targets[0]) == [5]
    assert captured_targets[0][5]["color_hex"] == "12AB34"
    assert captured_targets[0][5]["material"] == "PLA"
    assert captured_targets[0][5]["filament_id"] == "GFL99"
    assert delivered[0][1] == {
        "ok": True,
        "code": None,
        "applied": True,
        "observationUploaded": True,
        "operation": "assign",
        "physicalPrinterId": 3,
        "materialSystemId": 7,
    }

def test_bambu_immediate_assignment_rejects_stale_commit_before_lan(
    plugin_module, monkeypatch
):
    commit = _immediate_commit()
    stale = _immediate_device(revision=5)
    monkeypatch.setattr(
        plugin_module,
        "_bambu_local_binding",
        lambda *_args: (
            {"source_instance_id": "fixture-instance-123456"},
            {"physical_printer_id": 3, "material_system_id": 7,
             "bridge_token": "fhpb_fixture"},
        ),
    )
    monkeypatch.setattr(
        plugin_module,
        "_plugin_material_server_inventory",
        lambda *_args, **_kwargs: ({"printers": [stale]}, None),
    )
    monkeypatch.setattr(
        plugin_module,
        "http_get_bridge_json",
        lambda *_args: pytest.fail("stale commit must stop before bridge or LAN reads"),
    )
    monkeypatch.setattr(
        plugin_module,
        "apply_bambu_material_targets",
        lambda *_args: pytest.fail("stale commit must not reach MQTT"),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_bambu_material_result",
        lambda _request_id, result: delivered.append(result),
    )

    catalog._do_bambu_material_immediate(
        "stale", "assign", 3, 7, "token", {}, commit,
        plugin_module.time.monotonic() + 20,
    )

    assert delivered[0]["code"] == "stale_assignment"
    assert delivered[0]["applied"] is False

def test_bambu_immediate_assignment_rejects_wrong_spool_material(
    plugin_module, monkeypatch
):
    snapshot = {
        "physical_printer_id": 3,
        "material_system_id": 7,
        "slots": [{
            "material_slot_id": 71,
            "index": 1,
            "assignment_revision": 4,
            "preset": {"id": 41},
            "spool": {"id": 301, "material_type": "PETG", "color_hex": "#123456"},
        }],
    }
    monkeypatch.setattr(
        plugin_module,
        "http_get_bridge_json",
        lambda *_args: (200, json.dumps(snapshot).encode()),
    )
    target, error = plugin_module._bambu_committed_spool_target(
        {"physical_printer_id": 3, "material_system_id": 7,
         "bridge_token": "fhpb_fixture"},
        _immediate_commit(),
        {41: {
            "filament_id": "GFL99", "setting_id": "GFSL99_01",
            "filament_type": "PLA", "filament_colour": "#FFFFFF",
            "nozzle_temperature_range_low": 190,
            "nozzle_temperature_range_high": 230,
        }},
    )

    assert target is None
    assert error == "material_mismatch"

def test_bambu_refresh_forces_snapshot_upload_without_device_write(
    plugin_module, monkeypatch
):
    binding = {
        "physical_printer_id": 3,
        "material_system_id": 7,
        "bridge_token": "fhpb_fixture",
    }
    monkeypatch.setattr(
        plugin_module, "_bambu_local_binding",
        lambda *_args: ({"source_instance_id": "fixture-instance-123456"}, binding),
    )
    monkeypatch.setattr(
        plugin_module, "read_bambu_lan_snapshot",
        lambda *_args: ("SERIAL-1", {"gcode_state": "IDLE"}),
    )
    monkeypatch.setattr(
        plugin_module, "_prepare_bambu_observation",
        lambda *_args: (binding, "fixture-instance-123456"),
    )
    monkeypatch.setattr(
        plugin_module, "build_bambu_bridge_snapshot",
        lambda *_args: {"snapshot": True},
    )
    uploads = []
    monkeypatch.setattr(
        plugin_module, "http_post_bridge_json",
        lambda *args: (uploads.append(args) or (200, b"{}", None)),
    )
    monkeypatch.setattr(
        plugin_module, "_publish_bambu_json",
        lambda *_args: pytest.fail("refresh must never write to the printer"),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_bambu_material_result",
        lambda _request_id, result: delivered.append(result),
    )

    catalog._do_bambu_material_immediate(
        "refresh", "refresh", 3, 7, "token", {}, None,
        plugin_module.time.monotonic() + 20,
    )

    assert len(uploads) == 1
    assert delivered[0]["ok"] is True
    assert delivered[0]["applied"] is False
    assert delivered[0]["observationUploaded"] is True

def test_bambu_write_with_failed_upload_is_reported_as_uncertain(
    plugin_module, monkeypatch
):
    commit = _immediate_commit()
    monkeypatch.setattr(
        plugin_module, "_bambu_local_binding",
        lambda *_args: (
            {"source_instance_id": "fixture-instance-123456"},
            {"physical_printer_id": 3, "material_system_id": 7,
             "bridge_token": "fhpb_fixture"},
        ),
    )
    monkeypatch.setattr(
        plugin_module, "_material_commit_context",
        lambda *_args: (_immediate_device(), {}, {}, None),
    )
    monkeypatch.setattr(
        plugin_module, "_bambu_committed_spool_target",
        lambda *_args: (_bambu_material_target(), None),
    )
    monkeypatch.setattr(
        plugin_module, "apply_bambu_material_targets",
        lambda *_args, **_kwargs: {"ok": True, "report": {"gcode_state": "IDLE"}},
    )
    monkeypatch.setattr(plugin_module, "build_bambu_bridge_snapshot", lambda *_args: {})
    monkeypatch.setattr(
        plugin_module, "http_post_bridge_json", lambda *_args: (0, b"", None)
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_bambu_material_result",
        lambda _request_id, result: delivered.append(result),
    )

    catalog._do_bambu_material_immediate(
        "uncertain", "assign", 3, 7, "token", {}, commit,
        plugin_module.time.monotonic() + 20,
    )

    assert delivered[0]["ok"] is False
    assert delivered[0]["code"] == "snapshot_failed"
    assert delivered[0]["applied"] is True
    assert delivered[0]["observationUploaded"] is False

@pytest.mark.parametrize(
    "failure_code",
    ["printer_busy", "rfid_managed", "write_failed", "verification_failed"],
)
def test_bambu_immediate_boundary_never_turns_unconfirmed_write_into_delivery(
    plugin_module, monkeypatch, failure_code
):
    monkeypatch.setattr(
        plugin_module, "_bambu_local_binding",
        lambda *_args: (
            {"source_instance_id": "fixture-instance-123456"},
            {"physical_printer_id": 3, "material_system_id": 7,
             "bridge_token": "fhpb_fixture"},
        ),
    )
    monkeypatch.setattr(
        plugin_module, "_material_commit_context",
        lambda *_args: (_immediate_device(), {}, {}, None),
    )
    monkeypatch.setattr(
        plugin_module, "_bambu_committed_spool_target",
        lambda *_args: (_bambu_material_target(), None),
    )
    monkeypatch.setattr(
        plugin_module, "apply_bambu_material_targets",
        lambda *_args, **_kwargs: {"ok": False, "code": failure_code},
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_bambu_material_result",
        lambda _request_id, result: delivered.append(result),
    )

    catalog._do_bambu_material_immediate(
        "failure", "assign", 3, 7, "token", {}, _immediate_commit(),
        plugin_module.time.monotonic() + 20,
    )

    assert delivered[0]["ok"] is False
    assert delivered[0]["code"] == failure_code
    assert delivered[0]["applied"] is False

def test_bambu_immediate_expired_request_never_reads_or_writes_lan(
    plugin_module, monkeypatch
):
    monkeypatch.setattr(
        plugin_module, "_bambu_local_binding",
        lambda *_args: (
            {"source_instance_id": "fixture-instance-123456"},
            {"physical_printer_id": 3, "material_system_id": 7,
             "bridge_token": "fhpb_fixture"},
        ),
    )
    monkeypatch.setattr(
        plugin_module, "_material_commit_context",
        lambda *_args: pytest.fail("expired request must not reload or touch LAN"),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog, "_deliver_bambu_material_result",
        lambda _request_id, result: delivered.append(result),
    )

    catalog._do_bambu_material_immediate(
        "expired", "assign", 3, 7, "token", {}, _immediate_commit(),
        plugin_module.time.monotonic() - 1,
    )

    assert delivered[0]["code"] == "expired"
    assert delivered[0]["applied"] is False

def test_bambu_material_preview_uses_the_bambu_bridge_source_for_inventory(
    plugin_module, monkeypatch
):
    global_source = "global-plugin-source-1234"
    bambu_source = "bambu-bridge-source-1234"
    local = {"source_instance_id": bambu_source}
    binding = {
        "physical_printer_id": 3,
        "material_system_id": 7,
        "bridge_token": "fhpb_fixture",
    }
    events = []

    def local_binding(physical_printer_id, material_system_id):
        events.append(("binding", physical_printer_id, material_system_id))
        return local, binding

    requested_sources = []

    def inventory(path, token):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        source_instance_id = query["source_instance_id"][0]
        requested_sources.append(source_instance_id)
        events.append(("inventory", source_instance_id, token))
        return 200, {
            "source_instance_id": source_instance_id,
            "printers": [
                {
                    "id": 3,
                    "material_systems": [
                        {
                            "id": 7,
                            "provider": "bambu",
                            "slots": [],
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(plugin_module, "_bambu_local_binding", local_binding)
    monkeypatch.setattr(
        plugin_module, "plugin_source_instance_id", lambda: global_source
    )
    monkeypatch.setattr(plugin_module, "_filamenthub_json_get", inventory)
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _binding: ("SERIAL-1", _bambu_report(gcode_state="IDLE")),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_bambu_material_result",
        lambda request_id, result: delivered.append((request_id, result)),
    )

    catalog._do_bambu_material_action(
        "request-1", "preview", 3, 7, "plugin-token", {}
    )

    assert delivered[0][1]["ok"] is True
    assert events[:2] == [
        ("binding", 3, 7),
        ("inventory", bambu_source, "plugin-token"),
    ]

    inventory_result, inventory_error = plugin_module._happy_hare_server_inventory(
        "plugin-token"
    )
    assert inventory_error is None
    assert inventory_result["source_instance_id"] == global_source
    assert requested_sources == [bambu_source, global_source]

def test_bambu_material_preview_never_invents_an_unloaded_preset(plugin_module):
    assignments = [
        {
            "slot": 1,
            "preset_id": 41,
            "spool_id": 301,
            "source_ts": "2026-08-14T00:00:00Z",
        }
    ]

    changes, unresolved, targets = plugin_module._bambu_material_preview(
        _bambu_report(gcode_state="IDLE"), assignments, {}
    )

    assert changes == []
    assert unresolved == [{"slot": 1, "reason": "preset_not_loaded"}]
    assert targets == {}

def test_bambu_local_binding_is_private_and_replaceable(plugin_module, tmp_path, monkeypatch):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    identity = {"kind": "bambu_serial", "token": "a" * 64}

    plugin_module.configure_bambu_bridge(
        3, 4, "192.168.1.42", "local-secret", "SERIAL-1", "fhpb_first"
    )
    plugin_module.configure_bambu_bridge(
        3,
        5,
        "192.168.1.43",
        "new-secret",
        "SERIAL-2",
        "fhpb_second",
        identity,
    )

    stored = plugin_module.load_bambu_config()
    assert len(stored["printers"]) == 1
    assert stored["printers"][0]["material_system_id"] == 5
    assert stored["printers"][0]["access_code"] == "new-secret"
    assert stored["printers"][0]["bridge_token"] == "fhpb_second"
    assert stored["printers"][0]["device_identity"] == identity
    assert len(stored["source_instance_id"]) >= 16
    with pytest.raises(ValueError, match="already linked"):
        plugin_module.configure_bambu_bridge(
            8, 9, "192.168.1.44", "secret", "serial-2", "fhpb_duplicate"
        )
    with pytest.raises(ValueError, match="already linked"):
        plugin_module.configure_bambu_bridge(
            8,
            9,
            "192.168.1.44",
            "secret",
            "OTHER-SERIAL",
            "fhpb_duplicate",
            identity,
        )
    with pytest.raises(ValueError, match="invalid serial"):
        plugin_module.configure_bambu_bridge(
            9, 9, "192.168.1.44", "secret", "device/+/report", "fhpb_bad"
        )
    assert plugin_module.remove_bambu_bridge(3)
    assert plugin_module.load_bambu_config()["printers"] == []

def test_bambu_runtime_removes_local_secrets_after_server_rejects_binding(
    plugin_module, tmp_path, monkeypatch
):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    plugin_module.configure_bambu_bridge(
        3, 5, "192.168.1.43", "local-secret", "SERIAL-2", "fhpb_revoked"
    )
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("SERIAL-2", _bambu_report()),
    )
    monkeypatch.setattr(
        plugin_module,
        "http_post_bridge_json",
        lambda _path, _token, _payload: (401, b"", None),
    )
    monkeypatch.setattr(plugin_module, "http_get_bridge_json", lambda *_args: (404, b""))

    runtime = plugin_module.BambuBridgeRuntime()
    monkeypatch.setattr(runtime._wake, "wait", lambda _timeout: True)
    runtime._run()

    assert plugin_module.load_bambu_config()["printers"] == []

def test_bambu_runtime_deduplicates_stable_snapshots_and_uses_heartbeat(
    plugin_module, monkeypatch
):
    binding = {
        "physical_printer_id": 3,
        "material_system_id": 5,
        "bridge_token": "fhpb_live",
    }
    active = {"source_instance_id": "fixture-instance-0001", "printers": [binding]}
    configs = iter([active, active, active, {"source_instance_id": "x", "printers": []}])
    times = iter([1000.0, 1030.0, 1121.0])
    posts = []

    monkeypatch.setattr(plugin_module, "load_bambu_config", lambda: next(configs))
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("SERIAL-2", _bambu_report()),
    )
    monkeypatch.setattr(plugin_module.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(
        plugin_module,
        "http_post_bridge_json",
        lambda path, _token, _payload: posts.append(path) or (200, b"", None),
    )
    monkeypatch.setattr(
        plugin_module,
        "_prepare_bambu_observation",
        lambda config, serial: (
            {**config, "serial": serial},
            active["source_instance_id"],
        ),
    )

    runtime = plugin_module.BambuBridgeRuntime()
    monkeypatch.setattr(runtime._wake, "wait", lambda _timeout: False)
    runtime._run()

    assert posts == ["/printer-bridge/snapshot", "/printer-bridge/heartbeat"]

def test_bambu_runtime_fails_closed_when_the_printer_serial_changes(
    plugin_module, tmp_path, monkeypatch
):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    identity = plugin_module._bambu_device_identity("1" * 64, "EXPECTED-SERIAL")
    plugin_module.configure_bambu_bridge(
        3,
        5,
        "192.168.1.43",
        "local-secret",
        "EXPECTED-SERIAL",
        "fhpb_live",
        identity,
    )
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("OTHER-SERIAL", _bambu_report()),
    )
    posts = []
    monkeypatch.setattr(
        plugin_module,
        "http_post_bridge_json",
        lambda path, _token, _payload: posts.append(path) or (200, b"", None),
    )

    runtime = plugin_module.BambuBridgeRuntime()
    waits = 0

    def wait(_timeout):
        nonlocal waits
        waits += 1
        if waits > 1:
            runtime._stop.set()
        return False

    monkeypatch.setattr(runtime._wake, "wait", wait)
    runtime._run()

    assert posts == []
    assert plugin_module.load_bambu_config()["printers"][0]["serial"] == "EXPECTED-SERIAL"

def test_bambu_legacy_binding_learns_unique_serial_without_new_server_endpoint(
    plugin_module, tmp_path, monkeypatch
):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    plugin_module.configure_bambu_bridge(
        3, 5, "192.168.1.43", "local-secret", "", "fhpb_legacy"
    )
    monkeypatch.setattr(plugin_module, "http_get_bridge_json", lambda *_args: (404, b""))

    binding = plugin_module.load_bambu_config()["printers"][0]
    prepared, source_instance_id = plugin_module._prepare_bambu_observation(
        binding,
        "DISCOVERED-SERIAL",
    )

    assert prepared["serial"] == "DISCOVERED-SERIAL"
    assert "device_identity" not in prepared
    assert len(source_instance_id) >= 16
    assert plugin_module.load_bambu_config()["printers"][0] == prepared

def test_bambu_observation_persists_private_identity_without_uploading_serial(
    plugin_module, tmp_path, monkeypatch
):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    plugin_module.configure_bambu_bridge(
        3, 5, "192.168.1.43", "local-secret", "", "fhpb_live"
    )
    discovery_key = "2" * 64
    monkeypatch.setattr(
        plugin_module,
        "http_get_bridge_json",
        lambda path, token: (
            200,
            json.dumps({"printer_discovery_key": discovery_key}).encode("utf-8"),
        ),
    )

    binding = plugin_module.load_bambu_config()["printers"][0]
    prepared, source_instance_id = plugin_module._prepare_bambu_observation(
        binding,
        "PRIVATE-SERIAL",
    )
    snapshot = plugin_module.build_bambu_bridge_snapshot(
        prepared,
        source_instance_id,
        _bambu_report(),
    )

    assert snapshot["device_identity"] == plugin_module._bambu_device_identity(
        discovery_key,
        "PRIVATE-SERIAL",
    )
    assert "PRIVATE-SERIAL" not in json.dumps(snapshot)
    assert "PRIVATE-SERIAL" not in json.dumps(snapshot["device_identity"])

def test_bambu_discovered_serial_cannot_claim_an_existing_local_printer(
    plugin_module, tmp_path, monkeypatch
):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    plugin_module.configure_bambu_bridge(
        3, 5, "192.168.1.43", "first-secret", "SERIAL-1", "fhpb_first"
    )
    plugin_module.configure_bambu_bridge(
        4, 6, "192.168.1.44", "second-secret", "", "fhpb_second"
    )
    monkeypatch.setattr(plugin_module, "http_get_bridge_json", lambda *_args: (404, b""))

    second = plugin_module.load_bambu_config()["printers"][1]
    with pytest.raises(ValueError, match="already linked"):
        plugin_module._prepare_bambu_observation(second, "serial-1")

    stored = plugin_module.load_bambu_config()["printers"]
    assert stored[1]["serial"] == ""

def test_bambu_runtime_spreads_automatic_startup_but_wake_interrupts_it(
    plugin_module, monkeypatch
):
    waits = []
    runtime = plugin_module.BambuBridgeRuntime()

    def wait(timeout):
        waits.append(timeout)
        return True

    monkeypatch.setattr(runtime._wake, "wait", wait)
    monkeypatch.setattr(
        plugin_module,
        "load_bambu_config",
        lambda: {"source_instance_id": "fixture", "printers": []},
    )
    monkeypatch.setattr(plugin_module.random, "uniform", lambda lower, upper: upper)

    runtime._run()

    assert waits == [plugin_module.BAMBU_STARTUP_JITTER_SECONDS]

def test_bambu_runtime_stop_interrupts_startup_without_polling(
    plugin_module, monkeypatch
):
    runtime = plugin_module.BambuBridgeRuntime()
    original_wait = runtime._wake.wait
    waiting = threading.Event()
    reads = []

    def wait(timeout):
        waiting.set()
        return original_wait(timeout)

    monkeypatch.setattr(runtime._wake, "wait", wait)
    monkeypatch.setattr(
        plugin_module,
        "load_bambu_config",
        lambda: reads.append(True)
        or {"source_instance_id": "fixture", "printers": []},
    )
    monkeypatch.setattr(
        plugin_module.random,
        "uniform",
        lambda _lower, _upper: plugin_module.BAMBU_STARTUP_JITTER_SECONDS,
    )

    runtime.start()
    assert waiting.wait(2)
    runtime.stop(wait_timeout=2)

    assert reads == []
    assert runtime._thread is None

def test_bambu_runtime_does_not_upload_after_stop_during_lan_read(
    plugin_module, monkeypatch
):
    runtime = plugin_module.BambuBridgeRuntime()
    read_started = threading.Event()
    release_read = threading.Event()
    posts = []
    binding = {
        "physical_printer_id": 3,
        "material_system_id": 5,
        "bridge_token": "fhpb_live",
    }

    monkeypatch.setattr(runtime._wake, "wait", lambda _timeout: False)
    monkeypatch.setattr(plugin_module.random, "uniform", lambda lower, _upper: lower)
    monkeypatch.setattr(
        plugin_module,
        "load_bambu_config",
        lambda: {
            "source_instance_id": "fixture-instance-0001",
            "printers": [binding],
        },
    )

    def read_snapshot(_config):
        read_started.set()
        assert release_read.wait(2)
        return "SERIAL-2", _bambu_report()

    monkeypatch.setattr(plugin_module, "read_bambu_lan_snapshot", read_snapshot)
    monkeypatch.setattr(
        plugin_module,
        "http_post_bridge_json",
        lambda path, _token, _payload: posts.append(path) or (200, b"", None),
    )

    runtime.start()
    assert read_started.wait(2)
    runtime.stop(wait_timeout=0)
    release_read.set()
    runtime.stop(wait_timeout=2)

    assert posts == []
    assert runtime._thread is None

def test_bambu_runtime_stop_during_connect_prevents_tls_and_mqtt(
    plugin_module, monkeypatch
):
    runtime = plugin_module.BambuBridgeRuntime()
    connect_started = threading.Event()
    connect_release = threading.Event()
    tls_started = []
    binding = {
        "physical_printer_id": 3,
        "material_system_id": 5,
        "host": "printer.local",
        "access_code": "local-secret",
        "serial": "SERIAL-2",
        "bridge_token": "fhpb_live",
    }

    class RawSocket:
        closed = False

        def settimeout(self, _timeout):
            return None

        def connect(self, _sockaddr):
            connect_started.set()
            assert connect_release.wait(2)

        def close(self):
            self.closed = True

    class TlsContext:
        check_hostname = False
        verify_mode = None

        def wrap_socket(self, *_args, **_kwargs):
            tls_started.append(True)
            raise AssertionError("retired observer started TLS")

    raw = RawSocket()
    monkeypatch.setattr(runtime._wake, "wait", lambda _timeout: False)
    monkeypatch.setattr(plugin_module.random, "uniform", lambda lower, _upper: lower)
    monkeypatch.setattr(
        plugin_module,
        "load_bambu_config",
        lambda: {"source_instance_id": "fixture-instance-0001", "printers": [binding]},
    )
    monkeypatch.setattr(
        plugin_module,
        "_resolved_bambu_address",
        lambda _host: (2, 1, 6, ("192.168.1.42", 8883)),
    )
    monkeypatch.setattr(plugin_module.socket, "socket", lambda *_args: raw)
    monkeypatch.setattr(plugin_module.ssl, "SSLContext", lambda *_args: TlsContext())

    runtime.start()
    assert connect_started.wait(2)
    runtime.stop(wait_timeout=0)
    connect_release.set()
    runtime.stop(wait_timeout=2)

    assert tls_started == []
    assert raw.closed is True
    assert runtime._thread is None

def test_bambu_runtime_restarts_after_previous_generation_finishes(
    plugin_module, monkeypatch
):
    runtime = plugin_module.BambuBridgeRuntime()
    first_read_started = threading.Event()
    release_first_read = threading.Event()
    second_read_finished = threading.Event()
    read_count = 0
    read_lock = threading.Lock()

    monkeypatch.setattr(runtime._wake, "wait", lambda _timeout: False)
    monkeypatch.setattr(plugin_module.random, "uniform", lambda lower, _upper: lower)

    def load_config():
        nonlocal read_count
        with read_lock:
            read_count += 1
            current_read = read_count
        if current_read == 1:
            first_read_started.set()
            assert release_first_read.wait(2)
        else:
            second_read_finished.set()
        return {"source_instance_id": "fixture", "printers": []}

    monkeypatch.setattr(plugin_module, "load_bambu_config", load_config)

    runtime.start()
    assert first_read_started.wait(2)
    runtime.stop(wait_timeout=0)
    runtime.start()
    release_first_read.set()

    assert second_read_finished.wait(2)
    runtime.stop(wait_timeout=2)
    assert read_count == 2
    assert runtime._thread is None

def test_bambu_pair_is_revoked_when_local_binding_cannot_be_persisted(
    plugin_module, monkeypatch
):
    monkeypatch.setattr(plugin_module, "_resolved_bambu_address", lambda _host: "192.168.1.42")
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("SERIAL-2", _bambu_report()),
    )
    monkeypatch.setattr(
        plugin_module,
        "load_bambu_config",
        lambda: {"source_instance_id": "fixture-instance-0001", "printers": []},
    )
    monkeypatch.setattr(plugin_module, "save_bambu_config", lambda _payload: None)
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda *_args, **_kwargs: (
            200,
            json.dumps({"bridge_token": "fhpb_fresh-token", "physical_printer_id": 3, "material_system_id": 5}).encode("utf-8"),
        ),
    )
    monkeypatch.setattr(
        plugin_module,
        "configure_bambu_bridge",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    revoked = []
    removed = []
    monkeypatch.setattr(
        plugin_module,
        "revoke_fresh_bridge_token",
        lambda token: revoked.append(("/printer-bridge/connection", token)) or 204,
    )
    monkeypatch.setattr(
        plugin_module,
        "remove_bambu_bridge",
        lambda physical_printer_id: removed.append(physical_printer_id) or True,
    )
    monkeypatch.setattr(plugin_module, "ui_text", lambda key: key)
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_notice",
        lambda text, status="info": delivered.append((text, status)),
    )

    catalog._do_configure_bambu(3, 5, "printer.local", "secret", "", "pair-code")

    assert revoked == [("/printer-bridge/connection", "fhpb_fresh-token")]
    assert removed == []
    assert delivered == [("bambuInvalid", "error")]

@pytest.mark.parametrize(
    "statuses,expected,attempts",
    [
        ([0, 0, 204], 204, 3),
        ([0, 0, 0], 0, 3),
        ([401], 401, 1),
    ],
)
def test_fresh_bambu_token_revoke_has_bounded_retry(
    plugin_module, monkeypatch, tmp_path, statuses, expected, attempts
):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))
    remaining = iter(statuses)
    calls = []

    def delete(path, token, allow_retired_generation=False):
        calls.append((path, token, allow_retired_generation))
        return next(remaining)

    monkeypatch.setattr(plugin_module, "_http_delete_bridge", delete)

    assert plugin_module.revoke_fresh_bridge_token("fhpb_fresh") == expected
    assert calls == [
        ("/printer-bridge/connection", "fhpb_fresh", True)
    ] * attempts
    pending = plugin_module._load_pending_bambu_revokes()
    if expected in {204, 401}:
        assert pending == []
    else:
        assert len(pending) == 1
        assert pending[0]["token"] == "fhpb_fresh"
        assert set(pending[0]) == {
            "token",
            "created_at",
            "next_retry_at",
            "attempts",
        }

@pytest.mark.parametrize("success_status", [204, 401])
def test_pending_bambu_revoke_retries_fixed_endpoint_and_clears_on_success(
    plugin_module, monkeypatch, tmp_path, success_status
):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    config_path = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(config_path))
    now = 2_000_000_000.0
    assert plugin_module.queue_fresh_bambu_revoke(
        "fhpb_retired", now=now, attempts=3
    )
    plugin_module.configure_bambu_bridge(
        3, 5, "current.local", "current-secret", "SERIAL-2", "fhpb_current"
    )
    current = plugin_module.load_bambu_config()
    calls = []

    def delete(path, token, allow_retired_generation=False):
        calls.append((path, token, allow_retired_generation))
        return success_status

    monkeypatch.setattr(plugin_module, "_http_delete_bridge", delete)

    outcome = plugin_module.retry_pending_bambu_revokes(
        now=now + plugin_module.BAMBU_REVOKE_BACKOFF_INITIAL_SECONDS
    )

    assert outcome == {"retried": 1, "remaining": 0}
    assert calls == [
        ("/printer-bridge/connection", "fhpb_retired", True)
    ]
    assert plugin_module._load_pending_bambu_revokes(now=now + 61) == []
    assert plugin_module.load_bambu_config() == current

@pytest.mark.parametrize("state_kind", ["corrupt", "oversized"])
def test_pending_bambu_revoke_state_fails_closed_and_is_sanitized(
    plugin_module, monkeypatch, tmp_path, state_kind
):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))
    now = 2_000_000_000.0
    if state_kind == "corrupt":
        state_path.write_text("{broken", encoding="utf-8")
    else:
        state_path.write_bytes(
            b"x" * (plugin_module.BAMBU_REVOKE_STATE_MAX_BYTES + 1)
        )
    calls = []
    monkeypatch.setattr(
        plugin_module,
        "_http_delete_bridge",
        lambda *_args, **_kwargs: calls.append(True) or 204,
    )

    assert plugin_module.retry_pending_bambu_revokes(now=now) == {
        "retried": 0,
        "remaining": 0,
    }
    assert calls == []
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "pending": [],
    }

def test_old_pending_bambu_revoke_is_not_dropped_without_server_expiry(
    plugin_module, monkeypatch, tmp_path
):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))
    now = 2_000_000_000.0
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pending": [
                    {
                        "token": "fhpb_old-pending",
                        "created_at": now - 10 * 365 * 24 * 60 * 60,
                        "next_retry_at": now - 1,
                        "attempts": 300,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(
        plugin_module,
        "_http_delete_bridge",
        lambda path, token, allow_retired_generation=False: calls.append(
            (path, token, allow_retired_generation)
        )
        or 204,
    )

    assert len(plugin_module._load_pending_bambu_revokes(now=now)) == 1
    assert plugin_module.retry_pending_bambu_revokes(now=now) == {
        "retried": 1,
        "remaining": 0,
    }
    assert calls == [
        ("/printer-bridge/connection", "fhpb_old-pending", True)
    ]

def test_pending_bambu_revoke_rejects_unbounded_or_non_bridge_tokens(
    plugin_module, monkeypatch, tmp_path
):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))

    assert not plugin_module.queue_fresh_bambu_revoke("account-token")
    assert not plugin_module.queue_fresh_bambu_revoke("fhpb_" + "x" * 300)
    assert not state_path.exists()

def test_pending_bambu_revoke_state_is_written_private_and_minimal(
    plugin_module, monkeypatch, tmp_path
):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))
    writes = []
    original_write = plugin_module._write_bytes_atomic_unchecked

    def write(path, payload, mode=None):
        writes.append((path, json.loads(payload.decode("utf-8")), mode))
        return original_write(path, payload, mode=mode)

    monkeypatch.setattr(plugin_module, "_write_bytes_atomic_unchecked", write)

    assert plugin_module.queue_fresh_bambu_revoke(
        "fhpb_private", now=2_000_000_000.0
    )
    assert len(writes) == 1
    path, payload, mode = writes[0]
    assert path == str(state_path)
    assert mode == 0o600
    assert set(payload) == {"version", "pending"}
    assert set(payload["pending"][0]) == {
        "token",
        "created_at",
        "next_retry_at",
        "attempts",
    }

def test_pending_bambu_revoke_queue_never_evicts_when_full(
    plugin_module, monkeypatch, tmp_path
):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))
    now = 2_000_000_000.0
    tokens = [
        "fhpb_pending-%02d" % index
        for index in range(plugin_module.BAMBU_REVOKE_MAX_PENDING)
    ]
    for token in tokens:
        assert plugin_module.queue_fresh_bambu_revoke(token, now=now)

    assert not plugin_module.can_queue_fresh_bambu_revoke(now=now)
    assert not plugin_module.queue_fresh_bambu_revoke(
        "fhpb_would-be-lost", now=now
    )
    assert [
        item["token"]
        for item in plugin_module._load_pending_bambu_revokes(now=now)
    ] == tokens

def test_full_revoke_queue_rejects_pair_before_consuming_code(
    plugin_module, monkeypatch, tmp_path
):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    config_path = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(config_path))
    now = time.time()
    for index in range(plugin_module.BAMBU_REVOKE_MAX_PENDING):
        assert plugin_module.queue_fresh_bambu_revoke(
            "fhpb_pending-%02d" % index, now=now
        )
    monkeypatch.setattr(
        plugin_module, "_resolved_bambu_address", lambda _host: "192.168.1.42"
    )
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("SERIAL-2", _bambu_report()),
    )
    pair_calls = []
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda *_args, **_kwargs: pair_calls.append(True) or (500, b""),
    )
    notices = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_notice",
        lambda text, status="info": notices.append((text, status)),
    )

    catalog._do_configure_bambu(
        3, 5, "printer.local", "secret", "", "one-time-code"
    )

    assert pair_calls == []
    assert len(plugin_module._load_pending_bambu_revokes(now=now)) == (
        plugin_module.BAMBU_REVOKE_MAX_PENDING
    )
    assert notices[-1][1] == "error"

def test_enqueue_during_lifecycle_retries_without_reload(
    plugin_module, monkeypatch, tmp_path
):
    scheduler = _active_revoke_scheduler(
        plugin_module, monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        plugin_module, "BAMBU_REVOKE_BACKOFF_INITIAL_SECONDS", 0.02
    )
    revoked = threading.Event()
    monkeypatch.setattr(
        plugin_module,
        "_http_delete_bridge",
        lambda *_args, **_kwargs: revoked.set() or 204,
    )
    scheduler.start()
    try:
        assert plugin_module.queue_fresh_bambu_revoke("fhpb_live-enqueue")
        assert revoked.wait(2)
        deadline = time.time() + 2
        while plugin_module._load_pending_bambu_revokes() and time.time() < deadline:
            time.sleep(0.01)
        assert plugin_module._load_pending_bambu_revokes() == []
    finally:
        scheduler.stop()

def test_failed_scheduled_revoke_reschedules_with_backoff(
    plugin_module, monkeypatch, tmp_path
):
    scheduler = _active_revoke_scheduler(
        plugin_module, monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        plugin_module, "BAMBU_REVOKE_BACKOFF_INITIAL_SECONDS", 0.01
    )
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_BACKOFF_MAX_SECONDS", 0.03)
    calls = []
    revoked = threading.Event()

    def delete(*_args, **_kwargs):
        calls.append(time.monotonic())
        if len(calls) <= plugin_module.BAMBU_REVOKE_ATTEMPTS:
            return 0
        revoked.set()
        return 204

    monkeypatch.setattr(plugin_module, "_http_delete_bridge", delete)
    scheduler.start()
    try:
        assert plugin_module.queue_fresh_bambu_revoke("fhpb_retry-backoff")
        assert revoked.wait(2)
        assert len(calls) == plugin_module.BAMBU_REVOKE_ATTEMPTS + 1
        assert calls[-1] > calls[plugin_module.BAMBU_REVOKE_ATTEMPTS - 1]
    finally:
        scheduler.stop()

def test_revoke_scheduler_stop_cancels_waiting_retry(
    plugin_module, monkeypatch, tmp_path
):
    scheduler = _active_revoke_scheduler(
        plugin_module, monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        plugin_module, "BAMBU_REVOKE_BACKOFF_INITIAL_SECONDS", 0.25
    )
    calls = []
    monkeypatch.setattr(
        plugin_module,
        "_http_delete_bridge",
        lambda *_args, **_kwargs: calls.append(True) or 204,
    )
    scheduler.start()
    assert plugin_module.queue_fresh_bambu_revoke("fhpb_cancel-on-unload")
    scheduler.stop()
    time.sleep(0.35)

    assert calls == []
    assert len(plugin_module._load_pending_bambu_revokes()) == 1

def test_revoke_scheduler_stop_during_delete_does_not_start_next_token(
    plugin_module, monkeypatch, tmp_path
):
    scheduler = _active_revoke_scheduler(
        plugin_module, monkeypatch, tmp_path
    )
    now = time.time()
    state_path = Path(plugin_module.BAMBU_REVOKE_FILE)
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pending": [
                    {
                        "token": "fhpb_first-due",
                        "created_at": now - 10,
                        "next_retry_at": now - 1,
                        "attempts": 3,
                    },
                    {
                        "token": "fhpb_second-due",
                        "created_at": now - 10,
                        "next_retry_at": now - 1,
                        "attempts": 3,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    first_started = threading.Event()
    first_release = threading.Event()
    calls = []

    def delete(_path, token, allow_retired_generation=False):
        calls.append((token, allow_retired_generation))
        if token == "fhpb_first-due":
            first_started.set()
            assert first_release.wait(2)
            return 204
        raise AssertionError("scheduler started a new token after stop")

    monkeypatch.setattr(plugin_module, "_http_delete_bridge", delete)
    scheduler.start()
    assert first_started.wait(2)
    scheduler.stop()
    first_release.set()
    deadline = time.time() + 2
    while scheduler._running and time.time() < deadline:
        time.sleep(0.01)

    assert scheduler._running is False
    assert calls == [("fhpb_first-due", True)]
    pending = plugin_module._load_pending_bambu_revokes()
    assert [item["token"] for item in pending] == ["fhpb_second-due"]

def test_revoke_scheduler_restores_pending_retry_on_reload(
    plugin_module, monkeypatch, tmp_path
):
    scheduler = _active_revoke_scheduler(
        plugin_module, monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        plugin_module, "BAMBU_REVOKE_BACKOFF_INITIAL_SECONDS", 0.02
    )
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_ACTIVE", False)
    assert plugin_module.queue_fresh_bambu_revoke("fhpb_restore-on-load")
    revoked = threading.Event()
    monkeypatch.setattr(
        plugin_module,
        "_http_delete_bridge",
        lambda *_args, **_kwargs: revoked.set() or 204,
    )
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_ACTIVE", True)

    scheduler.start()
    try:
        assert revoked.wait(2)
        deadline = time.time() + 2
        while plugin_module._load_pending_bambu_revokes() and time.time() < deadline:
            time.sleep(0.01)
        assert plugin_module._load_pending_bambu_revokes() == []
    finally:
        scheduler.stop()

def test_bambu_pair_is_revoked_after_unload_before_local_persist(
    plugin_module, tmp_path, monkeypatch
):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    plugin_module.configure_bambu_bridge(
        9,
        10,
        "existing.local",
        "existing-secret",
        "EXISTING-SERIAL",
        "fhpb_existing",
    )
    existing = plugin_module.load_bambu_config()["printers"]
    monkeypatch.setattr(
        plugin_module, "_resolved_bambu_address", lambda _host: "192.168.1.42"
    )
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("SERIAL-2", _bambu_report()),
    )
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda *_args, **_kwargs: (
            200,
            json.dumps(
                {
                    "bridge_token": "fhpb_fresh-token",
                    "physical_printer_id": 3,
                    "material_system_id": 5,
                    "printer_discovery_key": "1" * 64,
                }
            ).encode("utf-8"),
        ),
    )
    persist_entered = threading.Event()
    persist_release = threading.Event()
    original_configure = plugin_module.configure_bambu_bridge

    def blocked_configure(*args, **kwargs):
        persist_entered.set()
        assert persist_release.wait(2)
        return original_configure(*args, **kwargs)

    monkeypatch.setattr(plugin_module, "configure_bambu_bridge", blocked_configure)
    revoked = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcode(self):
            return 204

    def urlopen(request, **_kwargs):
        revoked.append(
            (
                request.full_url,
                request.get_header("X-filamenthub-bridge-token"),
                request.get_method(),
            )
        )
        return Response()

    monkeypatch.setattr(plugin_module.urllib.request, "urlopen", urlopen)
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-bambu-pair-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    finished = threading.Event()
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver_notice", lambda *_args, **_kwargs: None)

    def configure_job():
        try:
            catalog._do_configure_bambu(
                3, 5, "printer.local", "secret", "", "pair-code"
            )
        finally:
            finished.set()

    assert worker.submit(configure_job)
    assert persist_entered.wait(2)
    worker.stop(wait_timeout=0)
    worker.activate()
    persist_release.set()

    assert finished.wait(2)
    assert revoked == [
        (
            plugin_module.API_BASE + "/printer-bridge/connection",
            "fhpb_fresh-token",
            "DELETE",
        )
    ]
    assert plugin_module.load_bambu_config()["printers"] == existing
    worker.stop()

def test_bambu_pair_removes_invalidated_binding_when_unload_follows_atomic_write(
    plugin_module, tmp_path, monkeypatch
):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    plugin_module.configure_bambu_bridge(
        3,
        4,
        "old.local",
        "old-secret",
        "OLD-SERIAL",
        "fhpb_old",
    )
    previous = plugin_module.load_bambu_config()["printers"]
    monkeypatch.setattr(
        plugin_module, "_resolved_bambu_address", lambda _host: "192.168.1.42"
    )
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("NEW-SERIAL", _bambu_report()),
    )
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda *_args, **_kwargs: (
            200,
            json.dumps(
                {
                    "bridge_token": "fhpb_fresh-token",
                    "physical_printer_id": 3,
                    "material_system_id": 5,
                    "printer_discovery_key": "1" * 64,
                }
            ).encode("utf-8"),
        ),
    )
    persist_entered = threading.Event()
    persist_release = threading.Event()
    original_replace = plugin_module.os.replace

    def replace(source, destination):
        payload = Path(source).read_bytes()
        if (
            Path(destination) == target
            and b"fhpb_fresh-token" in payload
            and not persist_entered.is_set()
        ):
            persist_entered.set()
            assert persist_release.wait(2)
        return original_replace(source, destination)

    monkeypatch.setattr(plugin_module.os, "replace", replace)
    revoked = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcode(self):
            return 204

    def urlopen(request, **_kwargs):
        revoked.append(
            (
                request.full_url,
                request.get_header("X-filamenthub-bridge-token"),
                request.get_method(),
            )
        )
        return Response()

    monkeypatch.setattr(plugin_module.urllib.request, "urlopen", urlopen)
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-bambu-atomic-pair-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    finished = threading.Event()
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver_notice", lambda *_args, **_kwargs: None)

    def configure_job():
        try:
            catalog._do_configure_bambu(
                3, 5, "new.local", "new-secret", "", "pair-code"
            )
        finally:
            finished.set()

    assert worker.submit(configure_job)
    assert persist_entered.wait(2)
    worker.stop(wait_timeout=0)
    worker.activate()
    persist_release.set()

    assert finished.wait(2)
    assert revoked == [
        (
            plugin_module.API_BASE + "/printer-bridge/connection",
            "fhpb_fresh-token",
            "DELETE",
        )
    ]
    assert previous[0]["bridge_token"] == "fhpb_old"
    assert plugin_module.load_bambu_config()["printers"] == []
    worker.stop()

def test_bambu_pair_response_after_unload_cannot_restart_observer(
    plugin_module, tmp_path, monkeypatch
):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    monkeypatch.setattr(
        plugin_module, "_resolved_bambu_address", lambda _host: "192.168.1.42"
    )
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("SERIAL-2", _bambu_report()),
    )
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda *_args, **_kwargs: (
            200,
            json.dumps(
                {
                    "bridge_token": "fhpb_fresh-token",
                    "physical_printer_id": 3,
                    "material_system_id": 5,
                    "printer_discovery_key": "2" * 64,
                }
            ).encode("utf-8"),
        ),
    )
    snapshot_started = threading.Event()
    snapshot_release = threading.Event()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcode(self):
            return 200

        def read(self, _size=-1):
            snapshot_started.set()
            assert snapshot_release.wait(2)
            return b"{}"

    monkeypatch.setattr(
        plugin_module.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(),
    )
    wakes = []
    monkeypatch.setattr(
        plugin_module.BAMBU_BRIDGE_RUNTIME,
        "wake",
        lambda: wakes.append(True),
    )
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-bambu-response-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    finished = threading.Event()
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver_notice", lambda *_args, **_kwargs: None)

    def configure_job():
        try:
            catalog._do_configure_bambu(
                3, 5, "printer.local", "secret", "", "pair-code"
            )
        finally:
            finished.set()

    assert worker.submit(configure_job)
    assert snapshot_started.wait(2)
    worker.stop(wait_timeout=0)
    worker.activate()
    snapshot_release.set()

    assert finished.wait(2)
    assert wakes == []
    worker.stop()

@pytest.mark.parametrize("paired_printer,paired_system", [(3, 5), (4, 5), (3, 6)])
def test_fresh_bambu_pair_and_first_snapshot_share_one_source_identity(
    plugin_module, tmp_path, monkeypatch, paired_printer, paired_system
):
    monkeypatch.setattr(plugin_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        plugin_module, "SYNC_STATE_FILE", str(tmp_path / ".fh_sync.json")
    )
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    monkeypatch.setattr(plugin_module, "_resolved_bambu_address", lambda _host: "192.168.1.42")
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("SERIAL-2", _bambu_report()),
    )
    captured = {}
    discovery_key = "3" * 64

    def pair(_path, _token, payload):
        captured["pair_source"] = payload["source_instance_id"]
        captured["pair_payload"] = payload
        return 200, json.dumps(
            {
                "bridge_token": "fhpb_fresh-token",
                "physical_printer_id": paired_printer,
                "material_system_id": paired_system,
                "printer_discovery_key": discovery_key,
            }
        ).encode("utf-8")

    def snapshot(_path, _token, payload):
        captured["snapshot_source"] = payload["source_instance_id"]
        captured["snapshot_payload"] = payload
        return 200, b"{}", None

    monkeypatch.setattr(plugin_module, "http_post_json", pair)
    revoked = []
    monkeypatch.setattr(
        plugin_module,
        "revoke_fresh_bridge_token",
        lambda token: revoked.append(("/printer-bridge/connection", token)) or 204,
    )
    monkeypatch.setattr(plugin_module, "http_post_bridge_json", snapshot)
    monkeypatch.setattr(plugin_module.BAMBU_BRIDGE_RUNTIME, "wake", lambda: None)
    monkeypatch.setattr(plugin_module, "ui_text", lambda key: key)
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_notice",
        lambda text, status="info": delivered.append((text, status)),
    )

    previous = []
    if (paired_printer, paired_system) != (3, 5):
        plugin_module.configure_bambu_bridge(3, 5, "previous.local", "old-secret", "OLD-SERIAL", "fhpb_previous")
        previous = plugin_module.load_bambu_config()["printers"]
    catalog._do_configure_bambu(3, 5, "printer.local", "secret", "", "pair-code")

    if (paired_printer, paired_system) != (3, 5):
        assert revoked == [("/printer-bridge/connection", "fhpb_fresh-token")]
        assert "snapshot_source" not in captured
        assert plugin_module.load_bambu_config()["printers"] == previous
        assert delivered == [("bambuPairingFailed", "error")]
        return
    assert revoked == []
    assert captured["pair_source"] == captured["snapshot_source"]
    assert "SERIAL-2" not in json.dumps(captured["pair_payload"])
    assert "SERIAL-2" not in json.dumps(captured["snapshot_payload"])
    assert captured["snapshot_payload"]["device_identity"] == (
        plugin_module._bambu_device_identity(discovery_key, "SERIAL-2")
    )
    stored = plugin_module.load_bambu_config()
    assert stored["source_instance_id"] == captured["pair_source"]
    assert len(stored["printers"]) == 1
    assert stored["printers"][0]["device_identity"] == (
        captured["snapshot_payload"]["device_identity"]
    )
    assert delivered == [("bambuSaved", "success")]

def test_bambu_pair_identity_conflict_revokes_the_new_connection(
    plugin_module, tmp_path, monkeypatch
):
    target = tmp_path / ".fh_bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(target))
    monkeypatch.setattr(plugin_module, "_resolved_bambu_address", lambda _host: "192.168.1.42")
    monkeypatch.setattr(
        plugin_module,
        "read_bambu_lan_snapshot",
        lambda _config: ("SERIAL-2", _bambu_report()),
    )
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda *_args: (
            200,
            json.dumps(
                {
                    "bridge_token": "fhpb_conflict",
                    "physical_printer_id": 3,
                    "material_system_id": 5,
                    "printer_discovery_key": "4" * 64,
                }
            ).encode("utf-8"),
        ),
    )
    monkeypatch.setattr(
        plugin_module,
        "http_post_bridge_json",
        lambda *_args: (409, b"{}", None),
    )
    revoked = []
    monkeypatch.setattr(
        plugin_module,
        "revoke_fresh_bridge_token",
        lambda token: revoked.append(("/printer-bridge/connection", token)) or 204,
    )
    monkeypatch.setattr(plugin_module, "ui_text", lambda key: key)
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_notice",
        lambda text, status="info": delivered.append((text, status)),
    )

    catalog._do_configure_bambu(3, 5, "printer.local", "secret", "", "pair-code")

    assert revoked == [("/printer-bridge/connection", "fhpb_conflict")]
    assert plugin_module.load_bambu_config()["printers"] == []
    assert delivered == [("bambuPairingFailed", "error")]

def test_bambu_address_must_resolve_to_the_lan(plugin_module, monkeypatch):
    def public(*_args, **_kwargs):
        return [(2, 1, 6, "", ("8.8.8.8", 8883))]

    monkeypatch.setattr(plugin_module.socket, "getaddrinfo", public)
    with pytest.raises(ValueError, match="local network"):
        plugin_module._resolved_bambu_address("printer.example")

    def private(*_args, **_kwargs):
        return [(2, 1, 6, "", ("192.168.1.42", 8883))]

    monkeypatch.setattr(plugin_module.socket, "getaddrinfo", private)
    resolved = plugin_module._resolved_bambu_address("bambu.local")
    assert resolved[3] == ("192.168.1.42", 8883)
