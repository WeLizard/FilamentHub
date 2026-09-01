from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import importlib.util
import io
import json
import sys
import threading
import time
import tomllib
import urllib.request
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


@pytest.fixture
def setup_flow(plugin_module, monkeypatch, tmp_path):
    plugin = plugin_module
    monkeypatch.setattr(plugin, "AUTH_FILE", str(tmp_path / "auth.json"))
    context = {
        "source_instance_id": "setup-desktop-instance", "discovery_key": "a" * 64,
        "account_scope": "owner-1", "bindings": [],
    }
    monkeypatch.setattr(plugin, "printer_setup_context", lambda _token: context)
    monkeypatch.setattr(plugin, "_moonraker_json", lambda *_args, **_kwargs: (
        200, {"result": {"objects": ["mmu", "print_stats"]}}, "",
    ))
    monkeypatch.setattr(plugin, "_observe_moonraker_identity", lambda _connection: "b" * 32)
    monkeypatch.setattr(plugin, "read_happy_hare_snapshot", lambda _connection: {
        "gate_count": 4, "gates": [], "printer_hostname": "workshop", "spoolman_support": "pull",
    })
    uploads = []
    monkeypatch.setattr(plugin, "upload_happy_hare_snapshot", lambda *args: uploads.append(args) or (200, {}))
    results = []
    catalog = plugin.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver", lambda _type, **data: results.append(data["result"]) or True)
    return plugin, catalog, context, results, uploads


def setup_manual_probe(catalog):
    catalog._do_printer_setup({
        "type": "printer-setup-local", "operation": "probe", "requestId": "probe",
        "host": "http://printer.local:7125", "apiKey": "local-secret",
    }, "token", [])


def test_setup_inventory_does_not_present_detached_binding_as_connected(setup_flow):
    _plugin, catalog, context, results, _uploads = setup_flow
    context["bindings"] = [{"connection_ref": "ref-1", "physical_printer_id": 7, "status": "detached"}]
    catalog._do_printer_setup({"operation": "list", "requestId": "list"}, "token", [
        {"connection_ref": "ref-1", "label": "Workshop", "print_host": "printer.local"},
    ])
    assert results[-1]["candidates"] == []


def setup_bind_and_activate(catalog, context, probe):
    context["bindings"] = [{"connection_ref": probe["connection"]["connection_ref"],
                            "physical_printer_id": 7, "status": "bound"}]
    catalog._do_printer_setup({"operation": "activate", "requestId": "activate",
                              "physicalPrinterId": 7, "probeId": probe["probeId"]}, "token", [])


@pytest.mark.parametrize("status,mode,digest,expected", [
    ("bound", "pull", "a" * 64, True),
    ("detached", "pull", "a" * 64, False),
    ("bound", "push", "a" * 64, False),
    ("bound", "pull", "b" * 64, False),
    ("bound", "pull", None, False),
])
def test_setup_inventory_link_requires_this_binding_and_current_inventory(plugin_module, status, mode, digest, expected):
    context = {"bindings": [{"connection_ref": "ref-1", "status": status, "inventory_key_digest": "a" * 64}]}
    snapshot = {"spoolman_support": mode, "inventory_key_digest": digest}
    assert plugin_module.setup_inventory_linked(context, "ref-1", snapshot) is expected
    assert not plugin_module.setup_inventory_linked(context, "other-ref", snapshot)


def test_setup_keeps_secrets_local_and_requires_cloud_binding_before_activation(setup_flow):
    plugin, catalog, context, results, uploads = setup_flow
    setup_manual_probe(catalog)
    probe = results[-1]
    assert probe["ok"] and probe["gateCount"] == 4
    assert "printer.local" not in json.dumps(probe) and "local-secret" not in json.dumps(probe)
    assert len(probe["connection"]["device_identity"]["token"]) == 64
    assert uploads == []
    catalog._do_printer_setup({"operation": "activate", "requestId": "unbound",
                              "physicalPrinterId": 7, "probeId": probe["probeId"]}, "token", [])
    assert not results[-1]["ok"] and uploads == []
    assert plugin._local_setup_config()[1]["connections"] == []
    setup_bind_and_activate(catalog, context, probe)
    assert results[-1]["ok"] and len(uploads) == 1
    stored = plugin.local_setup_connections(context)
    assert len(stored) == 1 and stored[0]["api_key"] == "local-secret"
    setup_bind_and_activate(catalog, context, probe)
    assert results[-1]["ok"] and len(plugin.local_setup_connections(context)) == 1
    setup_manual_probe(catalog)
    assert results[-1]["connection"]["connection_ref"] == probe["connection"]["connection_ref"]


@pytest.mark.parametrize("changed", ["account", "identity", "expired"])
def test_setup_revalidates_preview_before_activating(setup_flow, monkeypatch, changed):
    plugin, catalog, context, results, uploads = setup_flow
    setup_manual_probe(catalog)
    probe = results[-1]
    if changed == "account":
        context["account_scope"] = "another-account"
    elif changed == "identity":
        monkeypatch.setattr(plugin, "_observe_moonraker_identity", lambda _connection: "c" * 32)
    else:
        catalog._printer_setup_pending[probe["probeId"]]["expires"] = 0
    setup_bind_and_activate(catalog, context, probe)
    assert not results[-1]["ok"] and uploads == []
    assert plugin._local_setup_config()[1]["connections"] == []


@pytest.mark.parametrize("status,body", [
    (401, {}), (503, {"result": {"objects": []}}), (200, {"result": []}),
])
def test_setup_does_not_infer_direct_feed_from_a_failed_or_malformed_query(
    setup_flow, monkeypatch, status, body,
):
    plugin, catalog, _context, results, uploads = setup_flow
    monkeypatch.setattr(plugin, "_moonraker_json", lambda *_args, **_kwargs: (status, body, ""))
    setup_manual_probe(catalog)
    assert not results[-1]["ok"] and uploads == []


def test_setup_restored_local_connections_are_account_and_binding_scoped(setup_flow, monkeypatch):
    plugin, catalog, context, results, _uploads = setup_flow
    setup_manual_probe(catalog)
    setup_bind_and_activate(catalog, context, results[-1])
    assert len(plugin.verified_local_setup_connections("token")) == 1
    monkeypatch.setattr(plugin, "_observe_moonraker_identity", lambda _connection: "d" * 32)
    assert plugin.verified_local_setup_connections("token") == []
    assert plugin.local_setup_connections({**context, "account_scope": "other"}) == []
    assert plugin.local_setup_connections({**context, "bindings": []}) == []
    assert plugin.local_setup_connections({**context, "bindings": [
        {**context["bindings"][0], "physical_printer_id": 8},
    ]}) == []


def test_setup_local_form_is_not_impersonated_by_catalog_messages(plugin_module):
    assert "if (data.type === 'printer-setup-local') return;" in plugin_module.PAGE
    assert "showPrinterSetupOverlay(data)" in plugin_module.PAGE
    assert "st.resultType === 'printer-setup-result'" in plugin_module.PAGE
    assert "key.value = '';" in plugin_module.PAGE


def test_setup_corrupt_local_record_fails_closed(setup_flow):
    plugin, catalog, context, results, _uploads = setup_flow
    setup_manual_probe(catalog)
    setup_bind_and_activate(catalog, context, results[-1])
    path, config = plugin._local_setup_config()
    config["connections"][0]["device_identity"] = "broken"
    plugin.write_json_atomic(path, config, mode=0o600)
    with pytest.raises(ValueError, match="Invalid local printer connection store"):
        plugin.verified_local_setup_connections("token")


def test_bound_profile_and_manual_alias_do_not_make_same_endpoint_ambiguous(plugin_module, monkeypatch):
    monkeypatch.setattr(plugin_module, "read_happy_hare_snapshot", lambda _connection: {"gate_count": 4})
    inventory = {"printers": [{"id": 7, "connection_refs": ["profile", "manual"]}]}
    connections = [
        {"connection_ref": "profile", "print_host": "printer.local:7125", "api_key": "key"},
        {"connection_ref": "manual", "print_host": "http://printer.local:7125/", "api_key": "key"},
    ]
    _connection, snapshot, _device, error = plugin_module.resolve_happy_hare_connection(
        "token", connections, 7, inventory,
    )
    assert error is None and snapshot["gate_count"] == 4
    connections[1]["print_host"] = "different-printer.local:7125"
    assert plugin_module.resolve_happy_hare_connection("token", connections, 7, inventory)[3] == "ambiguous_connection"


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


def test_background_worker_discards_old_generation_after_plugin_reload(
    plugin_module, monkeypatch
):
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-lifecycle-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    entered = threading.Event()
    release = threading.Event()
    fresh_done = threading.Event()
    stale_results = []
    queued_ran = []
    posted = []

    class Window:
        def is_open(self):
            return True

        def post(self, payload):
            posted.append(payload)

    def stale_job():
        entered.set()
        assert release.wait(2)
        stale_results.append(
            plugin_module.post_window(Window(), {"generation": "stale"})
        )

    worker.submit(stale_job)
    assert entered.wait(2)
    worker.submit(lambda: queued_ran.append(True))

    worker.shutdown(wait_timeout=0)
    worker.activate()
    worker.submit(
        lambda: (
            plugin_module.post_window(Window(), {"generation": "fresh"}),
            fresh_done.set(),
        )
    )
    release.set()

    assert fresh_done.wait(2)
    assert stale_results == [False]
    assert queued_ran == []
    assert posted == [{"generation": "fresh"}]
    worker.shutdown()


def _retire_running_job_before_side_effect(plugin_module, monkeypatch, action):
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-stale-side-effect-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def stale_job():
        entered.set()
        assert release.wait(2)
        try:
            action()
        finally:
            finished.set()

    assert worker.submit(stale_job)
    assert entered.wait(2)
    worker.stop(wait_timeout=0)
    worker.activate()
    release.set()
    assert finished.wait(2)
    worker.stop()


def _retire_running_job_during_action(
    plugin_module, monkeypatch, action, entered, release
):
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-mid-transaction-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    finished = threading.Event()
    errors = []

    def job():
        try:
            action()
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()

    assert worker.submit(job)
    assert entered.wait(2)
    worker.stop(wait_timeout=0)
    worker.activate()
    release.set()
    assert finished.wait(2)
    worker.stop()
    return errors


def test_retired_worker_generation_cannot_start_http_file_upload(
    plugin_module, monkeypatch, tmp_path
):
    source = tmp_path / "fixture.gcode"
    source.write_bytes(b"G28\n")
    requests = []
    monkeypatch.setattr(
        plugin_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: requests.append((args, kwargs)),
    )

    _retire_running_job_before_side_effect(
        plugin_module,
        monkeypatch,
        lambda: plugin_module.http_post_file(
            "/orcaslicer/slices/fixture", "token", str(source)
        ),
    )

    assert requests == []


def test_retired_worker_generation_cannot_start_happy_hare_command(
    plugin_module, monkeypatch
):
    requests = []
    monkeypatch.setattr(
        plugin_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: requests.append((args, kwargs)),
    )

    _retire_running_job_before_side_effect(
        plugin_module,
        monkeypatch,
        lambda: plugin_module._moonraker_json(
            {"print_host": "http://printer.local:7125", "api_key": "secret"},
            "/printer/gcode/script",
            {"script": "MMU_SPOOLMAN REFRESH=1"},
        ),
    )

    assert requests == []


def test_external_operation_authorized_before_stop_finishes_once(
    plugin_module, monkeypatch
):
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-authorized-operation-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    authorized = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    calls = []

    def job():
        try:
            with plugin_module.external_operation():
                authorized.set()
                assert release.wait(2)
                calls.append("io")
        finally:
            finished.set()

    assert worker.submit(job)
    assert authorized.wait(2)
    worker.stop(wait_timeout=0)
    worker.activate()
    release.set()

    assert finished.wait(2)
    assert calls == ["io"]
    worker.stop()


def test_retired_worker_generation_cannot_create_sync_directory(
    plugin_module, monkeypatch, tmp_path
):
    target = tmp_path / "retired-sync"

    _retire_running_job_before_side_effect(
        plugin_module,
        monkeypatch,
        lambda: plugin_module.ensure_directory(str(target)),
    )

    assert not target.exists()


def test_threadpool_probe_inherits_retired_worker_generation(
    plugin_module, monkeypatch
):
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-probe-generation-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    child_started = threading.Event()
    child_release = threading.Event()
    finished = threading.Event()
    requests = []

    def observe(connection):
        child_started.set()
        assert child_release.wait(2)
        return plugin_module._moonraker_json(
            connection,
            "/server/database/item?namespace=moonraker&key=instance_id",
            timeout=3,
        )

    monkeypatch.setattr(plugin_module, "_observe_moonraker_identity", observe)
    monkeypatch.setattr(
        plugin_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: requests.append((args, kwargs)),
    )

    def job():
        try:
            plugin_module._observations_for_sync(
                [{"print_host": "printer.local:7125", "host_type": "moonraker"}],
                discovery_key="ab" * 32,
                local_connections=[{"print_host": "printer.local:7125"}],
            )
        finally:
            finished.set()

    assert worker.submit(job)
    assert child_started.wait(2)
    worker.stop(wait_timeout=0)
    worker.activate()
    child_release.set()

    assert finished.wait(2)
    assert requests == []
    worker.stop()


def test_import_finishes_authorized_artifact_but_skips_stale_host_effects(
    plugin_module, monkeypatch, tmp_path
):
    entered = threading.Event()
    release = threading.Event()
    mutations = []
    reloads = []
    messages = []
    target = tmp_path / "PLA Brand Fixture.json"

    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda *_args, **_kwargs: (200, b'{"name":"Fixture"}'),
    )
    monkeypatch.setattr(plugin_module, "validate_filament_profile", lambda value: value)
    monkeypatch.setattr(plugin_module, "ensure_parent_exists", lambda *_args: None)
    monkeypatch.setattr(plugin_module, "ensure_filament_colour", lambda *_args: None)
    monkeypatch.setattr(plugin_module, "filament_display_name", lambda *_args: "PLA Brand Fixture")
    monkeypatch.setattr(plugin_module, "ensure_bundle_metadata", lambda: None)
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(tmp_path))
    monkeypatch.setattr(plugin_module, "preset_file_path", lambda *_args: str(target))

    def write_info(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("info")
        entered.set()
        assert release.wait(2)

    def write_json(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("json")

    def cleanup(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("cleanup")
        return 0

    monkeypatch.setattr(plugin_module, "write_managed_info", write_info)
    monkeypatch.setattr(plugin_module, "write_json_atomic", write_json)
    monkeypatch.setattr(plugin_module, "remove_stale_preset_files", cleanup)
    monkeypatch.setattr(
        plugin_module.orca.host,
        "reload_local_bundle",
        lambda *_args: reloads.append(True),
        raising=False,
    )
    monkeypatch.setattr(
        plugin_module.orca.host.ui,
        "message",
        lambda *_args, **_kwargs: messages.append(True),
        raising=False,
    )
    catalog = plugin_module.FilamentHubCatalog()

    errors = _retire_running_job_during_action(
        plugin_module,
        monkeypatch,
        lambda: catalog._do_import(7, "token", set()),
        entered,
        release,
    )

    assert errors == []
    assert mutations == ["info", "json", "cleanup"]
    assert reloads == []
    assert messages == []


def test_display_name_migration_keeps_one_authorized_mutation_transaction(
    plugin_module, monkeypatch, tmp_path
):
    entered = threading.Event()
    release = threading.Event()
    mutations = []
    source = tmp_path / "Fixture.json"
    target = tmp_path / "PLA Brand Fixture.json"
    profile = {"name": "Fixture", "filament_type": ["PLA"]}
    local_entry = {
        "path": str(source),
        "profile": profile,
        "version_id": 11,
    }

    monkeypatch.setattr(plugin_module, "preset_file_path", lambda *_args: str(target))
    monkeypatch.setattr(plugin_module, "filament_display_name", lambda *_args: target.stem)
    monkeypatch.setattr(plugin_module, "validate_filament_profile", lambda value: value)

    def write_json(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("json")
        entered.set()
        assert release.wait(2)

    def write_info(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("info")

    def cleanup(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("cleanup")
        return 1

    monkeypatch.setattr(plugin_module, "write_json_atomic", write_json)
    monkeypatch.setattr(plugin_module, "write_bytes_atomic", write_info)
    monkeypatch.setattr(plugin_module, "remove_stale_preset_files", cleanup)

    errors = _retire_running_job_during_action(
        plugin_module,
        monkeypatch,
        lambda: plugin_module.migrate_managed_filament_display_name(
            str(tmp_path), 7, local_entry, {"name": "Fixture"}
        ),
        entered,
        release,
    )

    assert errors == []
    assert mutations == ["json", "info", "cleanup"]
    assert local_entry["path"] == str(target)


def test_pull_keeps_marker_profile_and_cleanup_in_one_transaction(
    plugin_module, monkeypatch, tmp_path
):
    entered = threading.Event()
    release = threading.Event()
    mutations = []
    target = tmp_path / "Fixture.json"

    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda *_args, **_kwargs: (200, b'{"name":"Fixture"}'),
    )
    monkeypatch.setattr(plugin_module, "validate_filament_profile", lambda value: value)
    monkeypatch.setattr(plugin_module, "ensure_parent_exists", lambda *_args: None)
    monkeypatch.setattr(plugin_module, "ensure_filament_colour", lambda *_args: None)
    monkeypatch.setattr(plugin_module, "filament_display_name", lambda *_args: "Fixture")
    monkeypatch.setattr(plugin_module, "preset_file_path", lambda *_args: str(target))

    def write_info(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("info")
        entered.set()
        assert release.wait(2)

    def write_json(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("json")

    def cleanup(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("cleanup")
        return 0

    monkeypatch.setattr(plugin_module, "write_managed_info", write_info)
    monkeypatch.setattr(plugin_module, "write_json_atomic", write_json)
    monkeypatch.setattr(plugin_module, "remove_stale_preset_files", cleanup)
    catalog = plugin_module.FilamentHubCatalog()

    errors = _retire_running_job_during_action(
        plugin_module,
        monkeypatch,
        lambda: catalog._pull_one(7, "token", set(), str(tmp_path), {}),
        entered,
        release,
    )

    assert errors == []
    assert mutations == ["info", "json", "cleanup"]


def test_fork_keeps_new_identity_and_old_quarantine_in_one_transaction(
    plugin_module, monkeypatch, tmp_path
):
    entered = threading.Event()
    release = threading.Event()
    mutations = []
    source = tmp_path / "Source.json"
    target = tmp_path / "Fork.json"
    profile = {"name": "Source", "bundle_id": "filamenthub:7"}
    local_entry = {
        "path": str(source),
        "profile": profile,
        "hash": "old-hash",
        "version_id": 2,
    }

    monkeypatch.setattr(plugin_module, "restore_remote_parent_for_upload", lambda value, *_args: dict(value))
    monkeypatch.setattr(
        plugin_module,
        "http_post_json",
        lambda *_args, **_kwargs: (
            200,
            b'{"results":[{"fhub_id":8,"version_id":3}]}',
        ),
    )
    monkeypatch.setattr(plugin_module, "preset_file_path", lambda *_args: str(target))

    def write_info(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("info")
        entered.set()
        assert release.wait(2)

    def write_json(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("json")

    def quarantine(*_args, **_kwargs):
        plugin_module.ensure_side_effect_allowed()
        mutations.append("quarantine")
        return True

    monkeypatch.setattr(plugin_module, "write_managed_info", write_info)
    monkeypatch.setattr(plugin_module, "write_json_atomic", write_json)
    monkeypatch.setattr(plugin_module, "_quarantine_managed_preset_artifact", quarantine)
    catalog = plugin_module.FilamentHubCatalog()

    errors = _retire_running_job_during_action(
        plugin_module,
        monkeypatch,
        lambda: catalog._push_one(7, "token", local_entry, {"name": "Source"}),
        entered,
        release,
    )

    assert errors == []
    assert mutations == ["info", "json", "quarantine"]


def test_printer_bundle_removal_keeps_quarantine_and_state_in_one_transaction(
    plugin_module, monkeypatch
):
    entered = threading.Event()
    release = threading.Event()
    mutations = []
    state = {
        "printers": [
            {
                "physical_printer_id": 3,
                "machine_profile_ids": [10],
                "process_profile_ids": [20],
            }
        ]
    }
    artifacts = {
        "machine": [{"profile_id": 10}],
        "process": [{"profile_id": 20}],
    }

    monkeypatch.setattr(plugin_module, "load_printer_bundle_state", lambda: state)
    monkeypatch.setattr(plugin_module, "user_machine_dir", lambda: "machine")
    monkeypatch.setattr(plugin_module, "user_process_dir", lambda: "process")
    monkeypatch.setattr(
        plugin_module,
        "_managed_profile_artifacts",
        lambda _folder, kind: artifacts[kind],
    )

    def quarantine(artifact, *_args):
        plugin_module.ensure_side_effect_allowed()
        mutations.append(("quarantine", artifact["profile_id"]))
        if len(mutations) == 1:
            entered.set()
            assert release.wait(2)
        return True

    def save(_state):
        plugin_module.ensure_side_effect_allowed()
        mutations.append(("state", 0))

    monkeypatch.setattr(plugin_module, "_quarantine_managed_preset_artifact", quarantine)
    monkeypatch.setattr(plugin_module, "save_printer_bundle_state", save)

    errors = _retire_running_job_during_action(
        plugin_module,
        monkeypatch,
        lambda: plugin_module.remove_installed_printer_bundle(3),
        entered,
        release,
    )

    assert errors == []
    assert mutations == [
        ("quarantine", 10),
        ("quarantine", 20),
        ("state", 0),
    ]


def test_side_effect_guard_does_not_block_non_worker_runtime_threads(
    plugin_module, monkeypatch
):
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-stopped-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    worker.stop(wait_timeout=0)
    results = []

    def independent_runtime():
        plugin_module.ensure_side_effect_allowed()
        results.append("allowed")

    thread = threading.Thread(target=independent_runtime)
    thread.start()
    thread.join(2)

    assert results == ["allowed"]


def test_blocked_host_callback_does_not_block_worker_stop(
    plugin_module, monkeypatch
):
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-blocked-host-callback-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    callback_started = threading.Event()
    callback_release = threading.Event()
    callback_finished = threading.Event()
    stop_finished = threading.Event()
    late_callbacks = []
    late_errors = []

    def message(*_args, **_kwargs):
        callback_started.set()
        assert callback_release.wait(2)

    monkeypatch.setattr(
        plugin_module.orca.host.ui,
        "message",
        message,
        raising=False,
    )

    def job():
        try:
            plugin_module.show_host_message("fixture")
            try:
                worker.run_if_current(lambda: late_callbacks.append(True))
            except Exception as exc:  # noqa: BLE001 - assert exact lifecycle error below
                late_errors.append(exc)
        finally:
            callback_finished.set()

    assert worker.submit(job)
    assert callback_started.wait(2)
    stopper = threading.Thread(
        target=lambda: (worker.stop(wait_timeout=0), stop_finished.set())
    )
    stopper.start()

    assert stop_finished.wait(0.5)
    callback_release.set()
    assert callback_finished.wait(2)
    stopper.join(2)
    assert late_callbacks == []
    assert len(late_errors) == 1
    assert isinstance(late_errors[0], plugin_module.PluginLifecycleStopped)
    worker.stop()


def test_retired_unauthorized_response_cannot_clear_new_lifecycle_auth(
    plugin_module, tmp_path, monkeypatch
):
    auth_path = tmp_path / ".auth.json"
    monkeypatch.setattr(plugin_module, "AUTH_FILE", str(auth_path))
    assert plugin_module.save_auth("old-token")
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-stale-auth-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    request_started = threading.Event()
    request_release = threading.Event()
    finished = threading.Event()

    def urlopen(request, **_kwargs):
        request_started.set()
        assert request_release.wait(2)
        raise plugin_module.urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b"{}"),
        )

    monkeypatch.setattr(plugin_module.urllib.request, "urlopen", urlopen)

    def stale_sync_fragment():
        try:
            status, _body = plugin_module.http_get(
                "/auth/my-presets", token="old-token"
            )
            if status == 401:
                plugin_module.clear_auth()
        finally:
            finished.set()

    assert worker.submit(stale_sync_fragment)
    assert request_started.wait(2)
    worker.stop(wait_timeout=0)
    worker.activate()
    assert plugin_module.save_auth("new-token")
    request_release.set()

    assert finished.wait(2)
    assert plugin_module.load_saved_auth() == {
        "accessToken": "new-token",
        "refreshToken": "",
    }
    worker.stop()


def test_retired_worker_generation_cannot_start_managed_preset_cleanup(
    plugin_module, tmp_path, monkeypatch
):
    live = tmp_path / "filamenthub"
    live.mkdir()
    stale_json = live / "Old Name.json"
    stale_info = live / "Old Name.info"
    stale_json.write_text(
        json.dumps({"bundle_id": "filamenthub:10", "name": "Old Name"}),
        encoding="utf-8",
    )
    stale_info.write_text(
        "sync_info = filamenthub:preset:10\n", encoding="utf-8"
    )

    _retire_running_job_before_side_effect(
        plugin_module,
        monkeypatch,
        lambda: plugin_module.remove_stale_preset_files(
            str(live), 10, str(live / "Current Name.json")
        ),
    )

    assert stale_json.is_file()
    assert stale_info.is_file()


def test_bambu_connect_does_not_continue_to_tls_after_worker_unload(
    plugin_module, monkeypatch
):
    worker = plugin_module.ReusableDaemonWorker(
        "filamenthub-bambu-connect-worker", idle_timeout=0.2
    )
    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", worker)
    connect_started = threading.Event()
    connect_release = threading.Event()
    finished = threading.Event()
    tls_started = []

    class RawSocket:
        closed = False

        def settimeout(self, _timeout):
            return None

        def connect(self, _sockaddr):
            connect_started.set()
            assert connect_release.wait(2)

        def close(self):
            self.closed = True

    raw = RawSocket()
    monkeypatch.setattr(
        plugin_module,
        "_resolved_bambu_address",
        lambda _host: (2, 1, 6, ("192.168.1.42", 8883)),
    )
    monkeypatch.setattr(plugin_module.socket, "socket", lambda *_args: raw)
    monkeypatch.setattr(
        plugin_module.ssl,
        "SSLContext",
        lambda *_args: tls_started.append(True),
    )

    def stale_connect():
        try:
            plugin_module._open_bambu_mqtt("printer.local", "secret", 1)
        finally:
            finished.set()

    assert worker.submit(stale_connect)
    assert connect_started.wait(2)
    worker.stop(wait_timeout=0)
    worker.activate()
    connect_release.set()

    assert finished.wait(2)
    assert tls_started == []
    assert raw.closed is True
    worker.stop()


def test_shell_server_stops_without_starting_a_shutdown_worker(plugin_module):
    server = plugin_module.ShellServer()
    url = server.url_for("<!doctype html><title>fixture</title>")
    stop_event = server._server_stop
    worker = server._server_thread

    assert url.startswith("http://127.0.0.1:")
    assert stop_event is not None
    assert worker is not None and worker.is_alive()
    with urllib.request.urlopen(url, timeout=2) as response:
        policy = response.headers["Content-Security-Policy"]
        assert "frame-src %s" % plugin_module.SITE_ORIGIN in policy
        assert "connect-src 'self'" in policy
        assert "default-src 'none'" in policy
        assert "frame-src *" not in policy
    server.stop(wait_timeout=2)
    assert stop_event.is_set()
    assert not worker.is_alive()
    assert server._server is None
    assert server._server_thread is None


def test_shell_sandboxes_the_catalog_without_popup_or_top_navigation(plugin_module):
    iframe = plugin_module.PAGE.split('<iframe id="fh"', 1)[1].split(">", 1)[0]

    assert 'sandbox="allow-scripts allow-same-origin allow-forms allow-downloads"' in iframe
    assert "allow-popups" not in iframe
    assert "allow-top-navigation" not in iframe
    assert "SITE_ORIGIN = '%s'" % plugin_module.SITE_ORIGIN in plugin_module.PAGE


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
    assert server._server_thread is None


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
    ("host_language", "expected", "site_language", "catalog_label"),
    [
        ("ru_RU", "ru", "ru", "Каталог"),
        ("zh_CN", "zh_CN", "zh", "目录"),
        ("zh-TW", "zh_TW", "zh", "目錄"),
        ("en_US", "en", "en", "Catalog"),
        ("de_DE", "de", "en", "Katalog"),
    ],
)
def test_shell_uses_orca_ui_language(
    plugin_module, monkeypatch, host_language, expected, site_language, catalog_label
):
    monkeypatch.setattr(
        plugin_module.orca.host,
        "app_language",
        lambda: host_language,
        raising=False,
    )

    rendered = plugin_module.render_page()

    assert f"var hostLanguage = '{expected}';" in rendered
    assert f"?lng={site_language}" in rendered
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
    plugin_module.refresh_ui_language()
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_sync_result",
        lambda text, **kwargs: messages.append((text, kwargs)),
    )

    catalog._do_sync("", set(), announce=True)

    assert messages == [(
        "Войдите в FilamentHub в окне плагина и повторите синхронизацию.",
        {"operation_id": "", "scope": "all", "status": "error"},
    )]


def test_catalog_sync_collects_every_profile_contour_in_dependency_order(
    plugin_module, monkeypatch
):
    jobs = []

    class CapturingWorker:
        def submit(self, function, *args):
            jobs.append((function, args))

    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", CapturingWorker())
    monkeypatch.setattr(plugin_module, "load_saved_auth", lambda: {"accessToken": "token"})
    monkeypatch.setattr(plugin_module, "refresh_user_preset_folder", lambda: None)
    monkeypatch.setattr(plugin_module, "scan_active_user_filaments", lambda: ["filament"])
    monkeypatch.setattr(plugin_module, "observe_printer_presets", lambda: ["observation"])
    monkeypatch.setattr(
        plugin_module,
        "observe_local_moonraker_connections",
        lambda observations: ["moonraker"],
    )
    monkeypatch.setattr(plugin_module, "plugin_source_instance_id", lambda: "source")
    monkeypatch.setattr(plugin_module, "loaded_managed_preset_ids", lambda: {10})
    scans = []
    monkeypatch.setattr(
        plugin_module,
        "scan_user_profiles_checked",
        lambda kind: (scans.append(kind) or ([kind], True)),
    )
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_known_filament_preset_names", lambda: {"Known"})

    catalog.on_message({
        "source": "filamenthub-plugin",
        "type": "sync",
        "scope": "all",
        "operationId": "sync-1",
    })

    assert len(jobs) == 1
    function, args = jobs[0]
    assert function == catalog._do_sync
    assert scans == ["machine", "process"]
    assert args == (
        "token",
        {"Known"},
        True,
        ["filament"],
        {
            "machine": {"items": ["machine"], "complete": True},
            "process": {"items": ["process"], "complete": True},
        },
        ["observation"],
        "source",
        ["moonraker"],
        {10},
        "all",
        "sync-1",
        "manual",
    )


def test_disabled_filament_directions_never_remove_managed_files(
    plugin_module, monkeypatch, tmp_path
):
    live = tmp_path / "filament"
    live.mkdir()
    managed = live / "Keep.json"
    managed.write_text(
        json.dumps({"name": "Keep", "bundle_id": "filamenthub:10"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(plugin_module, "user_filament_dir", lambda: str(live))
    monkeypatch.setattr(plugin_module, "load_sync_state", lambda: {})
    monkeypatch.setattr(plugin_module, "save_sync_state", lambda _state: None)
    monkeypatch.setattr(
        plugin_module,
        "_sync_preferences",
        lambda _token: {
            "available": True,
            "auto_import_local_presets": True,
            "sync_printer_endpoints": False,
            "allow_filament_presets_import": False,
            "allow_filament_presets_export": False,
            "allow_printer_profiles_import": False,
            "allow_printer_profiles_export": False,
            "allow_print_profiles_import": False,
            "allow_print_profiles_export": False,
        },
    )
    monkeypatch.setattr(
        plugin_module,
        "http_get",
        lambda *_args, **_kwargs: pytest.fail("disabled sync must not read desired state"),
    )
    monkeypatch.setattr(
        plugin_module,
        "quarantine_unwanted_managed_preset_files",
        lambda *_args, **_kwargs: pytest.fail("disabled sync must not quarantine files"),
    )
    monkeypatch.setattr(
        plugin_module,
        "push_filament_drafts",
        lambda *_args, **_kwargs: pytest.fail("disabled sync must not upload drafts"),
    )
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_sync_result",
        lambda text, draft_count=0, **kwargs: delivered.append(
            (text, draft_count, kwargs)
        ),
    )

    catalog._do_sync(
        "token",
        set(),
        announce=True,
        active_filaments=[{"name": "Unmanaged"}],
        scope="filament",
        operation_id="sync-disabled",
    )

    assert managed.exists()
    assert delivered[0][2]["status"] == "warning"
    assert delivered[0][2]["contours"] == [{
        "kind": "filament",
        "status": "warning",
        "summary": plugin_module.ui_text("summaryDisabled"),
    }]


def test_incomplete_host_scan_is_uploaded_non_authoritatively(
    plugin_module, monkeypatch
):
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
            "allow_filament_presets_export": False,
            "allow_printer_profiles_import": True,
            "allow_printer_profiles_export": True,
            "allow_print_profiles_import": False,
            "allow_print_profiles_export": False,
        },
    )
    calls = []
    monkeypatch.setattr(
        plugin_module,
        "push_user_profiles",
        lambda kind, token, items, state, authoritative=True: (
            calls.append((kind, items, authoritative)) or (len(items), 0)
        ),
    )
    monkeypatch.setattr(
        plugin_module,
        "send_printer_observations",
        lambda *_args, **_kwargs: (None, {}),
    )
    monkeypatch.setattr(plugin_module, "sync_happy_hare_topologies", lambda *_args: None)
    delivered = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(
        catalog,
        "_deliver_sync_result",
        lambda text, draft_count=0, **kwargs: delivered.append(kwargs),
    )

    catalog._do_sync(
        "token",
        set(),
        announce=True,
        host_profiles={
            "machine": {"items": [{"name": "Recovered"}], "complete": False},
        },
        scope="machine",
        operation_id="sync-partial",
    )

    assert calls == [("machine", [{"name": "Recovered"}], False)]
    assert delivered[0]["status"] == "error"
    assert plugin_module.ui_text("summaryScanIncomplete") in delivered[0]["contours"][0][
        "summary"
    ]


def test_unresolved_parent_makes_original_profile_snapshot_incomplete(
    plugin_module, monkeypatch
):
    preset = SimpleNamespace(name="Existing machine", bundle_id="", file="")
    preset.is_user = lambda: True
    collection = SimpleNamespace(size=lambda: 1, preset=lambda _index: preset)
    monkeypatch.setattr(
        plugin_module.orca.host,
        "preset_bundle",
        lambda: SimpleNamespace(printers=collection),
        raising=False,
    )
    monkeypatch.setattr(
        plugin_module,
        "analyze_user_profile",
        lambda *_args: {
            "parent_resolved": False,
            "has_technical_changes": True,
        },
    )

    items, complete = plugin_module.scan_user_profiles_checked("machine")

    assert items == []
    assert complete is False


def test_every_orca_locale_is_preserved_and_missing_catalogs_fall_back_per_key(
    plugin_module, tmp_path, monkeypatch
):
    for locale in plugin_module.ORCA_UI_LOCALES:
        assert plugin_module.normalize_ui_language(locale) == locale
        monkeypatch.setattr(
            plugin_module.orca.host,
            "app_language",
            lambda current=locale: current,
            raising=False,
        )
        rendered = plugin_module.render_page()
        site_language = (
            "ru" if locale == "ru"
            else "zh" if locale in {"zh_CN", "zh_TW"}
            else "en"
        )
        assert f"var hostLanguage = '{locale}';" in rendered
        assert f"?lng={site_language}" in rendered
        assert json.dumps(
            plugin_module.resolved_ui_catalog(locale)["catalog"],
            ensure_ascii=False,
        ) in rendered

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


@pytest.mark.parametrize(
    ("host_language", "site_language"),
    [
        ("ru", "ru"),
        ("ru_RU", "ru"),
        ("zh", "zh"),
        ("zh_CN", "zh"),
        ("zh-TW", "zh"),
        ("en", "en"),
        ("de", "en"),
        ("ja_JP", "en"),
        ("unsupported", "en"),
    ],
)
def test_embedded_site_is_limited_to_supported_languages(
    plugin_module, host_language, site_language
):
    assert plugin_module.localized_embed_url(host_language).endswith(
        f"?lng={site_language}"
    )


def test_invalid_optional_catalog_cannot_break_plugin_startup(plugin_module, tmp_path):
    (tmp_path / "en.json").write_text('{"ready":"Ready"}', encoding="utf-8")
    (tmp_path / "ru.json").write_text("not-json", encoding="utf-8")
    (tmp_path / "xx.json").write_text('{"ready":"Unknown"}', encoding="utf-8")

    assert plugin_module.load_ui_catalogs(str(tmp_path)) == {"en": {"ready": "Ready"}}


def test_bundled_locale_catalogs_are_valid():
    validator = _load_module(LOCALE_VALIDATOR_PATH, "filamenthub_locale_validator_test")
    assert validator.validate_catalogs() == []
    assert {
        path.stem for path in (PLUGIN_ROOT / "filamenthub_locales").glob("*.json")
    } == validator.ORCA_UI_LOCALES


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


def test_filament_display_name_is_type_brand_name_without_double_prefix(plugin_module):
    profile = {
        "name": "Smooth satin",
        "filament_type": ["PLA"],
        "filament_vendor": ["OlgaCraft"],
    }

    assert plugin_module.filament_display_name(profile) == "PLA • OlgaCraft • Smooth satin"
    assert (
        plugin_module.filament_display_name(profile, "PLA • OlgaCraft • Smooth satin")
        == "PLA • OlgaCraft • Smooth satin"
    )
    assert (
        plugin_module.filament_display_name(profile, "PLA • Smooth satin")
        == "PLA • OlgaCraft • Smooth satin"
    )
    assert plugin_module.filament_source_name(
        profile, "PLA • OlgaCraft • Smooth satin"
    ) == "Smooth satin"
    assert plugin_module.filament_source_name(
        profile, "PLA • Smooth satin"
    ) == "Smooth satin"


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


def test_build_packages_locale_catalogs_and_checksums(plugin_module, tmp_path):
    builder = _load_module(BUILD_PATH, "filamenthub_build_package_test")
    package_dir = builder.build(tmp_path)
    package = package_dir / "filamenthub_plugin.py"
    metadata = json.loads((package_dir / "package-metadata.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    assert metadata["version"] == plugin_module.PLUGIN_VERSION
    assert metadata["network"] == ["filamenthub.ru", "*.filamenthub.ru"]
    assert metadata["sha256"] == digest
    expected_locales = sorted(plugin_module.ORCA_UI_LOCALES)
    assert metadata["locales"] == expected_locales
    locale_dir = package_dir / "filamenthub_locales"
    assert {path.name for path in locale_dir.glob("*.json")} == {
        f"{locale}.json" for locale in expected_locales
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
        metadata_path = (
            f"filamenthub-{plugin_module.PLUGIN_VERSION}.dist-info/METADATA"
        )
        metadata_bytes = archive.read(metadata_path)
        record_rows = list(csv.reader(io.StringIO(
            archive.read(
                f"filamenthub-{plugin_module.PLUGIN_VERSION}.dist-info/RECORD"
            ).decode("utf-8"),
            newline="",
        )))
        top_level = archive.read(
            f"filamenthub-{plugin_module.PLUGIN_VERSION}.dist-info/top_level.txt"
        )
    assert b"\r" not in wheel_source
    assert b"_EMBEDDED_UI_COPY = {}" not in wheel_source
    assert b'os.environ.get("FILAMENTHUB_SITE_URL", "https://filamenthub.ru")' in wheel_source
    assert b"http://localhost:3000" not in wheel_source
    assert b"filamenthub.club" not in wheel_source
    assert b"\r" not in metadata_bytes
    metadata_row = next(row for row in record_rows if row[0] == metadata_path)
    expected_metadata_digest = base64.urlsafe_b64encode(
        hashlib.sha256(metadata_bytes).digest()
    ).rstrip(b"=").decode("ascii")
    assert metadata_row[1] == f"sha256={expected_metadata_digest}"
    assert metadata_row[2] == str(len(metadata_bytes))
    assert top_level == b"filamenthub_plugin\n"
    assert not any(name.startswith("filamenthub_locales/") for name in names)

    standalone = tmp_path / "standalone_filamenthub_plugin.py"
    standalone.write_bytes(package.read_bytes())
    standalone_module = _load_module(standalone, "filamenthub_standalone_smoke")
    assert set(standalone_module.UI_COPY) == set(expected_locales)
    assert standalone_module.UI_COPY["ru"]["catalog"] == "Каталог"
    assert standalone_module.UI_COPY["de"]["catalog"] == "Katalog"


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


def _module_with_pages(native_lifecycle=False):
    """The plugin as it loads on the PR #14992 Pages artifact."""
    class PagesCapabilityBase:
        def __init__(self):
            self.posted_messages = []

        def post_message(self, message):
            self.posted_messages.append(message)

    if native_lifecycle:
        PagesCapabilityBase.on_load = lambda self: None
        PagesCapabilityBase.on_unload = lambda self: None

    fake_orca = ModuleType("orca")
    fake_orca.base = object
    fake_orca.plugin = lambda cls: cls
    registered: list = []
    fake_orca.register_capability = registered.append
    fake_orca.script = SimpleNamespace(ScriptPluginCapabilityBase=object)
    fake_orca.pages = SimpleNamespace(PagesPluginCapabilityBase=PagesCapabilityBase)
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


def test_current_host_defers_runtime_resources_to_capability_lifecycle(monkeypatch):
    module, _ = _module_with_pages(native_lifecycle=True)
    lifecycle = []
    stopped = []
    monkeypatch.setattr(
        module,
        "configure_plugin_storage",
        lambda: lifecycle.append("storage") or True,
    )
    monkeypatch.setattr(
        module,
        "start_plugin_runtime",
        lambda storage_initialized=False: lifecycle.append(
            ("start", storage_initialized)
        ),
    )
    monkeypatch.setattr(module, "stop_plugin_runtime", lambda: stopped.append(True))

    module.FilamentHubPlugin().register_capabilities()
    assert lifecycle == []

    page = module.FilamentHubPage()
    page.on_load()
    page.on_cancelled()
    page.on_unload()

    assert lifecycle == ["storage", ("start", True)]
    assert stopped == [True, True]


def test_old_host_keeps_registration_time_runtime_fallback(monkeypatch):
    module, _ = _module_with_pages(native_lifecycle=False)
    started = []
    monkeypatch.setattr(module, "start_plugin_runtime", lambda: started.append(True))

    module.FilamentHubPlugin().register_capabilities()

    assert started == [True]


def test_runtime_stop_closes_every_owned_resource(plugin_module, monkeypatch):
    stopped = []
    monkeypatch.setattr(
        plugin_module,
        "BACKGROUND_WORKER",
        SimpleNamespace(stop=lambda: stopped.append("worker")),
    )
    monkeypatch.setattr(
        plugin_module,
        "BAMBU_BRIDGE_RUNTIME",
        SimpleNamespace(stop=lambda: stopped.append("bambu")),
    )
    monkeypatch.setattr(
        plugin_module,
        "BAMBU_REVOKE_SCHEDULER",
        SimpleNamespace(stop=lambda: stopped.append("revoke-scheduler")),
    )
    monkeypatch.setattr(
        plugin_module,
        "SHELL_SERVER",
        SimpleNamespace(stop=lambda: stopped.append("loopback")),
    )
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_ACTIVE", True)
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_EPOCH", 1)

    assert plugin_module.stop_plugin_runtime() is True
    assert stopped == ["revoke-scheduler", "worker", "bambu", "loopback"]
    assert plugin_module._PLUGIN_RUNTIME_ACTIVE is False


def test_runtime_load_starts_pending_bambu_revoke_scheduler(
    plugin_module, monkeypatch
):
    calls = []

    class Worker:
        def activate(self):
            calls.append("activate")

        def stop(self):
            calls.append("stop")

    monkeypatch.setattr(plugin_module, "BACKGROUND_WORKER", Worker())
    monkeypatch.setattr(
        plugin_module,
        "BAMBU_BRIDGE_RUNTIME",
        SimpleNamespace(start=lambda: calls.append("bambu-start"), stop=lambda: None),
    )
    monkeypatch.setattr(
        plugin_module,
        "BAMBU_REVOKE_SCHEDULER",
        SimpleNamespace(
            start=lambda: calls.append("revoke-start"),
            stop=lambda: calls.append("revoke-stop"),
        ),
    )
    monkeypatch.setattr(plugin_module, "SHELL_SERVER", SimpleNamespace(stop=lambda: None))
    monkeypatch.setattr(plugin_module, "refresh_ui_language", lambda: None)
    monkeypatch.setattr(
        plugin_module,
        "load_bambu_config",
        lambda: {"source_instance_id": "fixture", "printers": []},
    )
    monkeypatch.setattr(plugin_module, "repair_local_bundle_parents", lambda: 0)
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_ACTIVE", False)
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_EPOCH", 0)

    assert plugin_module.start_plugin_runtime(storage_initialized=True) is True
    assert calls[:2] == ["activate", "revoke-start"]
    assert plugin_module.stop_plugin_runtime() is True


def test_pages_host_delivers_plugin_messages_through_post_message():
    module, _ = _module_with_pages()
    page = module.FilamentHubPage()

    page._catalog._deliver_sync_result("Synced", 2)

    assert page.posted_messages == [{
        "source": "filamenthub-host",
        "type": "sync-result",
        "text": "Synced",
        "draftCount": 2,
        "operationId": "",
        "scope": "all",
        "status": "success",
        "contours": [],
    }]


def test_notice_uses_typed_loopback_fallback_without_a_push_transport(
    plugin_module, monkeypatch
):
    captured = []
    monkeypatch.setattr(
        plugin_module.SHELL_SERVER,
        "set_sync_result",
        lambda payload: captured.append(payload),
    )

    plugin_module.FilamentHubCatalog()._deliver_notice("Saved", "success")

    assert captured == [{
        "text": "Saved",
        "status": "success",
        "resultType": "plugin-notice",
    }]


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
    (legacy / ".fh_bambu_revoke.json").write_text(
        '{"version":1,"pending":[]}', encoding="utf-8"
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
        plugin_module,
        "BAMBU_REVOKE_FILE",
        str(legacy / ".fh_bambu_revoke.json"),
    )
    monkeypatch.setattr(
        plugin_module,
        "PRINTER_BUNDLE_STATE_FILE",
        str(legacy / ".fh_printer_bundles.json"),
    )
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

    plugin_module.stop_plugin_runtime()
    plugin_module.FilamentHubPlugin().register_capabilities()

    assert plugin_module.PLUGIN_STORAGE_DIR == str(storage)
    assert plugin_module.AUTH_FILE == str(storage / ".auth.json")
    assert plugin_module.BAMBU_CONFIG_FILE == str(storage / ".fh_bambu.json")
    assert plugin_module.BAMBU_REVOKE_FILE == str(
        storage / ".fh_bambu_revoke.json"
    )
    assert plugin_module.PRINTER_BUNDLE_STATE_FILE == str(
        storage / ".fh_printer_bundles.json"
    )
    assert plugin_module.SYNC_STATE_FILE == str(storage / ".fh_sync.json")
    assert plugin_module._SLICE_CACHE_DIR == str(storage / "slices")
    assert (storage / ".auth.json").read_text(encoding="utf-8") == (
        '{"accessToken":"fixture"}'
    )
    assert (storage / ".fh_bambu.json").exists()
    assert (storage / ".fh_bambu_revoke.json").exists()
    assert (storage / "slices" / "fixture.gcode").read_text(encoding="utf-8") == "G28"
    assert (legacy / ".auth.json").exists()
    assert (legacy / ".fh_bambu_revoke.json").exists()
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
        plugin_module,
        "BAMBU_REVOKE_FILE",
        str(legacy / ".fh_bambu_revoke.json"),
    )
    monkeypatch.setattr(
        plugin_module,
        "PRINTER_BUNDLE_STATE_FILE",
        str(legacy / ".fh_printer_bundles.json"),
    )
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
    assert plugin_module.BAMBU_REVOKE_FILE == str(
        stable / ".fh_bambu_revoke.json"
    )
    assert plugin_module.PRINTER_BUNDLE_STATE_FILE == str(
        stable / ".fh_printer_bundles.json"
    )
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


def _active_revoke_scheduler(plugin_module, monkeypatch, tmp_path):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    scheduler = plugin_module.BambuRevokeScheduler()
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_SCHEDULER", scheduler)
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_ACTIVE", True)
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_EPOCH", 1)
    return scheduler


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
