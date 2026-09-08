"""Background worker and lifecycle contracts."""

from .filamenthub_plugin_test_support import (
    io,
    json,
    PLUGIN_PATH,
    _retire_running_job_before_side_effect,
    _retire_running_job_during_action,
    SimpleNamespace,
    threading,
    urllib,
)


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
