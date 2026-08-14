from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
import tomllib
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = PLUGIN_ROOT / "filamenthub_plugin.py"
BUILD_PATH = PLUGIN_ROOT / "build_package.py"
LOCALE_VALIDATOR_PATH = PLUGIN_ROOT / "validate_locales.py"


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


def test_worker_results_use_host_push_with_loopback_fallback(plugin_module):
    page = plugin_module.PAGE
    assert "orca.onMessage(function (data)" in page
    assert "data.source !== 'filamenthub-host'" in page
    assert "type: 'host-ready'" in page
    assert "if (hostPush) return;" in page
    assert "http.server.ThreadingHTTPServer" not in PLUGIN_PATH.read_text(encoding="utf-8")


def test_post_window_tolerates_closed_or_legacy_handles(plugin_module):
    posted = []

    class Window:
        def is_open(self):
            return True

        def post(self, payload):
            posted.append(payload)

    assert plugin_module.post_window(Window(), {"type": "done"})
    assert posted == [{"type": "done"}]
    assert not plugin_module.post_window(None, {})
    assert not plugin_module.post_window(SimpleNamespace(is_open=lambda: True), {})


def test_background_worker_reuses_one_thread_for_bursty_jobs(plugin_module):
    worker = plugin_module.ReusableDaemonWorker("filamenthub-test-worker", idle_timeout=0.2)
    done = threading.Event()
    thread_ids = []

    def record():
        thread_ids.append(threading.get_ident())
        if len(thread_ids) == 2:
            done.set()

    worker.submit(record)
    worker.submit(record)

    assert done.wait(2)
    assert len(set(thread_ids)) == 1


def test_shell_server_stops_without_starting_a_shutdown_worker(plugin_module):
    server = plugin_module.ShellServer()
    url = server.url_for("<!doctype html><title>fixture</title>")
    stop_event = server._server_stop

    assert url.startswith("http://127.0.0.1:")
    assert stop_event is not None
    server.stop()
    assert stop_event.is_set()
    assert server._server is None


def test_shell_server_recovers_when_the_host_denies_thread_start(plugin_module, monkeypatch):
    class DeniedThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            raise PermissionError("denied by fixture")

    monkeypatch.setattr(plugin_module.threading, "Thread", DeniedThread)
    server = plugin_module.ShellServer()

    with pytest.raises(PermissionError, match="denied by fixture"):
        server.url_for("<!doctype html><title>fixture</title>")
    assert server._server is None
    assert server._server_stop is None


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


@pytest.mark.parametrize(
    ("host_language", "expected", "catalog_label"),
    [
        ("ru_RU", "ru", "Каталог"),
        ("zh_CN", "zh_CN", "目录"),
        ("zh-TW", "zh_TW", "目錄"),
        ("en_US", "en", "Catalog"),
        ("de_DE", "de", "Catalog"),
    ],
)
def test_shell_uses_orca_ui_language(
    plugin_module, monkeypatch, host_language, expected, catalog_label
):
    monkeypatch.setattr(
        plugin_module.orca.host,
        "app_language",
        lambda: host_language,
        raising=False,
    )

    rendered = plugin_module.render_page()

    assert f"var hostLanguage = '{expected}';" in rendered
    assert f"?lng={expected}" in rendered
    assert json.dumps(catalog_label, ensure_ascii=False) in rendered
    assert "__HOST_UI_LANGUAGE__" not in rendered
    assert "__EMBED_URL__" not in rendered


def test_shell_language_falls_back_on_older_or_uninitialized_hosts(plugin_module, monkeypatch):
    monkeypatch.delattr(plugin_module.orca.host, "app_language", raising=False)
    rendered = plugin_module.render_page()
    assert "var hostLanguage = '';" in rendered
    assert "?lng=" not in rendered

    def unavailable():
        raise RuntimeError("OrcaSlicer application is not initialized")

    monkeypatch.setattr(plugin_module.orca.host, "app_language", unavailable, raising=False)
    rendered = plugin_module.render_page()
    assert "var hostLanguage = '';" in rendered
    assert "?lng=" not in rendered


def test_shell_keeps_default_button_copy_without_embedded_locales(plugin_module, monkeypatch):
    monkeypatch.setattr(plugin_module, "UI_COPY", {})

    rendered = plugin_module.render_page()

    assert '>Catalog</button>' in rendered
    assert '>Profile</button>' in rendered
    assert '>Wiki</button>' in rendered
    assert "element && typeof text === 'string' && text.length > 0" in rendered


def test_log_button_is_hidden_by_default_and_requires_explicit_dev_opt_in(
    plugin_module, monkeypatch
):
    assert '<button id="diag" hidden' in plugin_module.render_page()

    monkeypatch.setenv("FILAMENTHUB_SHOW_LOG", "1")
    enabled_module = _load_module(
        PLUGIN_PATH,
        "filamenthub_plugin_diagnostics_enabled_test",
    )

    rendered = enabled_module.render_page()
    assert '<button id="diag"' in rendered
    assert '<button id="diag" hidden' not in rendered


def test_native_plugin_messages_follow_orca_ui_language(plugin_module, monkeypatch):
    messages = []
    monkeypatch.setattr(
        plugin_module.orca.host,
        "app_language",
        lambda: "ru_RU",
        raising=False,
    )
    monkeypatch.setattr(
        plugin_module.orca.host.ui,
        "message",
        lambda text, **kwargs: messages.append((text, kwargs)),
        raising=False,
    )
    plugin_module.refresh_ui_language()

    plugin_module.FilamentHubCatalog()._do_sync("", set(), announce=True)

    assert messages == [(
        "Войдите в FilamentHub в окне плагина и повторите синхронизацию.",
        {"title": "FilamentHub", "icon": "warning"},
    )]


def test_every_orca_locale_is_preserved_and_missing_catalogs_fall_back_per_key(
    plugin_module, tmp_path, monkeypatch
):
    for locale in plugin_module.ORCA_UI_LOCALES:
        assert plugin_module.normalize_ui_language(locale) == locale

    (tmp_path / "en.json").write_text(
        json.dumps({"shared": "English", "englishOnly": "Fallback"}),
        encoding="utf-8",
    )
    (tmp_path / "de.json").write_text(
        json.dumps({"shared": "Deutsch"}),
        encoding="utf-8",
    )
    catalogs = plugin_module.load_ui_catalogs(str(tmp_path))
    monkeypatch.setattr(plugin_module, "UI_COPY", catalogs)

    assert plugin_module.resolved_ui_catalog("de_DE") == {
        "shared": "Deutsch",
        "englishOnly": "Fallback",
    }
    assert plugin_module.resolved_ui_catalog("pt_BR") == {
        "shared": "English",
        "englishOnly": "Fallback",
    }


def test_invalid_optional_catalog_cannot_break_plugin_startup(plugin_module, tmp_path):
    (tmp_path / "en.json").write_text('{"ready":"Ready"}', encoding="utf-8")
    (tmp_path / "ru.json").write_text("not-json", encoding="utf-8")
    (tmp_path / "xx.json").write_text('{"ready":"Unknown"}', encoding="utf-8")

    assert plugin_module.load_ui_catalogs(str(tmp_path)) == {"en": {"ready": "Ready"}}


def test_bundled_locale_catalogs_are_valid():
    validator = _load_module(LOCALE_VALIDATOR_PATH, "filamenthub_locale_validator_test")
    assert validator.validate_catalogs() == []


def test_safe_filename_handles_windows_names_and_bounds(plugin_module):
    assert plugin_module.safe_filename("CON") == "_CON"
    assert plugin_module.safe_filename('bad<>:"/\\|?* name. ') == "bad_________ name"
    assert plugin_module.safe_filename("Legacy [fh]") == "Legacy _fh"
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


def test_info_marker_keeps_managed_identity_after_orca_save(plugin_module, tmp_path):
    path = tmp_path / "Managed PLA.json"
    path.write_text(json.dumps({"name": "Managed PLA"}), encoding="utf-8")
    (tmp_path / "Managed PLA.info").write_text(
        "sync_info = filamenthub:preset:42\n", encoding="utf-8"
    )

    assert plugin_module.managed_preset_id(str(path), {"name": "Managed PLA"}) == 42
    assert plugin_module.preset_file_path(str(tmp_path), "Managed PLA", 42) == str(path)
    assert plugin_module.scan_local_fh_presets(str(tmp_path))[42]["path"] == str(path)


def test_pull_keeps_managed_identity_when_server_info_is_unavailable(
    plugin_module, monkeypatch, tmp_path
):
    profile = {
        "name": "Managed PLA",
        "inherits": "fdm_filament_common",
        "filament_type": ["PLA"],
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
    path = tmp_path / "Managed PLA.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "inherits" not in saved
    saved.pop("bundle_id")
    path.write_text(json.dumps(saved), encoding="utf-8")
    assert plugin_module.managed_preset_id(str(path), saved) == 42
    assert plugin_module.scan_local_fh_presets(str(tmp_path))[42]["path"] == str(path)


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
    (live / "My local profile.json").write_text(
        json.dumps({"name": "My local profile"}), encoding="utf-8"
    )

    removed, removed_ids = plugin_module.quarantine_unwanted_managed_preset_files(
        str(live), {10}
    )

    assert removed == 4
    assert removed_ids == {10, 20, 30}
    assert sorted(path.name for path in live.iterdir()) == [
        "Current.info",
        "Current.json",
        "My local profile.json",
    ]
    assert sorted(path.name for path in private.rglob("*.*")) == [
        "Broken current.info",
        "Broken.json",
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
            "auto_import_local_presets": False,
            "sync_printer_endpoints": False,
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
            "auto_import_local_presets": False,
            "sync_printer_endpoints": False,
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

    plugin_module.FilamentHubCatalog().on_message({
        "source": "filamenthub-plugin",
        "type": "install-printer-bundle",
        "physicalPrinterId": 12,
        "token": "",
    })

    assert refreshed == [True]
    assert len(submitted) == 1
    assert submitted[0][0].__name__ == "_do_install_printer_bundle"
    assert submitted[0][1:] == (12, "saved-token")


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
    capability._auto_sync = lambda announce=False: calls.append(announce)

    capability.on_message({
        "source": "filamenthub-plugin",
        "type": "profile-changed",
    })

    assert calls == [True]


def test_plugin_load_never_opens_a_window_automatically(plugin_module):
    assert "on_load" not in plugin_module.FilamentHubCatalog.__dict__


def test_host_ready_starts_sync_once(plugin_module):
    capability = plugin_module.FilamentHubCatalog()
    calls = []
    capability._auto_sync = lambda announce=False: calls.append(announce)

    capability.on_message({
        "source": "filamenthub-plugin",
        "type": "host-ready",
    })
    capability.on_message({
        "source": "filamenthub-plugin",
        "type": "host-ready",
    })
    assert calls == [False]


def test_active_filaments_use_the_host_preset_api(plugin_module, monkeypatch):
    class Preset:
        name = "Local PETG"
        bundle_id = "user-bundle"
        file = "Z:/this/file/does/not/need/to/exist.json"

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
                "nozzle_temperature": ["245"],
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

    assert plugin_module.scan_active_user_filaments() == [{
        "name": "Local PETG",
        "profile": {
            "filament_type": ["PETG"],
            "nozzle_temperature": ["245"],
            "future_orca_object": {"mode": "adaptive", "levels": [1, 3]},
            "future_orca_nullable": None,
            "name": "Local PETG",
            "bundle_id": "user-bundle",
        },
    }]


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


def test_build_packages_locale_catalogs_and_checksums(plugin_module, tmp_path):
    builder = _load_module(BUILD_PATH, "filamenthub_build_package_test")
    package_dir = builder.build(tmp_path)
    package = package_dir / "filamenthub_plugin.py"
    metadata = json.loads((package_dir / "package-metadata.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    assert metadata["version"] == plugin_module.PLUGIN_VERSION
    assert metadata["network"] == ["filamenthub.ru", "*.filamenthub.ru"]
    assert metadata["sha256"] == digest
    assert metadata["locales"] == ["en", "ru", "zh_CN", "zh_TW"]
    locale_dir = package_dir / "filamenthub_locales"
    assert {path.name for path in locale_dir.glob("*.json")} == {
        "en.json", "ru.json", "zh_CN.json", "zh_TW.json"
    }
    checksums = (package_dir / "SHA256SUMS").read_text(encoding="utf-8")
    assert f"{digest}  filamenthub_plugin.py\n" in checksums
    assert "filamenthub_locales/ru.json" in checksums

    wheel = tmp_path / "wheels" / (
        f"filamenthub-{plugin_module.PLUGIN_VERSION}-py3-none-any.whl"
    )
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        wheel_source = archive.read("filamenthub_plugin.py")
        top_level = archive.read(
            f"filamenthub-{plugin_module.PLUGIN_VERSION}.dist-info/top_level.txt"
        )
    assert b"\r" not in wheel_source
    assert b"_EMBEDDED_UI_COPY = {}" not in wheel_source
    assert top_level == b"filamenthub_plugin\n"
    assert not any(name.startswith("filamenthub_locales/") for name in names)

    standalone = tmp_path / "standalone_filamenthub_plugin.py"
    standalone.write_bytes(package.read_bytes())
    standalone_module = _load_module(standalone, "filamenthub_standalone_smoke")
    assert set(standalone_module.UI_COPY) == {"en", "ru", "zh_CN", "zh_TW"}
    assert standalone_module.UI_COPY["ru"]["catalog"] == "Каталог"


def test_dev_build_is_single_file_with_localhost_and_embedded_locales(plugin_module, tmp_path):
    builder = _load_module(BUILD_PATH, "filamenthub_dev_build_package_test")

    dev_plugin = builder.build_dev(tmp_path)
    source = dev_plugin.read_text(encoding="utf-8")

    assert 'os.environ.get("FILAMENTHUB_SITE_URL", "http://localhost:3000")' in source
    assert "_EMBEDDED_UI_COPY = {}" not in source
    standalone_module = _load_module(dev_plugin, "filamenthub_dev_standalone_smoke")
    assert standalone_module.DEV_CONTOUR is True
    assert standalone_module.UI_COPY["ru"]["catalog"] == "Каталог"
    standalone_module._CACHED_UI_LANGUAGE = "ru"
    assert standalone_module.ui_text(
        "syncComplete",
        summary=standalone_module.ui_text("summaryCurrent", count=4),
        note="",
    ).strip() == "Синхронизация завершена: актуальны: 4."


def test_combined_build_keeps_dev_and_prod_in_parity(plugin_module, tmp_path):
    builder = _load_module(BUILD_PATH, "filamenthub_combined_build_package_test")

    package_dir, dev_plugin = builder.build_all(tmp_path, wheel=False)
    prod_source = (package_dir / "filamenthub_plugin.py").read_text(encoding="utf-8")
    dev_source = dev_plugin.read_text(encoding="utf-8")

    assert package_dir.name == f"filamenthub-{plugin_module.PLUGIN_VERSION}"
    assert dev_plugin.parent.name == f"filamenthub-{plugin_module.PLUGIN_VERSION}-dev"
    assert (
        dev_source.replace(builder.DEV_SITE_DEFAULT, builder.PROD_SITE_DEFAULT)
        == prod_source
    )


def _isolate_profile_identity(plugin_module, monkeypatch, tmp_path):
    monkeypatch.setattr(
        plugin_module,
        "profile_identity_registry_path",
        lambda: str(tmp_path / "profile_identity.json"),
    )
    monkeypatch.setattr(
        plugin_module,
        "plugin_source_instance_id",
        lambda: "test-source-instance-00000001",
    )


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


def test_automatic_machine_and_process_sync_remains_outbound_only(plugin_module):
    # The normal sync registry contains only outbound import endpoints. Restoring
    # a managed machine/process set is a separate explicit message and is never
    # entered into the automatic reconciliation loop.
    for spec in plugin_module.PROFILE_KINDS.values():
        assert "folder" not in spec
        assert "export_path" not in spec
        assert "pull_path" not in spec


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


def _module_with_pages():
    """The plugin as it loads on the PR #14992 Pages artifact."""
    fake_orca = ModuleType("orca")
    fake_orca.base = object
    fake_orca.plugin = lambda cls: cls
    registered: list = []
    fake_orca.register_capability = registered.append
    fake_orca.script = SimpleNamespace(ScriptPluginCapabilityBase=object)
    fake_orca.pages = SimpleNamespace(PagesPluginCapabilityBase=object)
    fake_orca.host = SimpleNamespace(ui=SimpleNamespace())
    fake_orca.ExecutionResult = SimpleNamespace(success=lambda message: message)
    previous = sys.modules.get("orca")
    sys.modules["orca"] = fake_orca
    try:
        module = _load_module(PLUGIN_PATH, "filamenthub_plugin_with_pages")
    finally:
        if previous is None:
            sys.modules.pop("orca", None)
        else:
            sys.modules["orca"] = previous
    return module, registered


def test_a_slice_is_identified_by_the_machine_it_was_made_for(tmp_path):
    """Only what names the slice travels; figures come from reading the file."""
    module, _ = _module_with_slicing()
    gcode = tmp_path / "Cube_PETG.gcode"
    gcode.write_text(
        chr(10).join(
            [
                "; generated by OrcaSlicer 2.4.2 on 2026-07-11 at 10:39:05",
                "G1 X1 Y1 E1",
                "; total filament used [g] = 151.22",
                '; printer_settings_id = "Voron 2.4 350 0.4 nozzle"',
                '; printer_model = "Voron 2.4 350"',
            ]
        ),
        encoding="utf-8",
    )

    identity = module._read_slice_identity(str(gcode))

    assert identity["printer_settings_id"] == "Voron 2.4 350 0.4 nozzle"
    assert identity["printer_model"] == "Voron 2.4 350"
    assert identity["slicer_version"] == "2.4.2"
    # Weights stay out of it: the file is the one source of them.
    assert not any("weight" in key or "seconds" in key for key in identity)


def test_managed_profile_identities_are_written_per_kind_and_tool_once(
    tmp_path, monkeypatch
):
    """One numeric id may exist in three tables; kind and tool keep it exact."""
    module, _ = _module_with_slicing()
    monkeypatch.setattr(module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(module, "_user_preset_folder", "default")

    managed = {
        "filament": ("Material", 7),
        "process": ("Process", 7),
        "machine": ("Machine", 7),
    }
    for folder, (name, entity_id) in managed.items():
        target = tmp_path / "user" / "default" / "_local" / "filamenthub" / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / (name + ".json")).write_text(
            json.dumps({"name": name, "bundle_id": "filamenthub:%d" % entity_id}),
            encoding="utf-8",
        )

    config = {
        "filament_settings_id": '"_local/filamenthub/Material";"Generic PETG @System"',
        "print_settings_id": "_local/filamenthub/Process",
        "printer_settings_id": "_local/filamenthub/Machine",
    }
    ctx = SimpleNamespace(config_value=lambda key: config.get(key))
    identities = module._slice_managed_identities(ctx)
    gcode = tmp_path / "managed.gcode"
    gcode.write_text(
        chr(10).join(
            [
                "; generated by OrcaSlicer 2.5.0-dev",
                "; print_settings_id = Process",
                "; printer_settings_id = Machine",
            ]
        ),
        encoding="utf-8",
    )

    assert identities == [
        {"kind": "material_preset", "tool_index": 0, "id": 7},
        {"kind": "print_profile", "tool_index": None, "id": 7},
        {"kind": "printer_profile", "tool_index": None, "id": 7},
    ]
    assert module._append_fhub_slice_identities(str(gcode), identities)
    assert module._append_fhub_slice_identities(str(gcode), identities)

    content = gcode.read_text(encoding="utf-8")
    assert content.count("fhub_identity_v1") == 3
    assert "kind=material_preset;tool=0;id=7" in content
    reported = module._read_slice_identity(str(gcode))
    assert reported["fhub_print_profile_id"] == 7
    assert reported["fhub_printer_profile_id"] == 7


def _slice_storage(module, tmp_path, monkeypatch):
    """Index and cache in a scratch dir, and a temp root nothing else lives in."""
    monkeypatch.setattr(module, "_SLICE_INDEX_FILE", str(tmp_path / "slices.json"))
    monkeypatch.setattr(module, "_SLICE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path / "no-temp-here"))


def test_the_path_stays_behind_a_key_the_site_can_ask_with(tmp_path, monkeypatch):
    """A path carries a person's folders, so only a key leaves this machine."""
    module, _ = _module_with_slicing()
    _slice_storage(module, tmp_path, monkeypatch)
    gcode = tmp_path / "Cube_PETG.gcode"
    gcode.write_text("; generated by OrcaSlicer 2.4.2", encoding="utf-8")

    key = module._remember_slice_path(str(gcode))

    assert key and str(gcode) not in key
    assert module.slice_path_for_key(key) == str(gcode)
    assert module.slice_path_for_key("nothing-like-it") is None

    gcode.unlink()
    assert module.slice_path_for_key(key) is None


def test_a_slice_sent_to_a_printer_survives_the_host_deleting_it(tmp_path, monkeypatch):
    """Uploading writes a temp file the host removes; a copy keeps it countable."""
    module, _ = _module_with_slicing()
    _slice_storage(module, tmp_path, monkeypatch)
    upload = tmp_path / ".OrcaSlicer.upload.5ca1-0810"
    upload.write_text("; generated by OrcaSlicer 2.4.2", encoding="utf-8")

    key = module._remember_slice_path(str(upload), "Cube_PETG.gcode")
    upload.unlink()

    entry = module.slice_entry_for_key(key)
    assert entry is not None and entry["path"] != str(upload)
    # The copy is named after the key, so the name a person gave the print is
    # what the calculation must be labelled with.
    assert entry["name"] == "Cube_PETG.gcode"
    with open(entry["path"], "r", encoding="utf-8") as fh:
        assert fh.read() == "; generated by OrcaSlicer 2.4.2"


def test_only_the_newest_few_uploads_are_kept(tmp_path, monkeypatch):
    """The cache is a convenience, not an archive of someone's disk."""
    module, _ = _module_with_slicing()
    _slice_storage(module, tmp_path, monkeypatch)

    keys = []
    for number in range(module._SLICE_CACHE_FILES + 3):
        upload = tmp_path / (".OrcaSlicer.upload.%d" % number)
        upload.write_text("; slice %d" % number, encoding="utf-8")
        keys.append(module._remember_slice_path(str(upload)))
        upload.unlink()

    kept = [key for key in keys if module.slice_path_for_key(key)]
    assert len(kept) == module._SLICE_CACHE_FILES
    assert keys[-1] in kept


def test_the_reporter_is_registered_only_where_the_host_can_slice():
    """A host without the slicing pipeline must still load the plugin."""
    with_slicing, registered = _module_with_slicing()
    assert with_slicing.FilamentHubSliceReporter is not None
    with_slicing.FilamentHubPlugin().register_capabilities()
    assert with_slicing.FilamentHubSliceReporter in registered


def test_without_the_pipeline_the_plugin_still_registers_its_window(plugin_module):
    assert plugin_module.FilamentHubSliceReporter is None
    plugin_module.FilamentHubPlugin().register_capabilities()


def test_pages_host_registers_a_tab_instead_of_the_window_action():
    module, registered = _module_with_pages()
    module.FilamentHubPlugin().register_capabilities()
    assert module.FilamentHubPage in registered
    assert module.FilamentHubCatalog not in registered


def test_page_icon_materializes_for_a_single_file_install(
    plugin_module, tmp_path, monkeypatch
):
    missing = tmp_path / "not-packaged.svg"
    monkeypatch.setattr(plugin_module, "PACKAGED_ICON_PATH", str(missing))
    monkeypatch.setattr(plugin_module, "ICON_PATH", str(missing))
    monkeypatch.setattr(plugin_module, "PLUGIN_STORAGE_DIR", str(tmp_path))
    icon = plugin_module.ensure_icon()
    assert icon == str(tmp_path / "filamenthub.svg")
    assert (tmp_path / "filamenthub.svg").read_bytes() == plugin_module._ICON_SVG


def test_host_storage_migrates_mutable_state_without_deleting_legacy(
    plugin_module, tmp_path, monkeypatch
):
    legacy = tmp_path / "plugin"
    storage = tmp_path / "plugin_data" / "filamenthub"
    legacy.mkdir()
    (legacy / ".auth.json").write_text('{"accessToken":"fixture"}', encoding="utf-8")
    (legacy / ".fh_bambu.json").write_text(
        '{"version":1,"source_instance_id":"fixture-instance-0001","printers":[]}',
        encoding="utf-8",
    )
    (legacy / ".fh_sync.json").write_text('{"known":true}', encoding="utf-8")
    (legacy / "slices").mkdir()
    (legacy / "slices" / "fixture.gcode").write_text("G28", encoding="utf-8")

    monkeypatch.setattr(plugin_module, "PLUGIN_DIR", str(legacy))
    monkeypatch.setattr(plugin_module, "PLUGIN_STORAGE_DIR", str(legacy))
    monkeypatch.setattr(plugin_module, "SYNC_LOG_FILE", str(legacy / ".fh_sync.log"))
    monkeypatch.setattr(plugin_module, "AUTH_FILE", str(legacy / ".auth.json"))
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(legacy / ".fh_bambu.json"))
    monkeypatch.setattr(
        plugin_module, "IMPORTED_DRAFTS_FILE", str(legacy / ".fh_imported.json")
    )
    monkeypatch.setattr(plugin_module, "SYNC_STATE_FILE", str(legacy / ".fh_sync.json"))
    monkeypatch.setattr(plugin_module, "_SLICE_INDEX_FILE", str(legacy / ".fh_slices.json"))
    monkeypatch.setattr(plugin_module, "_SLICE_CACHE_DIR", str(legacy / "slices"))
    monkeypatch.setattr(
        plugin_module.orca.host,
        "plugin",
        SimpleNamespace(storage=lambda: str(storage)),
        raising=False,
    )

    plugin_module.FilamentHubPlugin().register_capabilities()

    assert plugin_module.PLUGIN_STORAGE_DIR == str(storage)
    assert plugin_module.AUTH_FILE == str(storage / ".auth.json")
    assert plugin_module.BAMBU_CONFIG_FILE == str(storage / ".fh_bambu.json")
    assert plugin_module.SYNC_STATE_FILE == str(storage / ".fh_sync.json")
    assert plugin_module._SLICE_CACHE_DIR == str(storage / "slices")
    assert (storage / ".auth.json").read_text(encoding="utf-8") == (
        '{"accessToken":"fixture"}'
    )
    assert (storage / ".fh_bambu.json").exists()
    assert (storage / "slices" / "fixture.gcode").read_text(encoding="utf-8") == "G28"
    assert (legacy / ".auth.json").exists()
    assert (legacy / "slices" / "fixture.gcode").exists()


def test_host_without_storage_uses_data_root_outside_replaceable_plugin_dir(
    plugin_module, tmp_path, monkeypatch
):
    data_root = tmp_path / "orca-data"
    legacy = data_root / "orca_plugins" / "filamenthub_plugin.py"
    stable = data_root / ".filamenthub" / "orca-plugin"
    legacy.mkdir(parents=True)
    (legacy / ".auth.json").write_text('{"accessToken":"fixture"}', encoding="utf-8")
    (legacy / ".fh_bambu.json").write_text(
        '{"version":1,"source_instance_id":"fixture-instance-0001","printers":[]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(plugin_module, "PLUGIN_DIR", str(legacy))
    monkeypatch.setattr(plugin_module, "PLUGIN_STORAGE_DIR", str(legacy))
    monkeypatch.setattr(plugin_module, "SYNC_LOG_FILE", str(legacy / ".fh_sync.log"))
    monkeypatch.setattr(plugin_module, "AUTH_FILE", str(legacy / ".auth.json"))
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(legacy / ".fh_bambu.json"))
    monkeypatch.setattr(
        plugin_module, "IMPORTED_DRAFTS_FILE", str(legacy / ".fh_imported.json")
    )
    monkeypatch.setattr(plugin_module, "SYNC_STATE_FILE", str(legacy / ".fh_sync.json"))
    monkeypatch.setattr(plugin_module, "_SLICE_INDEX_FILE", str(legacy / ".fh_slices.json"))
    monkeypatch.setattr(plugin_module, "_SLICE_CACHE_DIR", str(legacy / "slices"))
    monkeypatch.setattr(
        plugin_module.orca.host,
        "plugin",
        SimpleNamespace(),
        raising=False,
    )

    assert plugin_module.configure_plugin_storage() is True

    assert plugin_module.PLUGIN_STORAGE_DIR == str(stable)
    assert plugin_module.AUTH_FILE == str(stable / ".auth.json")
    assert plugin_module.BAMBU_CONFIG_FILE == str(stable / ".fh_bambu.json")
    assert (stable / ".auth.json").read_text(encoding="utf-8") == (
        '{"accessToken":"fixture"}'
    )
    assert (stable / ".fh_bambu.json").exists()
    assert (legacy / ".auth.json").exists()


def _bambu_report(**overrides):
    report = {
        "ams": {
            "tray_now": "1",
            "tray_exist_bits": "3",
            "ams": [
                {
                    "id": "0",
                    "tray": [
                        {
                            "id": "0",
                            "tray_type": "PLA",
                            "tray_color": "FF6A13FF",
                            "remain": 100,
                            "remain_g": 812,
                            "tray_uuid": "D1E2F3",
                        },
                        {
                            "id": "1",
                            "tray_type": "PETG",
                            "tray_color": "1F8A70FF",
                            "remain": -1,
                            "remain_g": -1,
                            "tray_uuid": "00000000",
                        },
                        {
                            "id": "2",
                            "tray_type": "",
                            "tray_color": "00000000",
                            "remain": -1,
                            "tray_uuid": "00000000",
                        },
                    ],
                }
            ],
        }
    }
    report.update(overrides)
    return report


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


def test_bambu_snapshot_keeps_tag_identity_local(plugin_module):
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
    serialized = json.dumps(snapshot)
    assert "provider_uid" not in serialized
    assert "D1E2F3" not in serialized
    assert "access_code" not in serialized
    assert "serial" not in serialized


def _bambu_material_target():
    return {
        "preset_id": 41,
        "name": "OlgaCraft PLA",
        "filament_id": "GFL99",
        "setting_id": "GFSL99_01",
        "material": "PLA",
        "color_hex": "3366CC",
        "nozzle_temp_min": 190,
        "nozzle_temp_max": 230,
    }


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
        lambda _token: (
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

    plugin_module.configure_bambu_bridge(
        3, 4, "192.168.1.42", "local-secret", "SERIAL-1", "fhpb_first"
    )
    plugin_module.configure_bambu_bridge(
        3, 5, "192.168.1.43", "new-secret", "SERIAL-2", "fhpb_second"
    )

    stored = plugin_module.load_bambu_config()
    assert len(stored["printers"]) == 1
    assert stored["printers"][0]["material_system_id"] == 5
    assert stored["printers"][0]["access_code"] == "new-secret"
    assert stored["printers"][0]["bridge_token"] == "fhpb_second"
    assert len(stored["source_instance_id"]) >= 16
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
        lambda _path, _token, _payload: (401, b""),
    )

    runtime = plugin_module.BambuBridgeRuntime()
    monkeypatch.setattr(runtime._wake, "wait", lambda _timeout: True)
    runtime._run()

    assert plugin_module.load_bambu_config()["printers"] == []


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
            json.dumps({"bridge_token": "fhpb_fresh-token"}).encode("utf-8"),
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
        "http_delete_bridge",
        lambda path, token: revoked.append((path, token)) or 204,
    )
    monkeypatch.setattr(
        plugin_module,
        "remove_bambu_bridge",
        lambda physical_printer_id: removed.append(physical_printer_id) or True,
    )
    monkeypatch.setattr(plugin_module, "ui_text", lambda key: key)
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver_sync_result", delivered.append)

    catalog._do_configure_bambu(3, 5, "printer.local", "secret", "", "pair-code")

    assert revoked == [("/printer-bridge/connection", "fhpb_fresh-token")]
    assert removed == [3]
    assert delivered == ["bambuInvalid"]


def test_fresh_bambu_pair_and_first_snapshot_share_one_source_identity(
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
    captured = {}

    def pair(_path, _token, payload):
        captured["pair_source"] = payload["source_instance_id"]
        return 200, json.dumps({"bridge_token": "fhpb_fresh-token"}).encode("utf-8")

    def snapshot(_path, _token, payload):
        captured["snapshot_source"] = payload["source_instance_id"]
        return 200, b"{}"

    monkeypatch.setattr(plugin_module, "http_post_json", pair)
    monkeypatch.setattr(plugin_module, "http_post_bridge_json", snapshot)
    monkeypatch.setattr(plugin_module.BAMBU_BRIDGE_RUNTIME, "wake", lambda: None)
    monkeypatch.setattr(plugin_module, "ui_text", lambda key: key)
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver_sync_result", delivered.append)

    catalog._do_configure_bambu(3, 5, "printer.local", "secret", "", "pair-code")

    assert captured["pair_source"] == captured["snapshot_source"]
    stored = plugin_module.load_bambu_config()
    assert stored["source_instance_id"] == captured["pair_source"]
    assert len(stored["printers"]) == 1
    assert delivered == ["bambuSaved"]


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
