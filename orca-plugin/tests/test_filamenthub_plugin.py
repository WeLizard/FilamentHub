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
        "inherits": plugin_module.FALLBACK_PARENT,
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


def test_stale_preset_files_are_removed_after_rename(plugin_module, tmp_path):
    (tmp_path / "Old Name__fh_10.json").write_text(
        json.dumps({"bundle_id": "filamenthub:10"}), encoding="utf-8"
    )
    (tmp_path / "Old Name__fh_10.info").write_text("meta", encoding="utf-8")
    keep = plugin_module.preset_file_path(str(tmp_path), "New Name", 10)
    plugin_module.write_json_atomic(keep, {"bundle_id": "filamenthub:10", "name": "New Name"})
    plugin_module.remove_stale_preset_files(str(tmp_path), 10, keep)
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["New Name.json"]


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
            },
        }],
        "process_profiles": [{
            "id": 77,
            "name": "Fast 0.20",
            "profile": {
                "name": "Fast 0.20",
                "type": "process",
                "print_settings_id": "Fast 0.20",
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
    assert process_payload["compatible_printers"] == [
        "Workshop 0.4 (FH-Machine-41)"
    ]
    assert (machine_dir / "Workshop 0.4 (FH-Machine-41).info").read_text(
        encoding="utf-8"
    ) == "sync_info = filamenthub:machine:41\n"


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
            return ["filament_type", "nozzle_temperature"]

        @staticmethod
        def config_value(key):
            return {
                "filament_type": ["PETG"],
                "nozzle_temperature": ["245"],
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
            "name": "Local PETG",
            "bundle_id": "user-bundle",
        },
    }]


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
    (legacy / ".fh_sync.json").write_text('{"known":true}', encoding="utf-8")
    (legacy / "slices").mkdir()
    (legacy / "slices" / "fixture.gcode").write_text("G28", encoding="utf-8")

    monkeypatch.setattr(plugin_module, "PLUGIN_DIR", str(legacy))
    monkeypatch.setattr(plugin_module, "PLUGIN_STORAGE_DIR", str(legacy))
    monkeypatch.setattr(plugin_module, "SYNC_LOG_FILE", str(legacy / ".fh_sync.log"))
    monkeypatch.setattr(plugin_module, "AUTH_FILE", str(legacy / ".auth.json"))
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
    assert plugin_module.SYNC_STATE_FILE == str(storage / ".fh_sync.json")
    assert plugin_module._SLICE_CACHE_DIR == str(storage / "slices")
    assert (storage / ".auth.json").read_text(encoding="utf-8") == (
        '{"accessToken":"fixture"}'
    )
    assert (storage / "slices" / "fixture.gcode").read_text(encoding="utf-8") == "G28"
    assert (legacy / ".auth.json").exists()
    assert (legacy / "slices" / "fixture.gcode").exists()


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
