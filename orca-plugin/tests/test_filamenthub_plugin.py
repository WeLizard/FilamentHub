from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
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
        ("zh_CN", "zh", "目录"),
        ("en_US", "en", "Catalog"),
        ("de_DE", "en", "Catalog"),
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
