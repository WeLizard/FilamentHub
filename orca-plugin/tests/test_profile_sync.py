"""Printer, process and filament profile transport contracts."""

from .filamenthub_plugin_test_support import (
    _isolate_profile_identity,
    json,
    pytest,
    SimpleNamespace,
)


def test_custom_machine_child_imports_only_technical_delta(
    plugin_module, monkeypatch
):
    class Preset:
        is_system = False

        def __init__(self, name, values, *, user):
            self.name = name
            self.bundle_id = "user" if user else "Voron"
            self._values = values
            self._user = user

        def is_user(self):
            return self._user

        def config_keys(self):
            return list(self._values)

        def config_value(self, key):
            return self._values.get(key)

    parent_values = {
        "printer_settings_id": "Voron 2.4 350 0.4 nozzle",
        "printer_model": "Voron 2.4 350",
        "nozzle_diameter": ["0.4"],
        "machine_max_acceleration_x": ["8000"],
    }
    parent = Preset("Voron 2.4 350 0.4 nozzle", parent_values, user=False)
    child = Preset(
        "Fast workshop Voron",
        {
            **parent_values,
            "inherits": parent.name,
            "machine_max_acceleration_x": ["12000"],
            "print_host": "192.168.1.21:7125",
            "printhost_apikey": "must-never-leave-orca",
            "bbl_use_printhost": "1",
        },
        user=True,
    )
    collection = SimpleNamespace(
        size=lambda: 2,
        preset=lambda index: [parent, child][index],
        find_preset=lambda name: parent if name == parent.name else None,
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(printers=collection),
        raising=False,
    )

    profiles = plugin_module.scan_user_profiles("machine")

    assert len(profiles) == 1
    assert profiles[0]["settings"] == {
        "machine_max_acceleration_x": ["12000"],
        "inherits": parent.name,
    }
    assert "print_host" not in profiles[0]["settings"]
    assert "printhost_apikey" not in profiles[0]["settings"]
    assert "bbl_use_printhost" not in profiles[0]["settings"]

def test_child_with_unavailable_parent_is_not_flattened_into_a_custom_profile(
    plugin_module, monkeypatch
):
    class Preset:
        is_system = False
        name = "Temporarily orphaned Voron"
        bundle_id = "user"

        @staticmethod
        def is_user():
            return True

        @staticmethod
        def config_keys():
            return [
                "inherits",
                "printer_settings_id",
                "printer_model",
                "machine_max_acceleration_x",
                "print_host",
            ]

        @staticmethod
        def config_value(key):
            return {
                "inherits": "Missing vendor parent",
                "printer_settings_id": "Missing vendor parent",
                "printer_model": "Voron 2.4 350",
                "machine_max_acceleration_x": ["8000"],
                "print_host": "192.168.1.21:7125",
            }[key]

    child = Preset()
    collection = SimpleNamespace(
        size=lambda: 1,
        preset=lambda _index: child,
        find_preset=lambda _name: None,
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(
            printers=collection,
            current_printer_preset=lambda: child,
        ),
        raising=False,
    )

    assert plugin_module.scan_user_profiles("machine") == []
    observation = plugin_module.observe_printer_presets()[0]
    assert observation["inherits"] == "Missing vendor parent"
    assert observation["has_technical_changes"] is None
    assert observation["profile_fingerprint"] is None

def test_printer_observations_keep_two_endpoints_using_one_profile(
    plugin_module, monkeypatch
):
    class Preset:
        is_system = False

        def __init__(self, name, host):
            self.name = name
            self.bundle_id = "user"
            self._host = host

        @staticmethod
        def is_user():
            return True

        def config_value(self, key):
            return {
                "printer_settings_id": "shared-voron-profile",
                "printer_model": "Voron 2.4 350",
                "print_host": self._host,
                "host_type": "moonraker",
                "nozzle_diameter": ["0.4"],
            }.get(key)

    presets = [
        Preset("Workshop left", "192.168.1.21:7125"),
        Preset("Workshop right", "192.168.1.22:7125"),
    ]
    collection = SimpleNamespace(
        size=lambda: len(presets),
        preset=lambda index: presets[index],
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(
            printers=collection,
            current_printer_preset=lambda: presets[0],
        ),
        raising=False,
    )

    observations = plugin_module.observe_printer_presets()

    assert [(item["preset_name"], item["print_host"]) for item in observations] == [
        ("Workshop left", "192.168.1.21:7125"),
        ("Workshop right", "192.168.1.22:7125"),
    ]

def test_printer_observations_keep_separate_named_user_profiles_without_hosts(
    plugin_module, monkeypatch
):
    def preset(name):
        values = {
            "printer_settings_id": "shared-p2s-profile",
            "printer_model": "Bambu Lab P2S",
            "nozzle_diameter": ["0.4"],
        }
        return SimpleNamespace(
            name=name,
            bundle_id="user",
            is_system=False,
            is_user=lambda: True,
            config_value=lambda key: values.get(key),
        )

    presets = [preset("P2S workshop"), preset("P2S home")]
    collection = SimpleNamespace(
        size=lambda: len(presets),
        preset=lambda index: presets[index],
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(
            printers=collection,
            current_printer_preset=lambda: presets[0],
        ),
        raising=False,
    )

    observations = plugin_module.observe_printer_presets()

    assert [item["preset_name"] for item in observations] == [
        "P2S workshop",
        "P2S home",
    ]

def test_printer_observations_send_visible_system_profiles_but_not_the_whole_bundle(
    plugin_module, monkeypatch
):
    def preset(name, model, *, visible=False):
        values = {
            "printer_model": model,
            "nozzle_diameter": ["0.4"],
        }
        return SimpleNamespace(
            name=name,
            bundle_id="BBL",
            is_system=True,
            is_visible=visible,
            is_user=lambda: False,
            config_value=lambda key: values.get(key),
        )

    selected = preset(
        "Bambu Lab P2S 0.4 nozzle", "Bambu Lab P2S", visible=True
    )
    other_bundle_profiles = [
        preset("Bambu Lab A1 0.4 nozzle", "Bambu Lab A1", visible=True),
        preset("Bambu Lab X1 Carbon 0.4 nozzle", "Bambu Lab X1 Carbon"),
    ]
    presets = other_bundle_profiles + [selected]
    collection = SimpleNamespace(
        size=lambda: len(presets),
        preset=lambda index: presets[index],
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(
            printers=collection,
            current_printer_preset=lambda: selected,
        ),
        raising=False,
    )

    observations = plugin_module.observe_printer_presets()

    assert [item["preset_name"] for item in observations] == [
        "Bambu Lab A1 0.4 nozzle",
        selected.name,
    ]
    assert all(item["is_visible"] for item in observations)

def test_profile_sync_still_excludes_a_selected_filamenthub_copy(
    plugin_module, monkeypatch
):
    managed = SimpleNamespace(
        name="Restored printer",
        bundle_id="filamenthub:machine:41",
        is_user=lambda: False,
        config_keys=lambda: ["printer_settings_id"],
        config_value=lambda _key: "Restored printer",
    )
    collection = SimpleNamespace(size=lambda: 1, preset=lambda _index: managed)
    bundle = SimpleNamespace(
        printers=collection,
        current_printer_preset=lambda: managed,
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: bundle,
        raising=False,
    )

    assert plugin_module.scan_user_profiles("machine") == []

def test_profile_payload_must_be_an_object(plugin_module):
    with pytest.raises(ValueError, match="JSON object"):
        plugin_module.validate_filament_profile([])
    with pytest.raises(ValueError, match="non-empty string"):
        plugin_module.validate_filament_profile({"name": ""})
    profile = {"name": "PLA", "inherits": "Generic PLA"}
    assert plugin_module.validate_filament_profile(profile) is profile

def test_profile_payload_must_survive_the_orca_config_loader(plugin_module):
    # Observed on build PR14992/5e6895dd: a numeric array, a numeric scalar and
    # the internal `enrichment` object each made Orca discard the whole preset
    # ("invalid json array for ..." / "invalid json type for ...") while the file
    # stayed on disk looking synced.
    rejected = {
        "name": "PETG",
        "fan_max_speed": [100],
        "filament_max_volumetric_speed": 10,
        "enrichment": {"material_type": "PETG"},
        "filament_notes": None,
    }
    assert plugin_module.orca_transport_violations(rejected) == [
        "enrichment",
        "fan_max_speed",
        "filament_max_volumetric_speed",
        "filament_notes",
    ]
    with pytest.raises(ValueError, match="fan_max_speed"):
        plugin_module.validate_filament_profile(rejected)

    accepted = {
        "name": "PETG",
        "fan_max_speed": ["100"],
        "filament_max_volumetric_speed": ["10"],
        "compatible_printers": [],
        "inherits": "Generic PETG",
    }
    assert plugin_module.validate_filament_profile(accepted) is accepted

def test_unloadable_server_profile_never_replaces_a_working_local_file(
    plugin_module, monkeypatch, tmp_path
):
    good = {"name": "Managed PETG", "bundle_id": "filamenthub:7", "filament_type": ["PETG"]}
    path = tmp_path / "Managed PETG.json"
    path.write_text(json.dumps(good), encoding="utf-8")

    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda path, token=None, **kwargs: (
            200,
            json.dumps({"name": "Managed PETG", "fan_max_speed": [100]}).encode("utf-8"),
        ),
    )

    result = plugin_module.FilamentHubCatalog()._pull_one(
        7, "token", set(), str(tmp_path), {"updated_at": "2026-08-15"}
    )

    assert result is None
    assert json.loads(path.read_text(encoding="utf-8")) == good

def test_locally_unloadable_managed_file_is_repaired_from_the_server(
    plugin_module, monkeypatch, tmp_path
):
    # A file Orca refused is never stale by hash or timestamp, so without this
    # branch the broken copy would survive every future sync — and pushing it
    # would send the damage back to FilamentHub.
    live = tmp_path / "live"
    live.mkdir()
    broken = {"name": "Broken", "bundle_id": "filamenthub:12", "fan_max_speed": [100]}
    broken_path = live / "Broken.json"
    broken_path.write_text(json.dumps(broken), encoding="utf-8")
    repaired = {"name": "Broken", "fan_max_speed": ["100"], "filament_type": ["PETG"]}

    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(live))
    monkeypatch.setattr(
        plugin_module,
        "managed_preset_quarantine_dir",
        lambda: str(tmp_path / "quarantine"),
    )
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(
        plugin_module,
        "load_sync_state",
        lambda: {"12": {"updated_at": "2026-08-15", "hash": plugin_module.preset_content_hash(broken), "name": "Broken"}},
    )
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda value: None)

    def fake_http_get(path, token=None, **kwargs):
        if path.endswith("orcaslicer.json"):
            return 200, json.dumps(repaired).encode("utf-8")
        return 200, json.dumps(
            {"items": [{"id": 12, "name": "Broken", "updated_at": "2026-08-15"}]}
        ).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_get", fake_http_get)
    monkeypatch.setattr(
        plugin_module,
        "_sync_preferences",
        lambda token: {
            "available": True,
            "auto_import_local_presets": False,
            "sync_printer_endpoints": False,
            "allow_filament_presets_import": True,
            "allow_filament_presets_export": True,
            "allow_printer_profiles_import": True,
            "allow_printer_profiles_export": True,
            "allow_print_profiles_import": True,
            "allow_print_profiles_export": True,
        },
    )
    monkeypatch.setattr(plugin_module, "push_user_profiles", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr(
        plugin_module, "send_printer_observations", lambda *args, **kwargs: (None, {})
    )
    monkeypatch.setattr(plugin_module, "sync_happy_hare_topologies", lambda *args: None)
    pushed = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_push_one", lambda *args, **kwargs: pushed.append(args))

    catalog._do_sync("token", set(), announce=False, source_instance_id="fixture")

    assert pushed == []
    repaired_path = live / "PETG • Broken.json"
    written = json.loads(repaired_path.read_text(encoding="utf-8"))
    assert written["fan_max_speed"] == ["100"]
    assert written["name"] == "PETG • Broken"
    assert plugin_module.orca_transport_violations(written) == []

def test_sync_reports_written_files_and_host_loaded_presets_separately(
    plugin_module, monkeypatch, tmp_path
):
    # A file written during this session only reaches Orca after a restart, and
    # one Orca refused never arrives. The log must not present the file count as
    # the number of presets OrcaSlicer actually has.
    live = tmp_path / "live"
    live.mkdir()
    for preset_id, name in ((10, "Loaded"), (11, "Pending")):
        (live / f"{name}.json").write_text(
            json.dumps({"name": name, "bundle_id": "filamenthub:%d" % preset_id}),
            encoding="utf-8",
        )

    messages = []
    monkeypatch.setattr(plugin_module, "fh_log", lambda msg: messages.append(msg))
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(live))

    catalog = plugin_module.FilamentHubCatalog()
    catalog._log_managed_preset_state(str(live), {10, 11}, {10}, [11])

    assert any("sync failed presets: [11]" in msg for msg in messages)
    assert any(
        "desired=2 files=2 loaded=1 pending_restart=[11]" in msg for msg in messages
    )

    messages.clear()
    catalog._log_managed_preset_state(str(live), {10, 11}, None, [])
    assert any("desired=2 files=2 loaded=unknown" in msg for msg in messages)

def test_filament_sync_reports_device_scoped_partial_result(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "live"
    live.mkdir()
    profiles = {
        10: {"name": "Loaded", "bundle_id": "filamenthub:10"},
        12: {"name": "Rejected", "bundle_id": "filamenthub:12"},
        20: {"name": "No longer desired", "bundle_id": "filamenthub:20"},
    }
    for preset_id, profile in profiles.items():
        (live / (profile["name"] + ".json")).write_text(
            json.dumps(profile), encoding="utf-8"
        )
    state = {
        str(preset_id): {
            "updated_at": "2026-08-01",
            "hash": plugin_module.preset_content_hash(profile),
            "name": profile["name"],
        }
        for preset_id, profile in profiles.items()
    }
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(live))
    monkeypatch.setattr(
        plugin_module,
        "managed_preset_quarantine_dir",
        lambda: str(tmp_path / "quarantine"),
    )
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(plugin_module, "load_sync_state", lambda: state)
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda _value: None)
    monkeypatch.setattr(
        plugin_module,
        "_sync_preferences",
        lambda _token: {
            "available": True,
            "auto_import_local_presets": False,
            "sync_printer_endpoints": False,
            "allow_filament_presets_import": False,
            "allow_filament_presets_export": True,
            "allow_printer_profiles_import": False,
            "allow_printer_profiles_export": False,
            "allow_print_profiles_import": False,
            "allow_print_profiles_export": False,
        },
    )
    remote_items = [
        {"id": preset_id, "name": name, "updated_at": "2026-08-01"}
        for preset_id, name in (
            (10, "Loaded"),
            (11, "New"),
            (12, "Rejected"),
            (13, "Write failure"),
        )
    ]
    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda path, token=None: (
            200,
            json.dumps({"items": remote_items}).encode("utf-8"),
        ),
    )
    posted = []
    report_id = "11111111-1111-4111-8111-111111111111"

    def post(path, _token, payload):
        posted.append((path, payload))
        if path == "/orcaslicer/sync-plan":
            return 200, json.dumps(
                {"sync_version": 4, "report_id": report_id}
            ).encode("utf-8")
        if path == "/orcaslicer/sync-complete/chunk":
            return 200, json.dumps(
                {
                    "sync_version": 4,
                    "report_id": report_id,
                    "chunk_index": payload["chunk_index"],
                    "received_chunks": 1,
                    "chunk_count": payload["chunk_count"],
                    "complete": True,
                    "duplicate": False,
                }
            ).encode("utf-8")
        raise AssertionError(path)

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    catalog = plugin_module.FilamentHubCatalog()

    def pull(preset_id, _token, _known, folder, remote):
        if preset_id == 13:
            return None
        profile = {"name": remote["name"], "bundle_id": "filamenthub:%d" % preset_id}
        path = plugin_module.preset_file_path(folder, remote["name"], preset_id)
        plugin_module.write_bytes_atomic(
            path, json.dumps(profile).encode("utf-8")
        )
        return {
            "updated_at": remote["updated_at"],
            "hash": plugin_module.preset_content_hash(profile),
            "name": remote["name"],
        }

    monkeypatch.setattr(catalog, "_pull_one", pull)

    catalog._do_sync(
        "token",
        set(),
        announce=False,
        source_instance_id="device-a",
        loaded_preset_ids={10},
        scope="filament",
        operation_id="sync-a",
    )

    assert [path for path, _payload in posted] == [
        "/orcaslicer/sync-plan",
        "/orcaslicer/sync-complete/chunk",
    ]
    report = posted[1][1]
    assert report["device_fingerprint"] == "device-a"
    assert report["sync_version"] == 4
    assert report["report_id"] == report_id
    assert report["chunk_index"] == 0
    assert report["chunk_count"] == 1
    assert {
        (item["preset_id"], item["operation"], item["state"], item.get("error_code"))
        for item in report["results"]
    } == {
        (10, "download", "loaded", None),
        (11, "download", "pending_restart", None),
        (12, "download", "error", "host_did_not_load"),
        (13, "download", "error", "local_write_or_validation_failed"),
        (20, "delete", "removed", None),
    }

def test_filament_sync_report_chunks_more_than_one_thousand_results(
    plugin_module,
    monkeypatch,
):
    report_id = "22222222-2222-4222-8222-222222222222"
    posted = []

    def post(path, _token, payload):
        posted.append((path, payload))
        return 200, json.dumps(
            {
                "sync_version": 9,
                "report_id": report_id,
                "chunk_index": payload["chunk_index"],
                "received_chunks": payload["chunk_index"] + 1,
                "chunk_count": payload["chunk_count"],
                "complete": payload["chunk_index"] + 1 == payload["chunk_count"],
                "duplicate": False,
            }
        ).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    results = [
        {
            "preset_id": preset_id,
            "preset_type": "filament",
            "operation": "download",
            "state": "on_disk",
        }
        for preset_id in range(1, 1002)
    ]

    assert plugin_module.complete_filament_sync_report(
        "token",
        "device-a",
        9,
        report_id,
        results,
    ) is True
    assert [path for path, _payload in posted] == [
        "/orcaslicer/sync-complete/chunk",
        "/orcaslicer/sync-complete/chunk",
        "/orcaslicer/sync-complete/chunk",
    ]
    assert [len(payload["results"]) for _path, payload in posted] == [500, 500, 1]
    assert [payload["chunk_index"] for _path, payload in posted] == [0, 1, 2]
    assert {payload["report_id"] for _path, payload in posted} == {report_id}

def test_filament_sync_report_retries_the_exact_same_chunk(
    plugin_module,
    monkeypatch,
):
    report_id = "33333333-3333-4333-8333-333333333333"
    posted = []
    responses = iter((503, 200))
    monkeypatch.setattr(plugin_module.time, "sleep", lambda _seconds: None)

    def post(_path, _token, payload):
        posted.append(json.loads(json.dumps(payload)))
        status = next(responses)
        if status != 200:
            return status, b"temporary"
        return 200, json.dumps(
            {
                "sync_version": 2,
                "report_id": report_id,
                "chunk_index": 0,
                "received_chunks": 1,
                "chunk_count": 1,
                "complete": True,
                "duplicate": True,
            }
        ).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_post_json", post)

    assert plugin_module.complete_filament_sync_report(
        "token",
        "device-a",
        2,
        report_id,
        [
            {
                "preset_id": 1,
                "preset_type": "filament",
                "operation": "download",
                "state": "loaded",
            }
        ],
    ) is True
    assert posted[0] == posted[1]

def test_failed_sync_report_becomes_an_explicit_warning(plugin_module):
    contours = [
        {"kind": "filament", "status": "success", "summary": "up to date: 4"},
        {"kind": "machine", "status": "success", "summary": "nothing to sync"},
    ]

    status = plugin_module.mark_sync_report_failed(contours, "success")

    assert status == "warning"
    assert contours[0]["status"] == "warning"
    assert plugin_module.ui_text("summaryReportFailed") in contours[0]["summary"]
    assert contours[1]["status"] == "success"

def test_filament_sync_reports_on_disk_when_host_observation_is_unavailable(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "live"
    live.mkdir()
    profile = {"name": "Present", "bundle_id": "filamenthub:42"}
    (live / "Present.json").write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(live))
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(
        plugin_module,
        "load_sync_state",
        lambda: {
            "42": {
                "updated_at": "2026-08-01",
                "hash": plugin_module.preset_content_hash(profile),
                "name": "Present",
            }
        },
    )
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda _value: None)
    monkeypatch.setattr(
        plugin_module,
        "_sync_preferences",
        lambda _token: {
            "available": True,
            "auto_import_local_presets": False,
            "sync_printer_endpoints": False,
            "allow_filament_presets_import": False,
            "allow_filament_presets_export": True,
            "allow_printer_profiles_import": False,
            "allow_printer_profiles_export": False,
            "allow_print_profiles_import": False,
            "allow_print_profiles_export": False,
        },
    )
    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda *_args, **_kwargs: (
            200,
            json.dumps({
                "items": [{
                    "id": 42,
                    "name": "Present",
                    "updated_at": "2026-08-01",
                }]
            }).encode("utf-8"),
        ),
    )
    posted = []

    report_id = "44444444-4444-4444-8444-444444444444"

    def post(path, _token, payload):
        posted.append((path, payload))
        if path == "/orcaslicer/sync-plan":
            body = {"sync_version": 1, "report_id": report_id}
        else:
            body = {
                "sync_version": 1,
                "report_id": report_id,
                "chunk_index": payload["chunk_index"],
                "received_chunks": 1,
                "chunk_count": 1,
                "complete": True,
                "duplicate": False,
            }
        return 200, json.dumps(body).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_post_json", post)

    plugin_module.FilamentHubCatalog()._do_sync(
        "token",
        set(),
        announce=False,
        source_instance_id="device-b",
        loaded_preset_ids=None,
        scope="filament",
        operation_id="sync-b",
    )

    assert posted[1][1]["results"] == [{
        "preset_id": 42,
        "preset_type": "filament",
        "operation": "download",
        "state": "on_disk",
    }]

def test_managed_local_bundle_reload_is_feature_detected(plugin_module, monkeypatch):
    calls = []
    monkeypatch.setattr(
        plugin_module.orca.host,
        "reload_local_bundle",
        lambda bundle_id: calls.append(bundle_id),
        raising=False,
    )

    assert plugin_module.reload_managed_local_bundle_if_available()
    assert calls == [plugin_module.BUNDLE_ID]

    def unavailable(_bundle_id):
        raise RuntimeError("host unavailable")

    monkeypatch.setattr(
        plugin_module.orca.host, "reload_local_bundle", unavailable, raising=False
    )
    monkeypatch.setattr(plugin_module, "fh_log", lambda _message: None)

    assert not plugin_module.reload_managed_local_bundle_if_available()

def test_sync_reports_loaded_after_native_local_bundle_reload(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "live"
    live.mkdir()
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(live))
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(plugin_module, "load_sync_state", lambda: {})
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda _state: None)
    monkeypatch.setattr(
        plugin_module,
        "_sync_preferences",
        lambda _token: {
            "available": True,
            "auto_import_local_presets": False,
            "sync_printer_endpoints": False,
            "allow_filament_presets_import": False,
            "allow_filament_presets_export": True,
            "allow_printer_profiles_import": False,
            "allow_printer_profiles_export": False,
            "allow_print_profiles_import": False,
            "allow_print_profiles_export": False,
        },
    )
    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda *_args, **_kwargs: (
            200,
            json.dumps({
                "items": [{"id": 73, "name": "Live", "updated_at": "2026-08-28"}]
            }).encode("utf-8"),
        ),
    )
    posted = []

    report_id = "55555555-5555-4555-8555-555555555555"

    def post(path, _token, payload):
        posted.append((path, payload))
        if path == "/orcaslicer/sync-plan":
            body = {"sync_version": 1, "report_id": report_id}
        else:
            body = {
                "sync_version": 1,
                "report_id": report_id,
                "chunk_index": payload["chunk_index"],
                "received_chunks": 1,
                "chunk_count": 1,
                "complete": True,
                "duplicate": False,
            }
        return 200, json.dumps(body).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_post_json", post)

    def pull(preset_id, _token, _known_presets, folder, remote):
        profile = {"name": remote["name"], "bundle_id": "filamenthub:%d" % preset_id}
        path = plugin_module.preset_file_path(folder, remote["name"], preset_id)
        plugin_module.write_bytes_atomic(path, json.dumps(profile).encode("utf-8"))
        return {
            "updated_at": remote["updated_at"],
            "hash": plugin_module.preset_content_hash(profile),
            "name": remote["name"],
        }

    reloaded = []
    monkeypatch.setattr(
        plugin_module.orca.host,
        "reload_local_bundle",
        lambda bundle_id: reloaded.append(bundle_id),
        raising=False,
    )
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_pull_one", pull)

    catalog._do_sync(
        "token",
        set(),
        announce=False,
        source_instance_id="device-native",
        loaded_preset_ids=set(),
        scope="filament",
        operation_id="native-reload",
    )

    assert reloaded == [plugin_module.BUNDLE_ID]
    assert posted[1][1]["results"] == [{
        "preset_id": 73,
        "preset_type": "filament",
        "operation": "download",
        "state": "loaded",
    }]

def test_loaded_managed_preset_ids_reports_unknown_without_a_host_bundle(
    plugin_module, monkeypatch
):
    def unavailable():
        raise RuntimeError("no host")

    monkeypatch.setattr(plugin_module.orca, "host", SimpleNamespace(preset_bundle=unavailable))
    monkeypatch.setattr(plugin_module, "fh_log", lambda msg: None)

    assert plugin_module.loaded_managed_preset_ids() is None

def test_atomic_json_write_replaces_complete_file(plugin_module, tmp_path):
    target = tmp_path / "state.json"
    plugin_module.write_json_atomic(str(target), {"version": 1})
    plugin_module.write_json_atomic(str(target), {"version": 2, "name": "FilamentHub"})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "version": 2,
        "name": "FilamentHub",
    }
    assert list(tmp_path.glob("*.tmp.*")) == []

def test_recovery_scans_all_profile_kinds_and_live_copy_wins(
    plugin_module, monkeypatch, tmp_path
):
    def write_profile(root, account, kind, name, payload):
        folder = root / account / kind
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.json").write_text(
            json.dumps({"name": name, **payload}),
            encoding="utf-8",
        )

    live = tmp_path / "user"
    backup = tmp_path / "user_backup_20260813"
    write_profile(live, "account", "filament", "Workshop PLA", {"filament_type": ["PLA"]})
    write_profile(live, "account", "machine", "Workshop Voron", {"inherits": "Voron 2.4"})
    write_profile(
        live,
        "account",
        "process",
        "Workshop quality",
        {"layer_height": "0.20"},
    )
    write_profile(
        backup,
        "account",
        "process",
        "Workshop quality",
        {"layer_height": "0.28"},
    )
    write_profile(
        backup,
        "account",
        "machine",
        "Old backup machine",
        {"nozzle_diameter": ["0.6"]},
    )
    write_profile(
        backup,
        "second-account",
        "process",
        "Workshop quality",
        {"layer_height": "0.12"},
    )
    monkeypatch.setattr(plugin_module, "DATA_DIR", str(tmp_path))

    recovered = plugin_module.scan_recovery_presets()

    assert {(item["kind"], item["name"]) for item in recovered} == {
        ("filament", "Workshop PLA"),
        ("machine", "Workshop Voron"),
        ("machine", "Old backup machine"),
        ("process", "Workshop quality"),
    }
    qualities = [item for item in recovered if item["kind"] == "process"]
    assert len(qualities) == 2
    quality = next(item for item in qualities if item["account"] == "account")
    assert quality["source"] == "live"
    assert quality["profile"]["layer_height"] == "0.20"
    second = next(item for item in qualities if item["account"] == "second-account")
    assert second["source"] == "backup"
    assert second["profile"]["layer_height"] == "0.12"

    disambiguated = plugin_module.disambiguate_recovery_candidates(qualities)
    assert {item["name"] for item in disambiguated} == {
        "Workshop quality [account]",
        "Workshop quality [second-account]",
    }
    assert {item["profile"]["name"] for item in disambiguated} == {
        "Workshop quality [account]",
        "Workshop quality [second-account]",
    }

def test_printer_profiles_never_leave_with_host_credentials(
    plugin_module, monkeypatch, tmp_path
):
    # A printer preset holds the credentials of its network host; they must stay
    # on the user's machine even though the rest of the preset is reported.
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(
        plugin_module, "http_post_json",
        lambda path, token, payload: (sent.append((path, payload)), (200, b"{}"))[1],
    )
    items = [{"name": "Voron 350", "settings": {
        "printer_settings_id": "voron-350",
        "print_host": "192.168.1.50",
        "printhost_apikey": "secret-key",
        "printhost_password": "hunter2",
        "printhost_user": "admin",
        "nozzle_diameter": ["0.4"],
    }}]
    state = {}
    assert plugin_module.push_user_profiles(
        "machine", "tok", items, state, authoritative=False
    ) == (1, 0)
    path, payload = sent[0]
    assert path == "/orcaslicer/printer-profiles/import"
    settings = payload["profiles"][0]["orcaslicer_settings"]
    assert "printhost_apikey" not in settings
    assert "printhost_password" not in settings
    assert "printhost_user" not in settings
    assert "print_host" not in settings
    assert "host_type" not in settings
    assert settings["nozzle_diameter"] == ["0.4"]
    assert payload["profiles"][0]["setting_id"] == "voron-350"
    assert payload["profiles"][0]["external_id"].startswith("orca-local-v1:")

def test_process_compatibility_values_are_normalized_for_backend_contract(
    plugin_module, monkeypatch, tmp_path
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda _path, _token, payload: (sent.append(payload), (200, b"{}"))[1],
    )
    items = [{
        "name": "0.20mm Standard",
        "settings": {"layer_height": "0.2"},
        "compatible_printers": [" Voron 2.4 ", "Voron 2.4", None, 42],
        "compatible_filaments": " PETG ",
        "compatible_printers_condition": ["", 'printer_model=="Voron 2.4"'],
    }]

    assert plugin_module.push_user_profiles(
        "process", "tok", items, {}, authoritative=False
    ) == (1, 0)

    profile = sent[0]["profiles"][0]
    assert profile["compatible_printers"] == ["Voron 2.4"]
    assert profile["compatible_filaments"] == ["PETG"]
    assert profile["compatible_printers_condition"] == 'printer_model=="Voron 2.4"'

def test_validation_error_log_shape_never_contains_rejected_input(plugin_module):
    body = json.dumps({
        "detail": [{
            "loc": ["body", "profiles", 0, "compatible_printers_condition"],
            "type": "string_type",
            "input": "private-profile-value",
        }]
    }).encode("utf-8")

    summary = plugin_module._http_error_shape(body)

    assert summary == (
        "body.profiles.0.compatible_printers_condition:string_type"
    )
    assert "private-profile-value" not in summary

def test_sibling_printer_profiles_with_shared_orca_id_keep_distinct_sync_ids(
    plugin_module,
    monkeypatch,
    tmp_path,
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda path, token, payload: (sent.append(payload), (200, b"{}"))[1],
    )
    items = [
        {
            "name": "Workshop A1 mini",
            "settings": {"printer_settings_id": "Bambu Lab A1 mini 0.4 nozzle"},
        },
        {
            "name": "Office A1 mini",
            "settings": {"printer_settings_id": "Bambu Lab A1 mini 0.4 nozzle"},
        },
    ]

    assert plugin_module.push_user_profiles(
        "machine", "tok", items, {}, authoritative=False
    ) == (2, 0)
    profiles = sent[0]["profiles"]
    assert profiles[0]["setting_id"] == profiles[1]["setting_id"]
    assert profiles[0]["external_id"] != profiles[1]["external_id"]

def test_profile_registry_distinguishes_rename_from_save_as(
    plugin_module, monkeypatch, tmp_path
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    original = [{
        "name": "Voron workshop",
        "locator": "file:machine/voron-workshop.json",
        "settings": {"nozzle_diameter": ["0.4"]},
    }]
    account_id, original, saved = plugin_module.reconcile_local_profile_identities(
        "machine", original
    )
    assert saved
    original_id = original[0]["local_profile_id"]

    renamed = [{
        "name": "Voron main",
        "locator": "file:machine/voron-main.json",
        "settings": {"nozzle_diameter": ["0.4"]},
    }]
    same_account_id, renamed, saved = plugin_module.reconcile_local_profile_identities(
        "machine", renamed
    )
    assert saved
    assert same_account_id == account_id
    assert renamed[0]["local_profile_id"] == original_id

    copied = [
        renamed[0],
        {
            "name": "Voron spare",
            "locator": "file:machine/voron-spare.json",
            "settings": {"nozzle_diameter": ["0.4"]},
        },
    ]
    _account_id, copied, saved = plugin_module.reconcile_local_profile_identities(
        "machine", copied
    )
    assert saved
    assert copied[0]["local_profile_id"] == original_id
    assert copied[1]["local_profile_id"] != original_id

    monkeypatch.setattr(
        plugin_module,
        "profile_identity_registry_path",
        lambda: str(tmp_path / "other-account" / "profile_identity.json"),
    )
    other_account_id, other_account_items, saved = (
        plugin_module.reconcile_local_profile_identities(
            "machine",
            [{
                "name": "Voron main",
                "locator": "file:machine/voron-main.json",
                "settings": {"nozzle_diameter": ["0.4"]},
            }],
        )
    )
    assert saved
    assert other_account_id != account_id
    assert other_account_items[0]["local_profile_id"] != original_id

def test_filament_draft_rename_keeps_identity_and_is_not_reimported(
    plugin_module, monkeypatch, tmp_path
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    monkeypatch.setattr(
        plugin_module,
        "IMPORTED_DRAFTS_FILE",
        str(tmp_path / "imported_drafts.json"),
    )
    requests = []

    def post(_path, _token, payload):
        requests.append(payload)
        return 200, json.dumps({
            "results": [
                {
                    "status": "created",
                    "external_id": item["external_id"],
                    "review_state": "almost_ready",
                    "important_decisions": 1,
                }
                for item in payload["profiles"]
            ]
        }).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    original = [{
        "name": "Workshop PETG",
        "locator": "file:filament/workshop-petg.json",
        "profile": {"filament_type": ["PETG"], "name": "Workshop PETG"},
    }]
    sent = plugin_module.push_filament_drafts("tok", original)
    assert len(sent) == 1
    assert requests[0]["profiles"][0]["source_version"] == plugin_module.PLUGIN_VERSION
    assert requests[0]["profiles"][0]["capture_mode"] == "resolved_runtime"
    assert original[0]["_draft_review_state"] == "almost_ready"
    assert original[0]["_draft_decisions"] == 1
    plugin_module.save_imported_draft_ids({sent[0]: 1})

    renamed = [{
        "name": "Workshop PETG tuned",
        "locator": "file:filament/workshop-petg-tuned.json",
        "profile": {"filament_type": ["PETG"], "name": "Workshop PETG tuned"},
    }]
    assert plugin_module.push_filament_drafts("tok", renamed) == []
    assert renamed[0]["_draft_sync_id"] == sent[0]
    assert len(requests) == 1

def test_filament_draft_batch_retries_only_item_level_errors(
    plugin_module, monkeypatch, tmp_path
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    monkeypatch.setattr(
        plugin_module,
        "IMPORTED_DRAFTS_FILE",
        str(tmp_path / "imported_drafts.json"),
    )
    requests = []

    def post(_path, _token, payload):
        requests.append(payload)
        statuses = ["created", "error"] if len(requests) == 1 else ["created"]
        return 200, json.dumps({
            "results": [{"status": status} for status in statuses]
        }).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    candidates = [
        {
            "name": "PLA accepted",
            "locator": "file:filament/pla-accepted.json",
            "profile": {"filament_type": ["PLA"]},
        },
        {
            "name": "PETG retry",
            "locator": "file:filament/petg-retry.json",
            "profile": {"filament_type": ["PETG"]},
        },
    ]
    accepted = plugin_module.push_filament_drafts("tok", candidates)
    assert accepted == [candidates[0]["_draft_sync_id"]]
    plugin_module.save_imported_draft_ids({accepted[0]: 1})

    retried = plugin_module.push_filament_drafts("tok", candidates)
    assert retried == [candidates[1]["_draft_sync_id"]]
    assert [item["name"] for item in requests[1]["profiles"]] == ["PETG retry"]

def test_recovered_filament_records_raw_backup_provenance(
    plugin_module, monkeypatch, tmp_path
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    monkeypatch.setattr(
        plugin_module,
        "IMPORTED_DRAFTS_FILE",
        str(tmp_path / "imported_drafts.json"),
    )
    sent_payloads = []

    def post(_path, _token, payload):
        sent_payloads.extend(payload["profiles"])
        return 200, json.dumps({"results": [{"status": "created"}]}).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    recovered = [{
        "name": "Recovered PLA",
        "key": "filament:backup:Recovered PLA",
        "source": "backup",
        "profile": {"filament_type": ["PLA"]},
    }]

    accepted = plugin_module.push_filament_drafts(
        "tok", recovered, authoritative=False
    )

    assert len(accepted) == 1
    assert sent_payloads[0]["capture_mode"] == "recovered_backup_json"
    assert sent_payloads[0]["source_version"] == plugin_module.PLUGIN_VERSION

def test_authoritative_profile_sync_uses_start_batch_finalize(
    plugin_module, monkeypatch, tmp_path
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    snapshot_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    calls = []
    server_bound_ids = set()

    def post(path, _token, payload):
        calls.append((path, payload))
        if path.endswith("/start"):
            return 200, json.dumps({
                "snapshot_id": snapshot_id,
                "bound_local_profile_ids": sorted(server_bound_ids),
            }).encode()
        if path.endswith("/finalize"):
            return 200, json.dumps({"status": "finalized"}).encode()
        server_bound_ids.update(
            item["local_profile_id"] for item in payload["profiles"]
        )
        return 200, json.dumps({"results": [{"status": "created"}]}).encode()

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    items = [{
        "name": "Voron 350",
        "locator": "file:machine/voron-350.json",
        "settings": {"nozzle_diameter": ["0.4"]},
    }]
    state = {}

    assert plugin_module.push_user_profiles("machine", "tok", items, state) == (1, 0)
    assert [path for path, _payload in calls] == [
        "/orcaslicer/profile-snapshots/start",
        "/orcaslicer/printer-profiles/import",
        "/orcaslicer/profile-snapshots/finalize",
    ]
    import_payload = calls[1][1]
    finalize_payload = calls[2][1]
    assert import_payload["snapshot_id"] == snapshot_id
    assert finalize_payload["present_local_profile_ids"] == [
        import_payload["profiles"][0]["local_profile_id"]
    ]

    calls.clear()
    assert plugin_module.push_user_profiles("machine", "tok", items, state) == (0, 0)
    assert [path for path, _payload in calls] == [
        "/orcaslicer/profile-snapshots/start",
        "/orcaslicer/profile-snapshots/finalize",
    ]

    # A local digest is only an optimization. If the server lost the durable
    # binding (for example after a dev DB reset), the unchanged source profile
    # is authoritative and must be sent again.
    server_bound_ids.clear()
    calls.clear()
    assert plugin_module.push_user_profiles("machine", "tok", items, state) == (1, 0)
    assert [path for path, _payload in calls] == [
        "/orcaslicer/profile-snapshots/start",
        "/orcaslicer/printer-profiles/import",
        "/orcaslicer/profile-snapshots/finalize",
    ]

def test_unchanged_profiles_are_not_reported_again(
    plugin_module, monkeypatch, tmp_path
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        plugin_module, "http_post_json",
        lambda path, token, payload: (calls.append(payload), (200, b"{}"))[1],
    )
    items = [{"name": "0.2mm Standard", "settings": {"layer_height": "0.2"}}]
    state = {}
    assert plugin_module.push_user_profiles(
        "process", "tok", items, state, authoritative=False
    ) == (1, 0)
    assert plugin_module.push_user_profiles(
        "process", "tok", items, state, authoritative=False
    ) == (0, 0)
    assert len(calls) == 1

    items[0]["settings"]["layer_height"] = "0.3"
    assert plugin_module.push_user_profiles(
        "process", "tok", items, state, authoritative=False
    ) == (1, 0)
    assert len(calls) == 2

def test_preset_folder_fallback_does_not_reuse_a_stale_account_directory(
    plugin_module, monkeypatch, tmp_path
):
    (tmp_path / "user" / "stale-account").mkdir(parents=True)
    monkeypatch.setattr(plugin_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(plugin_module, "_user_preset_folder", None)

    assert plugin_module.resolve_user_preset_folder() == "default"
    assert plugin_module.user_filament_dir() == str(
        tmp_path / "user" / "default" / "_local" / "filamenthub" / "filament"
    )

def test_failed_upload_is_retried_on_the_next_sync(
    plugin_module, monkeypatch, tmp_path
):
    # A rejected batch must not be recorded as reported, or the profile would be
    # silently dropped until the user happens to edit it again.
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    monkeypatch.setattr(plugin_module, "http_post_json",
                        lambda path, token, payload: (503, b""))
    items = [{"name": "Voron 350", "settings": {"nozzle_diameter": ["0.4"]}}]
    state = {}
    assert plugin_module.push_user_profiles(
        "machine", "tok", items, state, authoritative=False
    ) == (0, 1)
    assert state == {}

    monkeypatch.setattr(plugin_module, "http_post_json",
                        lambda path, token, payload: (200, b"{}"))
    assert plugin_module.push_user_profiles(
        "machine", "tok", items, state, authoritative=False
    ) == (1, 0)

def test_item_level_import_error_is_not_recorded_as_synced(
    plugin_module, monkeypatch, tmp_path
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    responses = [
        (
            200,
            json.dumps({
                "results": [
                    {"external_id": "first", "status": "created"},
                    {"external_id": "second", "status": "error"},
                ]
            }).encode("utf-8"),
        ),
        (
            200,
            json.dumps({
                "results": [{"external_id": "second", "status": "updated"}]
            }).encode("utf-8"),
        ),
    ]
    sent_batches = []

    def post(_path, _token, payload):
        sent_batches.append(payload["profiles"])
        return responses.pop(0)

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    items = [
        {"name": "First", "settings": {"nozzle_diameter": ["0.4"]}},
        {"name": "Second", "settings": {"nozzle_diameter": ["0.6"]}},
    ]
    state = {}

    assert plugin_module.push_user_profiles(
        "machine", "tok", items, state, authoritative=False
    ) == (1, 1)
    assert plugin_module.push_user_profiles(
        "machine", "tok", items, state, authoritative=False
    ) == (1, 0)
    assert [[profile["name"] for profile in batch] for batch in sent_batches] == [
        ["First", "Second"],
        ["Second"],
    ]

def test_validation_failure_isolated_without_finalizing_partial_snapshot(
    plugin_module, monkeypatch, tmp_path
):
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    snapshot_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    import_batches = []
    finalized = []

    def post(path, _token, payload):
        if path.endswith("/start"):
            return 200, json.dumps({
                "snapshot_id": snapshot_id,
                "bound_local_profile_ids": [],
            }).encode("utf-8")
        if path.endswith("/finalize"):
            finalized.append(payload)
            return 200, json.dumps({"status": "finalized"}).encode("utf-8")
        names = [profile["name"] for profile in payload["profiles"]]
        import_batches.append(names)
        if len(names) > 1 or names == ["Broken"]:
            return 422, json.dumps({"detail": [{"type": "value_error"}]}).encode(
                "utf-8"
            )
        return 200, json.dumps({"results": [{"status": "created"}]}).encode(
            "utf-8"
        )

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    items = [
        {"name": "Valid A", "settings": {"nozzle_diameter": ["0.4"]}},
        {"name": "Broken", "settings": {"nozzle_diameter": ["invalid"]}},
        {"name": "Valid B", "settings": {"nozzle_diameter": ["0.6"]}},
    ]
    state = {}

    assert plugin_module.push_user_profiles("machine", "tok", items, state) == (2, 1)
    assert import_batches == [
        ["Valid A", "Broken", "Valid B"],
        ["Valid A"],
        ["Broken", "Valid B"],
        ["Broken"],
        ["Valid B"],
    ]
    assert finalized == []
    assert len([key for key in state if key.startswith("machine:")]) == 2

def test_automatic_machine_and_process_sync_remains_outbound_only(plugin_module):
    # The normal sync registry contains only outbound import endpoints. Restoring
    # a managed machine/process set is a separate explicit message and is never
    # entered into the automatic reconciliation loop.
    for spec in plugin_module.PROFILE_KINDS.values():
        assert "folder" not in spec
        assert "export_path" not in spec
        assert "pull_path" not in spec
