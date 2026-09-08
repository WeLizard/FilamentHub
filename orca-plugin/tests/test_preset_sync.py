"""Managed preset synchronization and recovery contracts."""

from .filamenthub_plugin_test_support import (
    _isolate_profile_identity,
    json,
    pytest,
    SimpleNamespace,
)


def test_info_marker_keeps_managed_identity_after_orca_save(plugin_module, tmp_path):
    path = tmp_path / "Managed PLA.json"
    path.write_text(json.dumps({"name": "Managed PLA"}), encoding="utf-8")
    (tmp_path / "Managed PLA.info").write_text(
        "sync_info = filamenthub:preset:42\n", encoding="utf-8"
    )

    assert plugin_module.managed_preset_id(str(path), {"name": "Managed PLA"}) == 42
    assert plugin_module.preset_file_path(str(tmp_path), "Managed PLA", 42) == str(path)
    assert plugin_module.scan_local_fh_presets(str(tmp_path))[42]["path"] == str(path)

def test_saved_managed_filament_edit_roundtrips_by_info_identity(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "user" / "default" / "_local" / "filamenthub" / "filament"
    live.mkdir(parents=True)
    local_path = live / "PETG • Lumilayer • High clarity.json"
    local_profile = {
        "name": "PETG • Lumilayer • High clarity",
        "filament_settings_id": ["PETG • Lumilayer • High clarity"],
        "filament_type": ["PETG"],
        "filament_vendor": ["Lumilayer"],
        "nozzle_temperature": ["255"],
        "future_orca_setting": ["a", "b"],
    }
    baseline_profile = {
        **local_profile,
        "nozzle_temperature": ["245"],
    }
    local_path.write_text(json.dumps(local_profile), encoding="utf-8")
    local_path.with_suffix(".info").write_text(
        "sync_info = filamenthub:preset:42\nfhub_version_id = 100\n", encoding="utf-8"
    )
    state = {
        "42": {
            "updated_at": "2026-08-20T00:00:00Z",
            "hash": plugin_module.preset_content_hash(baseline_profile),
            "name": baseline_profile["name"],
            "version_id": 100,
        }
    }
    server = {
        "updated_at": "2026-08-20T00:00:00Z",
        "profile": {
            **baseline_profile,
            "name": "High clarity",
            "filament_settings_id": ["High clarity"],
        },
        "selected_version_id": 100,
        "latest_version_id": 100,
    }
    posted = []

    monkeypatch.setattr(plugin_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(plugin_module, "_user_preset_folder", "default")
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(
        plugin_module,
        "managed_preset_quarantine_dir",
        lambda: str(tmp_path / "quarantine"),
    )
    monkeypatch.setattr(plugin_module, "load_sync_state", lambda: state)
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda _state: None)
    monkeypatch.setattr(
        plugin_module,
        "_sync_preferences",
        lambda _token: {
            "available": True,
            "auto_import_local_presets": False,
            "sync_printer_endpoints": False,
            "allow_filament_presets_import": True,
            "allow_filament_presets_export": True,
            "allow_printer_profiles_import": False,
            "allow_printer_profiles_export": False,
            "allow_print_profiles_import": False,
            "allow_print_profiles_export": False,
        },
    )

    def get(path, token=None, **_kwargs):
        if path == "/auth/my-presets":
            return 200, json.dumps({"items": [{
                "id": 42,
                "name": "High clarity",
                "updated_at": server["updated_at"],
                "selected_version_id": server["selected_version_id"],
                "latest_version_id": server["latest_version_id"],
            }]}).encode("utf-8")
        if path == (
            "/presets/42/export/orcaslicer.json?version_id=%d"
            % server["selected_version_id"]
        ):
            return 200, json.dumps(server["profile"]).encode("utf-8")
        if path == "/presets/42/export/orcaslicer.info":
            return 503, b""
        raise AssertionError(path)

    def post(path, _token, payload):
        assert path == "/orcaslicer/filaments/import"
        posted.append(payload["profiles"][0])
        assert posted[-1]["base_version_id"] == 100
        server["profile"] = dict(payload["profiles"][0]["orcaslicer_settings"])
        server["updated_at"] = "2026-08-21T00:00:00Z"
        server["selected_version_id"] = 101
        server["latest_version_id"] = 101
        return 200, json.dumps({"results": [{
            "status": "updated",
            "fhub_id": 42,
            "version_id": 101,
        }]}).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_get", get)
    monkeypatch.setattr(plugin_module, "http_post_json", post)
    monkeypatch.setattr(
        plugin_module,
        "restore_remote_parent_for_upload",
        lambda profile, *_args: dict(profile),
    )
    catalog = plugin_module.FilamentHubCatalog()

    catalog._do_sync("token", set(), announce=False, scope="filament")

    assert posted[0]["fhub_id"] == 42
    assert posted[0]["info_content"] == (
        "sync_info = filamenthub:preset:42\nfhub_version_id = 100\n"
    )
    assert posted[0]["orcaslicer_settings"]["nozzle_temperature"] == ["255"]
    assert posted[0]["orcaslicer_settings"]["future_orca_setting"] == ["a", "b"]

    catalog._do_sync("token", set(), announce=False, scope="filament")

    saved = json.loads(local_path.read_text(encoding="utf-8"))
    assert saved["nozzle_temperature"] == ["255"]
    assert saved["future_orca_setting"] == ["a", "b"]
    assert local_path.with_suffix(".info").read_text(encoding="utf-8") == (
        "sync_info = filamenthub:preset:42\nfhub_version_id = 101\n"
    )
    assert plugin_module.scan_local_fh_presets(str(live))[42]["version_id"] == 101
    assert plugin_module.scan_local_fh_presets(str(live))[42]["hash"] == (
        plugin_module.preset_content_hash(saved)
    )

def test_sync_keeps_both_versions_when_local_and_remote_changed(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "user" / "default" / "_local" / "filamenthub" / "filament"
    live.mkdir(parents=True)
    local_path = live / "PETG • Lumilayer • High clarity.json"
    local_profile = {
        "name": "PETG • Lumilayer • High clarity",
        "filament_settings_id": ["PETG • Lumilayer • High clarity"],
        "filament_type": ["PETG"],
        "filament_vendor": ["Lumilayer"],
        "nozzle_temperature": ["255"],
    }
    local_path.write_text(json.dumps(local_profile), encoding="utf-8")
    local_path.with_suffix(".info").write_text(
        "sync_info = filamenthub:preset:42\nfhub_version_id = 100\n", encoding="utf-8"
    )
    before = local_path.read_bytes()
    state = {
        "42": {
            "updated_at": "2026-08-20T00:00:00Z",
            "hash": plugin_module.preset_content_hash({
                **local_profile,
                "nozzle_temperature": ["245"],
            }),
            "name": local_profile["name"],
            "version_id": 100,
        }
    }
    delivered = []

    monkeypatch.setattr(plugin_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(plugin_module, "_user_preset_folder", "default")
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(
        plugin_module,
        "managed_preset_quarantine_dir",
        lambda: str(tmp_path / "quarantine"),
    )
    monkeypatch.setattr(plugin_module, "load_sync_state", lambda: state)
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda _state: None)
    monkeypatch.setattr(
        plugin_module,
        "_sync_preferences",
        lambda _token: {
            "available": True,
            "auto_import_local_presets": False,
            "sync_printer_endpoints": False,
            "allow_filament_presets_import": True,
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
        lambda path, token=None, **_kwargs: (
            200,
            json.dumps({"items": [{
                "id": 42,
                "name": "High clarity",
                "updated_at": "2026-08-21T00:00:00Z",
                "selected_version_id": 101,
                "latest_version_id": 101,
            }]}).encode("utf-8"),
        ) if path == "/auth/my-presets" else pytest.fail(path),
    )
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_push_one",
        lambda *_args: pytest.fail("a conflicted local version must not upload"),
    )
    monkeypatch.setattr(
        catalog,
        "_pull_one",
        lambda *_args: pytest.fail("a conflicted server version must not overwrite"),
    )
    monkeypatch.setattr(
        catalog,
        "_deliver_sync_result",
        lambda *_args, **kwargs: delivered.append(kwargs),
    )

    catalog._do_sync("token", set(), announce=True, scope="filament")

    assert local_path.read_bytes() == before
    assert delivered[0]["status"] == "warning"
    assert plugin_module.ui_text("summaryConflict", count=1) in delivered[0]["contours"][0]["summary"]

def test_push_of_foreign_managed_preset_reidentifies_saved_edit_as_personal_fork(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "user" / "default" / "_local" / "filamenthub" / "filament"
    live.mkdir(parents=True)
    source_path = live / "High clarity.json"
    profile = {
        "name": "High clarity",
        "filament_settings_id": ["High clarity"],
        "filament_type": ["PETG"],
        "filament_vendor": ["Lumilayer"],
        "nozzle_temperature": ["255"],
        "bundle_id": "filamenthub:42",
    }
    source_path.write_text(json.dumps(profile), encoding="utf-8")
    source_path.with_suffix(".info").write_text(
        "sync_info = filamenthub:preset:42\nfhub_version_id = 100\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        plugin_module,
        "managed_preset_quarantine_dir",
        lambda: str(tmp_path / "quarantine"),
    )
    monkeypatch.setattr(
        plugin_module,
        "restore_remote_parent_for_upload",
        lambda value, *_args: dict(value),
    )
    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda *_args, **_kwargs: (503, b""),
    )

    def post(path, _token, payload):
        assert path == "/orcaslicer/filaments/import"
        assert payload["profiles"][0]["fhub_id"] == 42
        assert payload["profiles"][0]["base_version_id"] == 100
        return 200, json.dumps({"results": [{
            "status": "created",
            "fhub_id": 84,
            "version_id": 201,
        }]}).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_post_json", post)
    result = plugin_module.FilamentHubCatalog()._push_one(
        42,
        "token",
        {
            "profile": profile,
            "path": str(source_path),
            "hash": plugin_module.preset_content_hash(profile),
            "version_id": 100,
        },
        {"name": "High clarity", "selected_version_id": 100},
    )

    assert result is not None
    assert result["preset_id"] == 84
    assert result["version_id"] == 201
    assert not source_path.exists()
    managed = plugin_module.scan_local_fh_presets(str(live))
    assert set(managed) == {84}
    assert managed[84]["version_id"] == 201
    assert managed[84]["profile"]["nozzle_temperature"] == ["255"]
    quarantined = sorted(path.name for path in (tmp_path / "quarantine").rglob("*.*"))
    assert quarantined == ["High clarity.info", "High clarity.json"]

def test_pull_keeps_managed_identity_when_server_info_is_unavailable(
    plugin_module, monkeypatch, tmp_path
):
    profile = {
        "name": "Managed PLA",
        "inherits": "fdm_filament_common",
        "filament_type": ["PLA"],
        "filament_vendor": ["OlgaCraft"],
    }

    def fake_http_get(path, token=None, **kwargs):
        if path.endswith(".json"):
            return 200, json.dumps(profile).encode("utf-8")
        return 503, b""

    monkeypatch.setattr(plugin_module, "http_get", fake_http_get)
    result = plugin_module.FilamentHubCatalog()._pull_one(
        42,
        "token",
        {"fdm_filament_common"},
        str(tmp_path),
        {"updated_at": "2026-08-01"},
    )

    assert result is not None
    path = tmp_path / "PLA • OlgaCraft • Managed PLA.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["name"] == "PLA • OlgaCraft • Managed PLA"
    assert saved["filament_settings_id"] == ["PLA • OlgaCraft • Managed PLA"]
    assert "inherits" not in saved
    saved.pop("bundle_id")
    path.write_text(json.dumps(saved), encoding="utf-8")
    assert plugin_module.managed_preset_id(str(path), saved) == 42
    assert plugin_module.scan_local_fh_presets(str(tmp_path))[42]["path"] == str(path)

def test_legacy_managed_name_migrates_to_material_first_display(
    plugin_module, monkeypatch, tmp_path
):
    private = tmp_path / "private"
    monkeypatch.setattr(
        plugin_module,
        "profile_identity_registry_path",
        lambda: str(private / "profile_identity.json"),
    )
    path = tmp_path / "Smooth satin.json"
    profile = {
        "name": "Smooth satin",
        "filament_settings_id": ["Smooth satin"],
        "filament_type": ["PLA"],
        "filament_vendor": ["OlgaCraft"],
        "bundle_id": "filamenthub:42",
    }
    path.write_text(json.dumps(profile), encoding="utf-8")
    (tmp_path / "Smooth satin.info").write_text(
        "sync_info = filamenthub:preset:42\n", encoding="utf-8"
    )
    entry = {
        "path": str(path),
        "profile": profile,
        "hash": plugin_module.preset_content_hash(profile),
        "version_id": 7,
    }

    name = plugin_module.migrate_managed_filament_display_name(
        str(tmp_path), 42, entry, {"name": "Smooth satin"}
    )

    assert name == "PLA • OlgaCraft • Smooth satin"
    migrated = tmp_path / "PLA • OlgaCraft • Smooth satin.json"
    saved = json.loads(migrated.read_text(encoding="utf-8"))
    assert saved["name"] == "PLA • OlgaCraft • Smooth satin"
    assert saved["filament_settings_id"] == ["PLA • OlgaCraft • Smooth satin"]
    assert entry["path"] == str(migrated)
    assert not path.exists()
    assert migrated.with_suffix(".info").read_text(encoding="utf-8") == (
        "sync_info = filamenthub:preset:42\nfhub_version_id = 7\n"
    )

def test_sync_migrates_legacy_display_without_pushing_it_to_filamenthub(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "live"
    live.mkdir()
    profile = {
        "name": "PLA • Smooth satin",
        "filament_settings_id": ["PLA • Smooth satin"],
        "filament_type": ["PLA"],
        "filament_vendor": ["OlgaCraft"],
        "bundle_id": "filamenthub:42",
    }
    path = live / "PLA • Smooth satin.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    (live / "PLA • Smooth satin.info").write_text(
        "sync_info = filamenthub:preset:42\n", encoding="utf-8"
    )
    state = {
        "42": {
            "updated_at": "2026-08-01",
            "hash": plugin_module.preset_content_hash(profile),
            "name": "PLA • Smooth satin",
        }
    }
    saved = {}
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(live))
    monkeypatch.setattr(
        plugin_module,
        "managed_preset_quarantine_dir",
        lambda: str(tmp_path / "quarantine"),
    )
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(plugin_module, "load_sync_state", lambda: state)
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda value: saved.update(value))
    monkeypatch.setattr(
        plugin_module,
        "_sync_preferences",
        lambda _token: {
            "available": True,
            "auto_import_local_presets": False,
            "sync_printer_endpoints": False,
            "allow_filament_presets_import": True,
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
        lambda path, token=None: (
            200,
            json.dumps({
                "items": [{
                    "id": 42,
                    "name": "Smooth satin",
                    "updated_at": "2026-08-01",
                }]
            }).encode("utf-8"),
        ),
    )
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_push_one",
        lambda *args, **kwargs: pytest.fail("automatic display name was pushed"),
    )

    catalog._do_sync("token", set(), announce=False, scope="filament")

    migrated = live / "PLA • OlgaCraft • Smooth satin.json"
    assert migrated.is_file()
    assert not path.exists()
    assert saved["42"]["name"] == "PLA • OlgaCraft • Smooth satin"
    assert saved["42"]["hash"] == plugin_module.preset_content_hash(
        json.loads(migrated.read_text(encoding="utf-8"))
    )

def test_recover_sync_record_never_treats_lost_state_as_remote_newer(plugin_module, monkeypatch):
    # The state file dies with plugin updates; a local file without a record
    # must be adopted when identical and pushed when edited — never re-pulled.
    remote = {"name": "PLA", "inherits": "fdm_filament_common", "nozzle_temperature": ["210"]}

    def fake_http_get(path, token=None, **kw):
        return 200, json.dumps(remote).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_get", fake_http_get)
    normalized = dict(remote)
    plugin_module.ensure_parent_exists(normalized, {"fdm_filament_common"})
    plugin_module.ensure_filament_colour(normalized)
    normalized["bundle_id"] = "filamenthub:5"
    local_same = {"hash": plugin_module.preset_content_hash(normalized),
                  "profile": {"name": "PLA"}}
    rec = plugin_module.recover_sync_record(5, "tok", {"fdm_filament_common"}, local_same, "2026-07-16")
    assert rec == {"updated_at": "2026-07-16", "hash": local_same["hash"], "name": "PLA"}

    local_edited = {"hash": "deadbeef", "profile": {"name": "PLA"}}
    assert plugin_module.recover_sync_record(5, "tok", {"fdm_filament_common"}, local_edited, "2026-07-16") is False

    monkeypatch.setattr(plugin_module, "http_get", lambda path, token=None, **kw: (503, b""))
    assert plugin_module.recover_sync_record(5, "tok", set(), local_same, "2026-07-16") is None

def test_push_preserves_legacy_remote_name_and_canonical_parent(
    plugin_module, monkeypatch, tmp_path
):
    local_path = tmp_path / "PLA_0.4.json"
    local_profile = {
        "name": "PLA_0.4",
        "filament_settings_id": ["PLA_0.4"],
        "nozzle_temperature": ["220"],
    }
    local_path.write_text(json.dumps(local_profile), encoding="utf-8")
    captured = {}

    def fake_get(path, token=None, **kwargs):
        assert path == "/presets/42/export/orcaslicer.json"
        return 200, json.dumps({"inherits": "Original Vendor PLA"}).encode("utf-8")

    def fake_post(path, token, payload):
        captured.update(payload["profiles"][0])
        return 200, b"{}"

    monkeypatch.setattr(plugin_module, "http_get", fake_get)
    monkeypatch.setattr(plugin_module, "http_post_json", fake_post)
    entry = {
        "path": str(local_path),
        "profile": local_profile,
        "hash": plugin_module.preset_content_hash(local_profile),
    }

    result = plugin_module.FilamentHubCatalog()._push_one(
        42,
        "token",
        entry,
        {"name": "PLA/0.4", "updated_at": "2026-08-01"},
    )

    assert captured["name"] == "PLA/0.4"
    assert captured["orcaslicer_settings"]["name"] == "PLA/0.4"
    assert captured["orcaslicer_settings"]["inherits"] == "Original Vendor PLA"
    assert result["updated_at"] == "2026-08-01"

def test_push_keeps_automatic_display_prefix_out_of_filamenthub_name(
    plugin_module, monkeypatch, tmp_path
):
    local_path = tmp_path / "PLA • OlgaCraft • Smooth satin.json"
    local_profile = {
        "name": "PLA • OlgaCraft • Smooth satin",
        "filament_settings_id": ["PLA • OlgaCraft • Smooth satin"],
        "filament_type": ["PLA"],
        "filament_vendor": ["OlgaCraft"],
        "nozzle_temperature": ["215"],
    }
    local_path.write_text(json.dumps(local_profile), encoding="utf-8")
    captured = {}
    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda path, token=None, **kwargs: (200, json.dumps({}).encode("utf-8")),
    )

    def fake_post(path, token, payload):
        captured.update(payload["profiles"][0])
        return 200, b"{}"

    monkeypatch.setattr(plugin_module, "http_post_json", fake_post)
    entry = {
        "path": str(local_path),
        "profile": local_profile,
        "hash": plugin_module.preset_content_hash(local_profile),
    }

    plugin_module.FilamentHubCatalog()._push_one(
        42,
        "token",
        entry,
        {"name": "Smooth satin", "updated_at": "2026-08-01"},
    )

    assert captured["name"] == "Smooth satin"
    assert captured["orcaslicer_settings"]["name"] == "Smooth satin"

def test_stale_preset_files_are_removed_after_rename(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "live"
    live.mkdir()
    private = tmp_path / "private"
    monkeypatch.setattr(
        plugin_module,
        "profile_identity_registry_path",
        lambda: str(private / "profile_identity.json"),
    )
    (live / "Old Name__fh_10.json").write_text(
        json.dumps({"bundle_id": "filamenthub:10"}), encoding="utf-8"
    )
    (live / "Old Name__fh_10.info").write_text(
        "sync_info = filamenthub:preset:10\n", encoding="utf-8"
    )
    keep = plugin_module.preset_file_path(str(live), "New Name", 10)
    plugin_module.write_json_atomic(keep, {"bundle_id": "filamenthub:10", "name": "New Name"})
    plugin_module.remove_stale_preset_files(str(live), 10, keep)
    remaining = sorted(p.name for p in live.iterdir())
    assert remaining == ["New Name.json"]
    quarantined = sorted(p.name for p in private.rglob("*.*"))
    assert quarantined == ["Old Name__fh_10.info", "Old Name__fh_10.json"]

def test_desired_state_cleanup_quarantines_stale_orphan_and_invalid_managed_files(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "live"
    live.mkdir()
    private = tmp_path / "private"
    monkeypatch.setattr(
        plugin_module,
        "profile_identity_registry_path",
        lambda: str(private / "profile_identity.json"),
    )

    (live / "Current.json").write_text(
        json.dumps({"name": "Current", "bundle_id": "filamenthub:10"}),
        encoding="utf-8",
    )
    (live / "Current.info").write_text(
        "sync_info = filamenthub:preset:10\n", encoding="utf-8"
    )
    (live / "Stale.json").write_text(
        json.dumps({"name": "Stale", "bundle_id": "filamenthub:20"}),
        encoding="utf-8",
    )
    (live / "Orphan.info").write_text(
        "sync_info = filamenthub:preset:30\n", encoding="utf-8"
    )
    (live / "Broken current.info").write_text(
        "sync_info = filamenthub:preset:10\n", encoding="utf-8"
    )
    (live / "Broken.json").write_text(
        json.dumps({"name": "Broken", "bundle_id": "filamenthub:not-an-id"}),
        encoding="utf-8",
    )
    # Written by an older plugin version: no ownership marker, but it sits inside
    # the FilamentHub bundle folder, where only this plugin writes.
    (live / "Legacy unmarked.json").write_text(
        json.dumps({"name": "Legacy unmarked"}), encoding="utf-8"
    )

    removed, removed_ids = plugin_module.quarantine_unwanted_managed_preset_files(
        str(live), {10}
    )

    # The FilamentHub tab must show only what is actually synchronised, so an
    # unmarked leftover leaves the live bundle as well — into quarantine, not
    # deletion. Files outside this folder are never touched.
    assert removed == 5
    assert removed_ids == {10, 20, 30}
    assert sorted(path.name for path in live.iterdir()) == [
        "Current.info",
        "Current.json",
    ]
    assert sorted(path.name for path in private.rglob("*.*")) == [
        "Broken current.info",
        "Broken.json",
        "Legacy unmarked.json",
        "Orphan.info",
        "Stale.json",
    ]

def test_sync_cleanup_does_not_require_a_surviving_state_record(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "live"
    live.mkdir()
    private = tmp_path / "private"
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(live))
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(
        plugin_module,
        "profile_identity_registry_path",
        lambda: str(private / "profile_identity.json"),
    )

    current = {"name": "Current", "bundle_id": "filamenthub:10"}
    current_path = live / "Current.json"
    current_path.write_text(json.dumps(current), encoding="utf-8")
    stale_path = live / "Stale.json"
    stale_path.write_text(
        json.dumps({"name": "Stale", "bundle_id": "filamenthub:20"}),
        encoding="utf-8",
    )
    state = {
        "10": {
            "updated_at": "2026-08-01",
            "hash": plugin_module.preset_content_hash(current),
            "name": "Current",
        }
    }
    monkeypatch.setattr(plugin_module, "load_sync_state", lambda: state)
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda value: None)
    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda path, **kwargs: (
            200,
            json.dumps({
                "items": [{
                    "id": 10,
                    "name": "Current",
                    "updated_at": "2026-08-01",
                }]
            }).encode("utf-8"),
        ),
    )
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

    plugin_module.FilamentHubCatalog()._do_sync(
        "token", set(), announce=False, source_instance_id="fixture"
    )

    assert current_path.exists()
    assert not stale_path.exists()
    assert "10" in state
    assert "20" not in state
    assert [path.name for path in private.rglob("*.json")] == ["Stale.json"]

def test_failed_remote_update_keeps_last_valid_local_profile(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "live"
    live.mkdir()
    current = {"name": "Current", "bundle_id": "filamenthub:10"}
    current_path = live / "Current.json"
    current_path.write_text(json.dumps(current), encoding="utf-8")
    state = {
        "10": {
            "updated_at": "2026-08-01",
            "hash": plugin_module.preset_content_hash(current),
            "name": "Current",
        }
    }
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(live))
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(plugin_module, "load_sync_state", lambda: state)
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda value: None)
    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda path, **kwargs: (
            200,
            json.dumps({
                "items": [{
                    "id": 10,
                    "name": "Current",
                    "updated_at": "2026-08-02",
                }]
            }).encode("utf-8"),
        ),
    )
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
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_pull_one", lambda *args, **kwargs: None)

    catalog._do_sync("token", set(), announce=False, source_instance_id="fixture")

    assert current_path.exists()
    assert json.loads(current_path.read_text(encoding="utf-8")) == current

def test_explicit_printer_bundle_install_creates_only_managed_profiles(
    plugin_module, monkeypatch, tmp_path
):
    monkeypatch.setattr(plugin_module, "user_bundle_dir", lambda: str(tmp_path))
    machine_dir = tmp_path / "machine"
    machine_dir.mkdir()
    unmanaged = machine_dir / "Workshop 0.4.json"
    unmanaged_payload = {
        "name": "Workshop 0.4",
        "type": "machine",
        "printer_settings_id": "Workshop 0.4",
    }
    unmanaged.write_text(json.dumps(unmanaged_payload), encoding="utf-8")

    counts = plugin_module.install_printer_bundle({
        "format": "filamenthub.orcaslicer.printer-bundle",
        "version": 1,
        "machine_profiles": [{
            "id": 41,
            "name": "Workshop 0.4",
            "profile": {
                "name": "Workshop 0.4",
                "type": "machine",
                "printer_settings_id": "Workshop 0.4",
                "inherits": "fdm_machine_common",
            },
        }],
        "process_profiles": [{
            "id": 77,
            "name": "Fast 0.20",
            "profile": {
                "name": "Fast 0.20",
                "type": "process",
                "print_settings_id": "Fast 0.20",
                "inherits": "fdm_process_common",
                "compatible_printers": ["Workshop 0.4"],
            },
        }],
    })

    managed_machine = machine_dir / "Workshop 0.4 (FH-Machine-41).json"
    managed_process = tmp_path / "process" / "Fast 0.20.json"
    machine_payload = json.loads(managed_machine.read_text(encoding="utf-8"))
    process_payload = json.loads(managed_process.read_text(encoding="utf-8"))

    assert counts == {"machine": 1, "process": 1}
    assert json.loads(unmanaged.read_text(encoding="utf-8")) == unmanaged_payload
    assert machine_payload["printer_settings_id"] == "Workshop 0.4 (FH-Machine-41)"
    assert "inherits" not in machine_payload
    assert "inherits" not in process_payload
    assert process_payload["compatible_printers"] == [
        "Workshop 0.4 (FH-Machine-41)"
    ]
    assert (machine_dir / "Workshop 0.4 (FH-Machine-41).info").read_text(
        encoding="utf-8"
    ) == "sync_info = filamenthub:machine:41\n"

def test_printer_bundle_toggle_quarantines_only_unshared_managed_profiles(
    plugin_module, monkeypatch, tmp_path
):
    bundle_root = tmp_path / "bundle"
    state_file = tmp_path / "storage" / ".fh_printer_bundles.json"
    quarantine = tmp_path / "quarantine"
    monkeypatch.setattr(plugin_module, "user_bundle_dir", lambda: str(bundle_root))
    monkeypatch.setattr(
        plugin_module, "PRINTER_BUNDLE_STATE_FILE", str(state_file)
    )
    monkeypatch.setattr(
        plugin_module, "managed_preset_quarantine_dir", lambda: str(quarantine)
    )
    machine_dir = bundle_root / "machine"
    machine_dir.mkdir(parents=True)
    unmanaged = machine_dir / "User profile.json"
    unmanaged.write_text(
        json.dumps({"name": "User profile", "type": "machine"}),
        encoding="utf-8",
    )
    bundle = {
        "format": "filamenthub.orcaslicer.printer-bundle",
        "version": 1,
        "machine_profiles": [{
            "id": 41,
            "name": "Workshop 0.4",
            "profile": {"name": "Workshop 0.4", "type": "machine"},
        }],
        "process_profiles": [{
            "id": 77,
            "name": "Fast 0.20",
            "profile": {"name": "Fast 0.20", "type": "process"},
        }],
    }

    plugin_module.install_printer_bundle(bundle, physical_printer_id=12)
    profile_ids = plugin_module.printer_bundle_profile_ids(bundle)
    plugin_module.remember_installed_printer_bundle(13, profile_ids)

    assert plugin_module.installed_printer_bundle_ids([12, 13]) == {12, 13}
    assert plugin_module.remove_installed_printer_bundle(12) == {
        "machine": 0,
        "process": 0,
    }
    assert plugin_module.installed_printer_bundle_ids([12, 13]) == {13}
    assert (machine_dir / "Workshop 0.4.json").exists()

    assert plugin_module.remove_installed_printer_bundle(13) == {
        "machine": 1,
        "process": 1,
    }
    assert plugin_module.installed_printer_bundle_ids([12, 13]) == set()
    assert unmanaged.exists()
    assert not (machine_dir / "Workshop 0.4.json").exists()
    assert len(list(quarantine.rglob("*.json"))) == 2

def test_printer_bundle_status_is_local_only_and_never_fetches_server_bundles(
    plugin_module, monkeypatch, tmp_path
):
    bundle_root = tmp_path / "bundle"
    state_file = tmp_path / "storage" / ".fh_printer_bundles.json"
    monkeypatch.setattr(plugin_module, "user_bundle_dir", lambda: str(bundle_root))
    monkeypatch.setattr(
        plugin_module, "PRINTER_BUNDLE_STATE_FILE", str(state_file)
    )
    bundle = {
        "format": "filamenthub.orcaslicer.printer-bundle",
        "version": 1,
        "machine_profiles": [{
            "id": 41,
            "name": "Legacy machine",
            "profile": {"name": "Legacy machine", "type": "machine"},
        }],
        "process_profiles": [],
    }
    plugin_module.install_printer_bundle(bundle)
    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda *args, **kwargs: pytest.fail("status must not fetch a server bundle"),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_printer_bundle_status",
        lambda request_id, ids: delivered.append((request_id, set(ids))),
    )

    catalog._do_printer_bundle_status("status-1", [12], "token")

    assert delivered == [("status-1", set())]
    assert plugin_module.installed_printer_bundle_ids([12]) == set()

def test_process_only_recovery_is_scoped_and_can_be_removed_offline(
    plugin_module, monkeypatch, tmp_path
):
    bundle_root = tmp_path / "bundle"
    state_file = tmp_path / "storage" / ".fh_printer_bundles.json"
    quarantine = tmp_path / "quarantine"
    source_id = "source-instance-123456"
    account_id = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setattr(plugin_module, "user_bundle_dir", lambda: str(bundle_root))
    monkeypatch.setattr(plugin_module, "PRINTER_BUNDLE_STATE_FILE", str(state_file))
    monkeypatch.setattr(
        plugin_module, "managed_preset_quarantine_dir", lambda: str(quarantine)
    )
    monkeypatch.setattr(plugin_module, "plugin_source_instance_id", lambda: source_id)
    monkeypatch.setattr(
        plugin_module,
        "load_profile_identity_registry",
        lambda: {"version": 1, "account_id": account_id, "profiles": {}},
    )
    monkeypatch.setattr(plugin_module, "save_profile_identity_registry", lambda _value: True)
    unmanaged_dir = bundle_root / "machine"
    unmanaged_dir.mkdir(parents=True)
    unmanaged = unmanaged_dir / "User machine.json"
    unmanaged.write_text(
        json.dumps({"name": "User machine", "type": "machine"}),
        encoding="utf-8",
    )
    profile = {
        "name": "0.20 mm stock machine process",
        "type": "process",
        "compatible_printers": ["Official machine 0.4"],
    }
    recovery = {
        "format": "filamenthub.orcaslicer.printer-recovery",
        "version": 1,
        "scope": {
            "owner_user_id": 7,
            "source_instance_id": source_id,
            "account_id": account_id,
        },
        "machine_profiles": [],
        "process_profiles": [{
            "id": 77,
            "name": profile["name"],
            "profile": profile,
            "content_hash": plugin_module._managed_profile_content_hash(profile),
            "physical_printer_ids": [12],
        }],
    }

    _scope, artifacts, counts = plugin_module.install_printer_recovery(recovery)

    assert counts == {"machine": 0, "process": 1}
    assert artifacts[0]["profile_id"] == 77
    # Repeating the same recovery is a no-op: no duplicate or replacement
    # backup is created for an already current content hash.
    plugin_module.install_printer_recovery(recovery)
    assert len(list((bundle_root / "process").glob("*.json"))) == 1
    assert len(list((bundle_root / "process").glob("*.info"))) == 1
    saved = plugin_module.load_printer_bundle_state()
    assert len(saved["scopes"]) == 1
    assert len(saved["scopes"][0]["artifacts"]) == 1
    local = plugin_module.current_printer_recovery_state(7)
    assert len(local["artifacts"]) == 1
    assert local["artifacts"][0]["ownership"] == "current"
    assert local["artifacts"][0]["contentHash"] == recovery["process_profiles"][0]["content_hash"]

    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda *args, **kwargs: pytest.fail("local cleanup must remain offline"),
    )
    outcome = plugin_module.remove_printer_recovery_artifacts([
        local["artifacts"][0]["artifactKey"]
    ])

    assert len(outcome["removed"]) == 1
    assert outcome["failed"] == []
    assert plugin_module.current_printer_recovery_state(7)["artifacts"] == []
    assert len(list(quarantine.rglob("*.json"))) == 1
    assert unmanaged.is_file()

def test_recovery_inventory_does_not_adopt_another_account_scope(
    plugin_module, monkeypatch, tmp_path
):
    bundle_root = tmp_path / "bundle"
    state_file = tmp_path / "storage" / ".fh_printer_bundles.json"
    source_id = "source-instance-123456"
    first_account = "11111111-1111-4111-8111-111111111111"
    second_account = "22222222-2222-4222-8222-222222222222"
    active_account = {"value": first_account}
    monkeypatch.setattr(plugin_module, "user_bundle_dir", lambda: str(bundle_root))
    monkeypatch.setattr(plugin_module, "PRINTER_BUNDLE_STATE_FILE", str(state_file))
    monkeypatch.setattr(plugin_module, "plugin_source_instance_id", lambda: source_id)
    monkeypatch.setattr(
        plugin_module,
        "load_profile_identity_registry",
        lambda: {"version": 1, "account_id": active_account["value"], "profiles": {}},
    )
    monkeypatch.setattr(plugin_module, "save_profile_identity_registry", lambda _value: True)
    profile = {"name": "Scoped machine", "type": "machine"}
    recovery = {
        "format": "filamenthub.orcaslicer.printer-recovery",
        "version": 1,
        "scope": {
            "owner_user_id": 7,
            "source_instance_id": source_id,
            "account_id": first_account,
        },
        "machine_profiles": [{
            "id": 41,
            "name": profile["name"],
            "profile": profile,
            "content_hash": plugin_module._managed_profile_content_hash(profile),
            "physical_printer_ids": [12],
        }],
        "process_profiles": [],
    }
    plugin_module.install_printer_recovery(recovery)

    active_account["value"] = second_account
    inventory = plugin_module.current_printer_recovery_state(7)

    assert inventory["context"]["account_id"] == second_account
    assert inventory["artifacts"][0]["ownership"] == "foreign"
    foreign_recovery = json.loads(json.dumps(recovery))
    foreign_recovery["scope"]["account_id"] = second_account
    live_path = bundle_root / "machine" / "Scoped machine.json"
    before = live_path.read_bytes()
    with pytest.raises(ValueError, match="Conflicting local managed profiles"):
        plugin_module.install_printer_recovery(foreign_recovery)
    assert live_path.read_bytes() == before

def test_printer_recovery_batch_rolls_back_after_a_partial_replace(
    plugin_module, monkeypatch, tmp_path
):
    bundle_root = tmp_path / "bundle"
    quarantine = tmp_path / "quarantine"
    monkeypatch.setattr(plugin_module, "user_bundle_dir", lambda: str(bundle_root))
    monkeypatch.setattr(
        plugin_module, "managed_preset_quarantine_dir", lambda: str(quarantine)
    )
    original = {
        "format": "filamenthub.orcaslicer.printer-bundle",
        "version": 1,
        "machine_profiles": [],
        "process_profiles": [{
            "id": 77,
            "name": "Shared process",
            "profile": {"name": "Shared process", "type": "process", "layer_height": "0.2"},
        }],
    }
    plugin_module.install_printer_bundle(original)
    live_path = bundle_root / "process" / "Shared process.json"
    before = live_path.read_bytes()
    real_replace = plugin_module.os.replace
    failed = {"value": False}

    def fail_live_info_once(source, target):
        normalized = str(target).replace("\\", "/")
        if (
            not failed["value"]
            and "/process/" in normalized
            and normalized.endswith("Shared process.info")
        ):
            failed["value"] = True
            raise OSError("simulated second-file failure")
        return real_replace(source, target)

    monkeypatch.setattr(plugin_module.os, "replace", fail_live_info_once)
    updated = json.loads(json.dumps(original))
    updated["process_profiles"][0]["profile"]["layer_height"] = "0.28"

    with pytest.raises(OSError, match="simulated second-file failure"):
        plugin_module.install_printer_bundle(updated)

    assert live_path.read_bytes() == before
    assert live_path.with_suffix(".info").is_file()

def test_printer_recovery_update_renames_without_leaving_duplicate(
    plugin_module, monkeypatch, tmp_path
):
    bundle_root = tmp_path / "bundle"
    state_file = tmp_path / "storage" / ".fh_printer_bundles.json"
    quarantine = tmp_path / "quarantine"
    source_id = "source-instance-123456"
    account_id = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setattr(plugin_module, "user_bundle_dir", lambda: str(bundle_root))
    monkeypatch.setattr(plugin_module, "PRINTER_BUNDLE_STATE_FILE", str(state_file))
    monkeypatch.setattr(
        plugin_module, "managed_preset_quarantine_dir", lambda: str(quarantine)
    )
    monkeypatch.setattr(plugin_module, "plugin_source_instance_id", lambda: source_id)
    monkeypatch.setattr(
        plugin_module,
        "load_profile_identity_registry",
        lambda: {"version": 1, "account_id": account_id, "profiles": {}},
    )
    monkeypatch.setattr(
        plugin_module, "save_profile_identity_registry", lambda _value: True
    )
    old_profile = {"name": "Old process name", "type": "process"}
    recovery = {
        "format": "filamenthub.orcaslicer.printer-recovery",
        "version": 1,
        "scope": {
            "owner_user_id": 7,
            "source_instance_id": source_id,
            "account_id": account_id,
        },
        "machine_profiles": [],
        "process_profiles": [{
            "id": 77,
            "name": old_profile["name"],
            "profile": old_profile,
            "content_hash": plugin_module._managed_profile_content_hash(old_profile),
        }],
    }
    plugin_module.install_printer_recovery(recovery)
    updated = json.loads(json.dumps(recovery))
    updated_profile = {"name": "New process name", "type": "process"}
    updated["process_profiles"][0].update({
        "name": updated_profile["name"],
        "profile": updated_profile,
        "content_hash": plugin_module._managed_profile_content_hash(updated_profile),
    })

    plugin_module.install_printer_recovery(updated)

    live_json = list((bundle_root / "process").glob("*.json"))
    live_info = list((bundle_root / "process").glob("*.info"))
    assert [path.name for path in live_json] == ["New process name.json"]
    assert [path.name for path in live_info] == ["New process name.info"]
    assert len(list(quarantine.rglob("*Old process name.json"))) == 1
    inventory = plugin_module.current_printer_recovery_state(7)
    assert len(inventory["artifacts"]) == 1
    assert inventory["artifacts"][0]["contentHash"] == updated[
        "process_profiles"
    ][0]["content_hash"]

def test_printer_recovery_rejects_content_hash_mismatch(plugin_module):
    profile = {"name": "Tampered machine", "type": "machine"}
    recovery = {
        "format": "filamenthub.orcaslicer.printer-recovery",
        "version": 1,
        "machine_profiles": [{
            "id": 41,
            "name": profile["name"],
            "profile": profile,
            "content_hash": "0" * 64,
        }],
        "process_profiles": [],
    }

    with pytest.raises(ValueError, match="content hash mismatch"):
        plugin_module._recovery_bundle_journal_artifacts(recovery)

def test_invalid_recovery_keeps_last_good_and_a_valid_retry_can_replace_it(
    plugin_module, monkeypatch, tmp_path
):
    bundle_root = tmp_path / "bundle"
    state_file = tmp_path / "storage" / ".fh_printer_bundles.json"
    source_id = "source-instance-123456"
    account_id = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setattr(plugin_module, "user_bundle_dir", lambda: str(bundle_root))
    monkeypatch.setattr(plugin_module, "PRINTER_BUNDLE_STATE_FILE", str(state_file))
    monkeypatch.setattr(plugin_module, "plugin_source_instance_id", lambda: source_id)
    monkeypatch.setattr(
        plugin_module,
        "managed_preset_quarantine_dir",
        lambda: str(tmp_path / "quarantine"),
    )
    monkeypatch.setattr(
        plugin_module,
        "load_profile_identity_registry",
        lambda: {"version": 1, "account_id": account_id, "profiles": {}},
    )
    monkeypatch.setattr(
        plugin_module, "save_profile_identity_registry", lambda _value: True
    )

    def recovery_for(profile):
        return {
            "format": "filamenthub.orcaslicer.printer-recovery",
            "version": 1,
            "scope": {
                "owner_user_id": 7,
                "source_instance_id": source_id,
                "account_id": account_id,
            },
            "machine_profiles": [],
            "process_profiles": [
                {
                    "id": 77,
                    "name": profile["name"],
                    "profile": profile,
                    "content_hash": plugin_module._managed_profile_content_hash(
                        profile
                    ),
                }
            ],
        }

    good = {
        "name": "Safe process",
        "type": "process",
        "layer_height": "0.20",
    }
    plugin_module.install_printer_recovery(recovery_for(good))
    live_path = bundle_root / "process" / "Safe process.json"
    last_good = live_path.read_bytes()

    invalid = dict(good, layer_height={"value": 0.28})
    with pytest.raises(ValueError, match="cannot load"):
        plugin_module.install_printer_recovery(recovery_for(invalid))
    assert live_path.read_bytes() == last_good

    retry = dict(good, layer_height="0.28")
    plugin_module.install_printer_recovery(recovery_for(retry))
    assert json.loads(live_path.read_text(encoding="utf-8"))["layer_height"] == "0.28"

def test_managed_artifact_quarantine_rolls_back_partial_move(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "live"
    quarantine = tmp_path / "quarantine"
    live.mkdir()
    json_path = live / "Managed.json"
    info_path = live / "Managed.info"
    json_path.write_text("{}", encoding="utf-8")
    info_path.write_text("sync_info = filamenthub:machine:41\n", encoding="utf-8")
    monkeypatch.setattr(
        plugin_module, "managed_preset_quarantine_dir", lambda: str(quarantine)
    )
    real_replace = plugin_module.os.replace

    def fail_info_move(source, target):
        if str(source).endswith("Managed.info"):
            raise OSError("simulated quarantine failure")
        return real_replace(source, target)

    monkeypatch.setattr(plugin_module.os, "replace", fail_info_move)
    artifact = {
        "json_path": str(json_path),
        "info_path": str(info_path),
    }

    assert not plugin_module._quarantine_managed_preset_artifact(
        artifact, "partial-test"
    )
    assert json_path.is_file()
    assert info_path.is_file()

def test_legacy_parent_repair_touches_only_filamenthub_managed_files(
    plugin_module, monkeypatch, tmp_path
):
    monkeypatch.setattr(plugin_module, "user_bundle_dir", lambda: str(tmp_path))
    machine_dir = tmp_path / "machine"
    filament_dir = tmp_path / "filament"
    process_dir = tmp_path / "process"
    for folder in (machine_dir, filament_dir, process_dir):
        folder.mkdir()

    managed = {
        machine_dir / "Managed machine.json": {
            "bundle_id": "filamenthub:41",
            "inherits": "fdm_machine_common",
        },
        filament_dir / "Managed filament.json": {
            "bundle_id": "filamenthub:42",
            "inherits": "fdm_filament_common",
        },
        process_dir / "Managed process.json": {
            "bundle_id": "filamenthub:43",
            "inherits": "fdm_process_vendor_common",
        },
    }
    for path, payload in managed.items():
        path.write_text(json.dumps(payload), encoding="utf-8")
    unmanaged = machine_dir / "User machine.json"
    unmanaged.write_text(
        json.dumps({"inherits": "fdm_machine_common"}), encoding="utf-8"
    )

    assert plugin_module.repair_local_bundle_parents() == 3
    for path in managed:
        assert "inherits" not in json.loads(path.read_text(encoding="utf-8"))
    assert json.loads(unmanaged.read_text(encoding="utf-8"))["inherits"] == "fdm_machine_common"

def test_printer_bundle_message_is_explicit_and_uses_saved_session(
    plugin_module, monkeypatch
):
    submitted = []
    refreshed = []
    monkeypatch.setattr(
        plugin_module,
        "BACKGROUND_WORKER",
        SimpleNamespace(submit=lambda *args: submitted.append(args)),
    )
    monkeypatch.setattr(
        plugin_module, "load_saved_auth", lambda: {"accessToken": "saved-token"}
    )
    monkeypatch.setattr(
        plugin_module,
        "refresh_user_preset_folder",
        lambda: refreshed.append(True),
    )

    catalog = plugin_module.FilamentHubCatalog()
    catalog.on_message({
        "source": "filamenthub-plugin",
        "type": "install-printer-bundle",
        "requestId": "bundle-1",
        "physicalPrinterId": 12,
        "token": "",
    })

    assert refreshed == [True]
    assert len(submitted) == 1
    assert submitted[0][0].__name__ == "_do_install_printer_bundle"
    assert submitted[0][1:] == ("bundle-1", 12, "saved-token")

    catalog.on_message({
        "source": "filamenthub-plugin",
        "type": "remove-printer-bundle",
        "requestId": "bundle-2",
        "physicalPrinterId": 12,
    })
    catalog.on_message({
        "source": "filamenthub-plugin",
        "type": "printer-bundle-status",
        "requestId": "bundle-3",
        "physicalPrinterIds": [12, 13, 12],
        "token": "",
    })

    assert refreshed == [True, True, True]
    assert submitted[1][0].__name__ == "_do_remove_printer_bundle"
    assert submitted[1][1:] == ("bundle-2", 12)
    assert submitted[2][0].__name__ == "_do_printer_bundle_status"
    assert submitted[2][1:] == ("bundle-3", [12, 13], "saved-token")

def test_recovery_state_observes_originals_before_background_inventory(
    plugin_module, monkeypatch
):
    submitted = []
    refreshed = []
    observations = {
        "machine": {
            "complete": True,
            "presentLocalProfileIds": ["11111111-1111-4111-8111-111111111111"],
        },
        "process": {"complete": False, "presentLocalProfileIds": []},
    }
    monkeypatch.setattr(
        plugin_module,
        "BACKGROUND_WORKER",
        SimpleNamespace(submit=lambda *args: submitted.append(args)),
    )
    monkeypatch.setattr(
        plugin_module,
        "refresh_user_preset_folder",
        lambda: refreshed.append(True),
    )
    monkeypatch.setattr(
        plugin_module, "observe_recovery_originals", lambda: observations
    )

    catalog = plugin_module.FilamentHubCatalog()
    catalog.on_message({
        "source": "filamenthub-plugin",
        "type": "printer-recovery-state",
        "requestId": "recovery-state-1",
        "ownerUserId": 7,
    })

    assert refreshed == [True]
    assert submitted[0][0].__name__ == "_do_printer_recovery_state"
    assert submitted[0][1:] == ("recovery-state-1", 7, observations)

def test_printer_bundle_messages_reject_boolean_ids(plugin_module, monkeypatch):
    submitted = []
    monkeypatch.setattr(
        plugin_module,
        "BACKGROUND_WORKER",
        SimpleNamespace(submit=lambda *args: submitted.append(args)),
    )
    catalog = plugin_module.FilamentHubCatalog()

    for message in (
        {
            "source": "filamenthub-plugin",
            "type": "install-printer-bundle",
            "requestId": "bundle-1",
            "physicalPrinterId": True,
        },
        {
            "source": "filamenthub-plugin",
            "type": "remove-printer-bundle",
            "requestId": "bundle-2",
            "physicalPrinterId": True,
        },
        {
            "source": "filamenthub-plugin",
            "type": "printer-bundle-status",
            "requestId": "bundle-3",
            "physicalPrinterIds": [True],
        },
    ):
        catalog.on_message(message)

    assert submitted == []

def test_happy_hare_mutation_message_rejects_boolean_ids(plugin_module, monkeypatch):
    submitted = []
    monkeypatch.setattr(
        plugin_module,
        "BACKGROUND_WORKER",
        SimpleNamespace(submit=lambda *args: submitted.append(args)),
    )
    capability = plugin_module.FilamentHubCatalog()
    common = {
        "source": "filamenthub-plugin",
        "type": "happy-hare-adopt",
        "requestId": "request-1",
        "materialSystemId": 7,
        "expectedDesiredAssignments": [{"gate": 0, "spool_id": None}],
    }

    capability.on_message({**common, "physicalPrinterId": True})
    capability.on_message({
        **common,
        "physicalPrinterId": 3,
        "expectedDesiredAssignments": [{"gate": 0, "spool_id": True}],
    })

    assert submitted == []

def test_profile_change_reports_automatic_sync_result(plugin_module):
    capability = plugin_module.FilamentHubCatalog()
    calls = []
    capability._auto_sync = lambda **kwargs: calls.append(kwargs) or True

    capability.on_message({
        "source": "filamenthub-plugin",
        "type": "profile-changed",
    })

    assert calls == [{
        "announce": True,
        "scope": "filament",
        "trigger": "profile-change",
    }]

def test_plugin_load_never_opens_a_window_automatically(plugin_module):
    assert "on_load" not in plugin_module.FilamentHubCatalog.__dict__

def test_host_ready_starts_sync_once(plugin_module):
    capability = plugin_module.FilamentHubCatalog()
    calls = []
    capability._auto_sync = lambda **kwargs: calls.append(kwargs) or True

    capability.on_message({
        "source": "filamenthub-plugin",
        "type": "host-ready",
    })
    capability.on_message({
        "source": "filamenthub-plugin",
        "type": "host-ready",
    })
    assert calls == [{
        "announce": True,
        "scope": "all",
        "trigger": "session-start",
    }]

def test_token_refresh_does_not_start_a_second_session_sync(plugin_module, monkeypatch):
    capability = plugin_module.FilamentHubCatalog()
    calls = []
    saved = []
    monkeypatch.setattr(plugin_module, "save_auth", saved.append)
    monkeypatch.setattr(plugin_module.BAMBU_BRIDGE_RUNTIME, "wake", lambda: None)
    capability._auto_sync = lambda **kwargs: calls.append(kwargs) or True

    capability.on_message({
        "source": "filamenthub-plugin",
        "type": "auth-token",
        "accessToken": "first-token",
    })
    capability.on_message({
        "source": "filamenthub-plugin",
        "type": "auth-token",
        "accessToken": "refreshed-token",
    })

    assert saved == ["first-token", "refreshed-token"]
    assert calls == [{
        "announce": True,
        "scope": "all",
        "trigger": "session-auth",
    }]

def test_active_filaments_use_only_saved_user_files(plugin_module, monkeypatch, tmp_path):
    saved_path = tmp_path / "user" / "default" / "filament" / "Local PETG.json"
    saved_path.parent.mkdir(parents=True)
    saved_path.write_text(json.dumps({
        "name": "Local PETG",
        "filament_type": ["PETG"],
        "nozzle_temperature": ["245"],
        "future_orca_object": {"mode": "adaptive", "levels": [1, 3]},
        "future_orca_nullable": None,
    }), encoding="utf-8")

    class Preset:
        name = "Local PETG"
        bundle_id = "user-bundle"
        file = str(saved_path)

        @staticmethod
        def is_user():
            return True

        @staticmethod
        def config_keys():
            return [
                "filament_type",
                "nozzle_temperature",
                "future_orca_object",
                "future_orca_nullable",
            ]

        @staticmethod
        def config_value(key):
            return {
                "filament_type": ["PETG"],
                "nozzle_temperature": ["265"],
                "future_orca_object": {"mode": "adaptive", "levels": [1, 3]},
                "future_orca_nullable": None,
            }[key]

    collection = SimpleNamespace(
        size=lambda: 1,
        preset=lambda _index: Preset(),
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(filaments=collection),
        raising=False,
    )
    monkeypatch.setattr(plugin_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(plugin_module, "_user_preset_folder", "default")

    assert plugin_module.scan_active_user_filaments() == [{
        "name": "Local PETG",
        "locator": "file:filament/local petg.json",
        "profile": {
            "filament_type": ["PETG"],
            "nozzle_temperature": ["245"],
            "future_orca_object": {"mode": "adaptive", "levels": [1, 3]},
            "future_orca_nullable": None,
            "name": "Local PETG",
        },
    }]

def test_local_profile_locator_lowercases_independently_of_platform_normcase(
    plugin_module, monkeypatch, tmp_path
):
    monkeypatch.setattr(plugin_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        plugin_module,
        "resolve_user_preset_folder",
        lambda: "default",
    )
    monkeypatch.setattr(plugin_module.os.path, "normcase", lambda value: value)

    preset_file = (
        tmp_path / "user" / "default" / "filament" / "Local PETG.json"
    )
    assert plugin_module._local_profile_locator_from_path(
        preset_file,
        "filament",
        "Local PETG",
    ) == "file:filament/local petg.json"

def test_save_as_user_filament_becomes_a_new_draft(plugin_module, monkeypatch, tmp_path):
    managed_path = (
        tmp_path
        / "user"
        / "default"
        / "_local"
        / "filamenthub"
        / "filament"
        / "PETG • Lumilayer • High clarity.json"
    )
    saved_as_path = (
        tmp_path / "user" / "default" / "filament" / "High clarity tuned.json"
    )
    managed_path.parent.mkdir(parents=True)
    saved_as_path.parent.mkdir(parents=True)
    managed_path.write_text(json.dumps({"name": "PETG • Lumilayer • High clarity"}), encoding="utf-8")
    managed_path.with_suffix(".info").write_text(
        "sync_info = filamenthub:preset:42\n", encoding="utf-8"
    )
    saved_as_profile = {
        "name": "High clarity tuned",
        "bundle_id": "filamenthub:42",
        "filament_type": ["PETG"],
        "nozzle_temperature": ["255"],
    }
    saved_as_path.write_text(json.dumps(saved_as_profile), encoding="utf-8")

    class Preset:
        def __init__(self, name, path):
            self.name = name
            self.file = str(path)
            self.bundle_id = "filamenthub:42"

        @staticmethod
        def is_user():
            return True

    presets = [
        Preset("PETG • Lumilayer • High clarity", managed_path),
        Preset("High clarity tuned", saved_as_path),
    ]
    collection = SimpleNamespace(
        size=lambda: len(presets),
        preset=lambda index: presets[index],
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(filaments=collection),
        raising=False,
    )
    monkeypatch.setattr(plugin_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(plugin_module, "_user_preset_folder", "default")
    _isolate_profile_identity(plugin_module, monkeypatch, tmp_path)
    monkeypatch.setattr(
        plugin_module,
        "IMPORTED_DRAFTS_FILE",
        str(tmp_path / "imported_drafts.json"),
    )
    sent = []
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda path, _token, payload: (
            sent.extend(payload["profiles"]),
            (200, json.dumps({"results": [{"status": "created"}]}).encode("utf-8")),
        )[1] if path == "/orcaslicer/filaments/import" else pytest.fail(path),
    )

    candidates = plugin_module.scan_active_user_filaments()
    accepted = plugin_module.push_filament_drafts("token", candidates)

    assert [candidate["name"] for candidate in candidates] == ["High clarity tuned"]
    assert len(accepted) == 1
    assert sent[0]["name"] == "High clarity tuned"
    assert sent[0]["external_id"].startswith("orca-local-v1:")
    assert "bundle_id" not in sent[0]["orcaslicer_settings"]
    assert "fhub_id" not in sent[0]
    assert "info_content" not in sent[0]

def test_managed_filament_uses_host_loaded_metadata_chain(
    plugin_module, tmp_path, monkeypatch
):
    managed_path = tmp_path / "OlgaCraft PLA.json"
    parent_path = tmp_path / "Generic PLA @System.json"
    base_path = tmp_path / "fdm_filament_pla.json"
    managed_path.write_text(
        json.dumps(
            {
                "name": "OlgaCraft PLA",
                "bundle_id": "filamenthub:41",
                "setting_id": "FHUB000041",
                "inherits": "Generic PLA @System",
            }
        ),
        encoding="utf-8",
    )
    parent_path.write_text(
        json.dumps(
            {
                "name": "Generic PLA @System",
                "inherits": "fdm_filament_pla",
            }
        ),
        encoding="utf-8",
    )
    base_path.write_text(
        json.dumps({"name": "fdm_filament_pla", "filament_id": "OGFL99"}),
        encoding="utf-8",
    )

    class Preset:
        def __init__(self, name, path, bundle_id=""):
            self.name = name
            self.file = str(path)
            self.bundle_id = bundle_id

        @staticmethod
        def config_keys():
            return [
                "filament_type",
                "filament_colour",
                "nozzle_temperature_range_low",
                "nozzle_temperature_range_high",
            ]

        @staticmethod
        def config_value(key):
            return {
                "filament_type": ["PLA"],
                "filament_colour": ["#3366CC"],
                "nozzle_temperature_range_low": ["190"],
                "nozzle_temperature_range_high": ["230"],
            }[key]

    managed = Preset("OlgaCraft PLA", managed_path, "filamenthub:41")
    parent = Preset("Generic PLA @System", parent_path)
    base = Preset("fdm_filament_pla", base_path)
    by_name = {preset.name: preset for preset in (managed, parent, base)}
    collection = SimpleNamespace(
        size=lambda: 1,
        preset=lambda _index: managed,
        find_preset=lambda name: by_name.get(name),
    )
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(filaments=collection),
        raising=False,
    )

    resolved = plugin_module.scan_managed_host_filaments()[41]

    assert resolved["setting_id"] == "FHUB000041"
    assert resolved["filament_id"] == "OGFL99"
    assert resolved["filament_type"] == ["PLA"]

def test_profile_sync_imports_user_profiles_but_not_selected_system_profile(
    plugin_module, monkeypatch
):
    class Preset:
        def __init__(self, name, *, user=False, bundle_id="system"):
            self.name = name
            self.bundle_id = bundle_id
            self._user = user

        def is_user(self):
            return self._user

        @staticmethod
        def config_keys():
            return ["printer_settings_id", "nozzle_diameter"]

        def config_value(self, key):
            return {
                "printer_settings_id": self.name,
                "nozzle_diameter": ["0.4"],
            }[key]

    selected_system = Preset("Bambu Lab P2S 0.4 nozzle")
    unselected_system = Preset("Bambu Lab A1 mini 0.4 nozzle")
    user_profile = Preset("Workshop Voron", user=True, bundle_id="user")
    collection = SimpleNamespace(
        size=lambda: 3,
        preset=lambda index: [selected_system, unselected_system, user_profile][index],
    )
    bundle = SimpleNamespace(
        printers=collection,
        current_printer_preset=lambda: selected_system,
    )
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: bundle,
        raising=False,
    )

    profiles = plugin_module.scan_user_profiles("machine")

    assert [profile["name"] for profile in profiles] == ["Workshop Voron"]

def test_connection_only_machine_child_is_observed_but_not_imported(
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
        "Workshop Voron",
        {
            **parent_values,
            "inherits": parent.name,
            "print_host": "192.168.1.21:7125",
            "host_type": "moonraker",
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
        lambda: SimpleNamespace(
            printers=collection,
            current_printer_preset=lambda: child,
        ),
        raising=False,
    )

    assert plugin_module.scan_user_profiles("machine") == []
    observation = plugin_module.observe_printer_presets()[0]
    assert observation["preset_name"] == "Workshop Voron"
    assert observation["inherits"] == parent.name
    assert observation["vendor_id"] == "Voron"
    assert observation["has_technical_changes"] is False
    assert observation["profile_fingerprint"] is None
    assert observation["print_host"] == "192.168.1.21:7125"
    assert observation["connection_ref"].startswith("orca-local-v1:")

def test_bambu_candidates_prefer_the_exact_bound_orca_profile(plugin_module):
    observations = [
        {
            "connection_ref": "other-ref",
            "preset_name": "Wrong printer",
            "print_host": "192.168.1.90:8883",
            "is_current": True,
        },
        {
            "connection_ref": "bound-ref",
            "preset_name": "Workshop P2S",
            "print_host": "https://192.168.1.42:8883/",
            "is_current": False,
        },
    ]
    context = {
        "bindings": [
            {
                "connection_ref": "bound-ref",
                "physical_printer_id": 7,
                "status": "bound",
            }
        ]
    }

    assert plugin_module.bambu_host_candidates(observations, context, 7) == [
        {"host": "192.168.1.42", "label": "Workshop P2S"}
    ]
