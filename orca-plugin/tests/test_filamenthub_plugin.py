from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tomllib
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = PLUGIN_ROOT / "filamenthub_plugin.py"
BUILD_PATH = PLUGIN_ROOT / "build_package.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plugin_module():
    fake_orca = ModuleType("orca")
    fake_orca.base = object
    fake_orca.plugin = lambda cls: cls
    fake_orca.register_capability = lambda _capability: None
    fake_orca.script = SimpleNamespace(ScriptPluginCapabilityBase=object)
    fake_orca.host = SimpleNamespace(ui=SimpleNamespace())
    fake_orca.ExecutionResult = SimpleNamespace(success=lambda message: message)
    previous = sys.modules.get("orca")
    sys.modules["orca"] = fake_orca
    try:
        yield _load_module(PLUGIN_PATH, "filamenthub_plugin_under_test")
    finally:
        if previous is None:
            sys.modules.pop("orca", None)
        else:
            sys.modules["orca"] = previous


def test_pep723_and_runtime_versions_match(plugin_module):
    builder = _load_module(BUILD_PATH, "filamenthub_build_under_test")
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    metadata = builder.extract_metadata(source)
    assert metadata["tool"]["orcaslicer"]["plugin"]["version"] == plugin_module.PLUGIN_VERSION
    assert metadata["tool"]["orcaslicer"]["plugin"]["network"] == [
        "filamenthub.ru",
        "*.filamenthub.ru",
    ]
    assert metadata["dependencies"] == []
    project = tomllib.loads((PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["dynamic"] == ["version"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "filamenthub_plugin.PLUGIN_VERSION"
    }


def test_plugin_hub_version_rejects_prerelease_suffix(plugin_module):
    builder = _load_module(BUILD_PATH, "filamenthub_build_version_test")
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    version = plugin_module.PLUGIN_VERSION
    invalid = source.replace(
        f'# version = "{version}"',
        f'# version = "{version}-alpha.1"',
        1,
    )
    with pytest.raises(ValueError, match="numeric X.Y.Z"):
        builder.extract_metadata(invalid)


def test_shell_accepts_messages_only_from_catalog_frame(plugin_module):
    assert "event.source !== frame.contentWindow" in plugin_module.PAGE
    assert "event.origin !== SITE_ORIGIN" in plugin_module.PAGE


def test_shell_replaces_webview_errors_with_maintenance_status(plugin_module):
    page = plugin_module.PAGE
    assert 'id="service-status"' in page
    assert "FilamentHub is temporarily unavailable" in page
    assert "Your local OrcaSlicer presets are safe" in page
    assert "FilamentHub временно недоступен" in page
    assert "FilamentHub 暂时不可用" in page
    assert "frame.style.visibility = 'hidden'" in page
    assert "markCatalogReady();" in page
    assert "fh_retry=" in page
    assert 'title="FilamentHub catalog"' in page
    assert "prefers-reduced-motion: reduce" in page
    assert "#service-retry:focus-visible" in page


def test_safe_filename_handles_windows_names_and_bounds(plugin_module):
    assert plugin_module.safe_filename("CON") == "_CON"
    assert plugin_module.safe_filename('bad<>:"/\\|?* name. ') == "bad_________ name"
    assert len(plugin_module.safe_filename("x" * 500)) == plugin_module.MAX_FILENAME_LENGTH


def test_preset_paths_are_stable_and_collision_resistant(plugin_module, tmp_path):
    # The file stem is the preset's display name in OrcaSlicer — a free name
    # stays clean, and re-resolving for the same id returns the same path.
    first = plugin_module.preset_file_path(str(tmp_path), "Generic PLA", 10)
    assert first.endswith("Generic PLA.json")
    (tmp_path / "Generic PLA.json").write_text(
        json.dumps({"bundle_id": "filamenthub:10"}), encoding="utf-8"
    )
    assert plugin_module.preset_file_path(str(tmp_path), "Generic PLA", 10) == first
    # A name owned by a different preset (another FilamentHub id or a foreign
    # user preset) is never overwritten — the new file gets a stable suffix.
    second = plugin_module.preset_file_path(str(tmp_path), "Generic PLA", 11)
    assert second.endswith("Generic PLA (FH-11).json")
    (tmp_path / "User PETG.json").write_text(json.dumps({"name": "User PETG"}), encoding="utf-8")
    foreign = plugin_module.preset_file_path(str(tmp_path), "User PETG", 12)
    assert foreign.endswith("User PETG (FH-12).json")


def test_recover_sync_record_never_treats_lost_state_as_remote_newer(plugin_module):
    # The state file dies with plugin updates; a local file without a record
    # must be adopted when identical and pushed when edited — never re-pulled.
    remote = {"name": "PLA", "inherits": "fdm_filament_common", "nozzle_temperature": ["210"]}

    def fake_http_get(path, token=None, **kw):
        return 200, json.dumps(remote).encode("utf-8")

    plugin_module.http_get = fake_http_get
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

    plugin_module.http_get = lambda path, token=None, **kw: (503, b"")
    assert plugin_module.recover_sync_record(5, "tok", set(), local_same, "2026-07-16") is None


def test_stale_preset_files_are_removed_after_rename(plugin_module, tmp_path):
    plugin_module.remove_host_filament = lambda name: False
    (tmp_path / "Old Name__fh_10.json").write_text(
        json.dumps({"bundle_id": "filamenthub:10"}), encoding="utf-8"
    )
    (tmp_path / "Old Name__fh_10.info").write_text("meta", encoding="utf-8")
    keep = plugin_module.preset_file_path(str(tmp_path), "New Name", 10)
    plugin_module.write_json_atomic(keep, {"bundle_id": "filamenthub:10", "name": "New Name"})
    plugin_module.remove_stale_preset_files(str(tmp_path), 10, keep)
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["New Name.json"]


def test_profile_change_reports_automatic_sync_result(plugin_module):
    capability = plugin_module.FilamentHubCatalog()
    calls = []
    capability._auto_sync = lambda announce=False: calls.append(announce)

    capability.on_message({
        "source": "filamenthub-plugin",
        "type": "profile-changed",
    })

    assert calls == [True]


def test_profile_payload_must_be_an_object(plugin_module):
    with pytest.raises(ValueError, match="JSON object"):
        plugin_module.validate_filament_profile([])
    with pytest.raises(ValueError, match="non-empty string"):
        plugin_module.validate_filament_profile({"name": ""})
    profile = {"name": "PLA", "inherits": "Generic PLA"}
    assert plugin_module.validate_filament_profile(profile) is profile


def test_atomic_json_write_replaces_complete_file(plugin_module, tmp_path):
    target = tmp_path / "state.json"
    plugin_module.write_json_atomic(str(target), {"version": 1})
    plugin_module.write_json_atomic(str(target), {"version": 2, "name": "FilamentHub"})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "version": 2,
        "name": "FilamentHub",
    }
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_build_produces_single_file_package_and_checksum(plugin_module, tmp_path):
    builder = _load_module(BUILD_PATH, "filamenthub_build_package_test")
    package_dir = builder.build(tmp_path)
    package = package_dir / "filamenthub_plugin.py"
    metadata = json.loads((package_dir / "package-metadata.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    assert metadata["version"] == plugin_module.PLUGIN_VERSION
    assert metadata["network"] == ["filamenthub.ru", "*.filamenthub.ru"]
    assert metadata["sha256"] == digest
    assert (package_dir / "SHA256SUMS").read_text(encoding="utf-8") == (
        f"{digest}  filamenthub_plugin.py\n"
    )


def test_printer_profiles_never_leave_with_host_credentials(plugin_module, monkeypatch):
    # A printer preset holds the credentials of its network host; they must stay
    # on the user's machine even though the rest of the preset is reported.
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
    assert plugin_module.push_user_profiles("machine", "tok", items, state) == (1, 0)
    path, payload = sent[0]
    assert path == "/orcaslicer/printer-profiles/import"
    settings = payload["profiles"][0]["orcaslicer_settings"]
    assert "printhost_apikey" not in settings
    assert "printhost_password" not in settings
    assert "printhost_user" not in settings
    assert settings["print_host"] == "192.168.1.50"
    assert settings["nozzle_diameter"] == ["0.4"]
    assert payload["profiles"][0]["external_id"] == "voron-350"


def test_unchanged_profiles_are_not_reported_again(plugin_module, monkeypatch):
    calls = []
    monkeypatch.setattr(
        plugin_module, "http_post_json",
        lambda path, token, payload: (calls.append(payload), (200, b"{}"))[1],
    )
    items = [{"name": "0.2mm Standard", "settings": {"layer_height": "0.2"}}]
    state = {}
    assert plugin_module.push_user_profiles("process", "tok", items, state) == (1, 0)
    assert plugin_module.push_user_profiles("process", "tok", items, state) == (0, 0)
    assert len(calls) == 1

    items[0]["settings"]["layer_height"] = "0.3"
    assert plugin_module.push_user_profiles("process", "tok", items, state) == (1, 0)
    assert len(calls) == 2


def test_failed_upload_is_retried_on_the_next_sync(plugin_module, monkeypatch):
    # A rejected batch must not be recorded as reported, or the profile would be
    # silently dropped until the user happens to edit it again.
    monkeypatch.setattr(plugin_module, "http_post_json",
                        lambda path, token, payload: (503, b""))
    items = [{"name": "Voron 350", "settings": {"nozzle_diameter": ["0.4"]}}]
    state = {}
    assert plugin_module.push_user_profiles("machine", "tok", items, state) == (0, 1)
    assert state == {}

    monkeypatch.setattr(plugin_module, "http_post_json",
                        lambda path, token, payload: (200, b"{}"))
    assert plugin_module.push_user_profiles("machine", "tok", items, state) == (1, 0)


def test_plugin_never_writes_machine_or_process_into_the_slicer(plugin_module):
    # Printer and print profiles are collected from OrcaSlicer, never written
    # back: OrcaCloud already syncs those between a user's own installs.
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    assert "user_machine_dir" not in source
    assert "user_process_dir" not in source
    for spec in plugin_module.PROFILE_KINDS.values():
        assert "folder" not in spec


def _module_with_slicing():
    """The plugin as it loads on a host that does have the slicing pipeline."""
    fake_orca = ModuleType("orca")
    fake_orca.base = object
    fake_orca.plugin = lambda cls: cls
    registered: list = []
    fake_orca.register_capability = registered.append
    fake_orca.script = SimpleNamespace(ScriptPluginCapabilityBase=object)
    fake_orca.host = SimpleNamespace(ui=SimpleNamespace())
    fake_orca.ExecutionResult = SimpleNamespace(
        success=lambda message: ("success", message),
        skipped=lambda message: ("skipped", message),
    )
    fake_orca.slicing = SimpleNamespace(
        SlicingPipelineCapabilityBase=object,
        Step=SimpleNamespace(psGCodePostProcess="psGCodePostProcess"),
    )
    previous = sys.modules.get("orca")
    sys.modules["orca"] = fake_orca
    try:
        module = _load_module(PLUGIN_PATH, "filamenthub_plugin_with_slicing")
    finally:
        if previous is None:
            sys.modules.pop("orca", None)
        else:
            sys.modules["orca"] = previous
    return module, registered


def test_slice_summary_is_read_from_a_real_gcode_tail(tmp_path):
    """Orca writes the totals into the file; that is all the plugin sends."""
    module, _ = _module_with_slicing()
    gcode = tmp_path / "Cube_PETG.gcode"
    gcode.write_text(
        "; HEADER_BLOCK_START\n"
        "; generated by OrcaSlicer 2.4.2 on 2026-07-11 at 10:39:05\n"
        "; total layer number: 384\n"
        "; HEADER_BLOCK_END\n"
        "G1 X1 Y1 E1\n"
        "; filament used [g] = 98.40, 52.82, 0.00\n"
        "; total filament used [g] = 151.22\n"
        "; total filament change = 299\n"
        "; estimated printing time (normal mode) = 6h 24m 10s\n"
        '; printer_settings_id = "Voron 2.4 350 0.4 nozzle"\n'
        '; printer_model = "Voron 2.4 350"\n',
        encoding="utf-8",
    )

    summary = module._read_slice_summary(str(gcode))

    assert summary["total_weight_g"] == 151.22
    assert summary["filament_weights_g"] == [98.40, 52.82, 0.00]
    assert summary["estimated_seconds"] == 6 * 3600 + 24 * 60 + 10
    assert summary["filament_changes"] == 299
    assert summary["layer_count"] == 384
    assert summary["printer_settings_id"] == "Voron 2.4 350 0.4 nozzle"
    assert summary["printer_model"] == "Voron 2.4 350"
    assert summary["slicer_version"] == "2.4.2"


def test_a_file_without_orca_totals_reports_nothing(tmp_path):
    module, _ = _module_with_slicing()
    plain = tmp_path / "hand_written.gcode"
    plain.write_text("G28\nG1 X10 Y10 E5\n", encoding="utf-8")

    assert module._read_slice_summary(str(plain)) is None


def test_the_reporter_is_registered_only_where_the_host_can_slice():
    """A host without the slicing pipeline must still load the plugin."""
    with_slicing, registered = _module_with_slicing()
    assert with_slicing.FilamentHubSliceReporter is not None
    with_slicing.FilamentHubPlugin().register_capabilities()
    assert with_slicing.FilamentHubSliceReporter in registered


def test_without_the_pipeline_the_plugin_still_registers_its_window(plugin_module):
    assert plugin_module.FilamentHubSliceReporter is None
    plugin_module.FilamentHubPlugin().register_capabilities()
