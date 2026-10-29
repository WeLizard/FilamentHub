"""OrcaSlicer asks before a plugin creates a thread; a refusal must degrade, not crash."""

from .filamenthub_plugin_test_support import (
    _module_with_pages,
    json,
    pytest,
    SimpleNamespace,
    ThreadAudit,
    threading,
    time,
)


class DenyingWorker:
    """BACKGROUND_WORKER whose thread the host refused."""

    def __init__(self):
        self.denial_count = 0
        self.jobs = []

    def submit(self, function, *args, **kwargs):
        self.denial_count += 1
        return False

    def run_if_current(self, function, *args, **kwargs):
        return function(*args, **kwargs)


def _audited_module(monkeypatch):
    module, registered = _module_with_pages(native_lifecycle=True, lifecycle_events=True)
    module.FilamentHubPlugin().register_capabilities()
    monkeypatch.setattr(module, "fh_log", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "_THREAD_GRANT_SEEN", False)
    return module, [cls() for cls in registered]


def _page_and_action(module, instances):
    page = next(i for i in instances if isinstance(i, module.FilamentHubPage))
    action = next(i for i in instances if isinstance(i, module.FilamentHubSyncAction))
    return page, action


@pytest.fixture
def denied(monkeypatch):
    """A page, its catalog and the Speed Dial action with the host answering "No"."""
    module, instances = _audited_module(monkeypatch)
    page, action = _page_and_action(module, instances)
    worker = DenyingWorker()
    monkeypatch.setattr(module, "BACKGROUND_WORKER", worker)
    monkeypatch.setattr(module, "load_saved_auth", lambda: {"accessToken": "token"})
    monkeypatch.setattr(module, "_PLUGIN_SETTINGS", dict(module.PLUGIN_SETTINGS_DEFAULTS))
    monkeypatch.setattr(module, "prime_background_runtime", lambda explicit=False: False)
    catalog = page._catalog
    monkeypatch.setattr(
        module.FilamentHubCatalog, "_prepare_sync",
        lambda self, token, scope, announce, operation_id, trigger: (
            token, set(), announce, [], {}, [], "", [], None, scope, operation_id, trigger,
        ),
    )
    delivered = []
    monkeypatch.setattr(
        catalog, "_deliver", lambda kind, **data: delivered.append((kind, data))
    )
    module._set_slice_delivery_target(catalog)
    return SimpleNamespace(
        module=module, page=page, action=action, catalog=catalog,
        worker=worker, delivered=delivered, monkeypatch=monkeypatch,
    )


def test_refused_worker_thread_leaves_no_job_behind_and_logs_once(monkeypatch):
    module = _module_with_pages(lifecycle_events=True)[0]
    logged = []
    monkeypatch.setattr(module, "fh_log", logged.append)
    audit = ThreadAudit(monkeypatch, allowed=False)
    worker = module.ReusableDaemonWorker("filamenthub-test-worker", idle_timeout=0.2)
    ran = []

    assert worker.submit(lambda: ran.append("refused")) is False
    assert worker.submit(lambda: ran.append("refused again")) is False

    assert worker._jobs.empty()
    assert worker.denial_count == 2
    assert len([line for line in logged if "did not allow" in line]) == 1
    assert len(audit.denied) == 2

    audit.allowed = True
    done = threading.Event()
    assert worker.submit(lambda: (ran.append("accepted"), done.set()))
    assert done.wait(2)
    worker.stop()
    # The refused jobs never run later, once the user has said "Yes".
    assert ran == ["accepted"]


def test_allowed_worker_thread_behaves_as_before(monkeypatch):
    module = _module_with_pages(lifecycle_events=True)[0]
    ThreadAudit(monkeypatch, allowed=True)
    worker = module.ReusableDaemonWorker("filamenthub-test-worker", idle_timeout=0.2)
    done = threading.Event()

    assert worker.submit(done.set) is True
    assert done.wait(2)
    assert worker.denial_count == 0
    worker.stop()


def test_page_sync_refused_thread_answers_the_waiting_operation(denied):
    started = denied.catalog._start_sync(
        scope="filament", announce=True, operation_id="op-1", trigger="manual"
    )

    assert started is False
    (kind, data), = denied.delivered
    assert kind == "sync-result"
    assert data["operationId"] == "op-1"
    assert data["status"] == "warning"
    assert data["text"] == denied.module.ui_text("backgroundDenied")


def test_page_message_refused_thread_posts_a_notice_per_failed_action(denied):
    session = "bridge-session"
    denied.catalog._direct_bridge_session = session
    message = {
        "source": "filamenthub-plugin", "type": "recover", "bridgeSession": session,
    }

    denied.catalog.on_message(message)
    denied.catalog.on_message(message)

    notices = [d for d in denied.delivered if d[0] == "plugin-notice"]
    assert [d[1]["text"] for d in notices] == [
        denied.module.ui_text("backgroundDenied")
    ] * 2
    assert all(d[1]["status"] == "warning" for d in notices)


def test_sync_message_is_reported_once_not_twice(denied):
    session = "bridge-session"
    denied.catalog._direct_bridge_session = session
    denied.catalog.on_message({
        "source": "filamenthub-plugin", "type": "sync", "scope": "filament",
        "operationId": "op-9", "bridgeSession": session,
    })

    assert [d[0] for d in denied.delivered] == ["sync-result"]


def test_speed_dial_refused_thread_returns_the_explanation(denied):
    result = denied.action.execute()

    assert result == ("skipped", denied.module.ui_text("backgroundDenied"))


def test_preset_saved_refused_thread_warns_natively_once_per_session(denied):
    module = denied.module
    pushed = []
    denied.monkeypatch.setattr(
        module, "push_native_notification",
        lambda level, text: pushed.append((level, text)) or True,
    )
    denied.monkeypatch.setattr(module, "_BACKGROUND_DENIED_PUSHED", False)
    denied.monkeypatch.setattr(
        denied.catalog, "_saved_preset_scope", lambda _name: "filament"
    )

    for _ in range(3):
        denied.catalog._on_preset_saved(SimpleNamespace(name="Fil"))

    assert pushed == [
        ("WarningNotificationLevel", module.ui_text("backgroundDenied"))
    ]


def test_first_worker_thread_comes_from_opening_the_page_not_from_load(monkeypatch):
    module, instances = _audited_module(monkeypatch)
    page, _action = _page_and_action(module, instances)
    audit = ThreadAudit(monkeypatch, allowed=True)
    bridge_started = []
    monkeypatch.setattr(module, "repair_local_bundle_parents", lambda: 0)
    monkeypatch.setattr(
        module, "load_bambu_config",
        lambda: {"printers": [{"bridge_token": "t"}]},
    )
    monkeypatch.setattr(
        module, "_next_pending_bambu_revoke_at", lambda: time.time() + 3600
    )
    monkeypatch.setattr(
        module.BAMBU_BRIDGE_RUNTIME, "_run",
        lambda generation=None: bridge_started.append(generation), raising=False,
    )
    monkeypatch.setattr(
        module.STOCK_ALERT_RUNTIME, "_run",
        lambda generation=None: None, raising=False,
    )
    monkeypatch.setattr(module, "BACKGROUND_WORKER", module.ReusableDaemonWorker(
        "filamenthub-test-worker", idle_timeout=0.5,
    ))
    monkeypatch.setattr(module, "_PLUGIN_RUNTIME_ACTIVE", False)
    try:
        module.start_plugin_runtime(storage_initialized=True)
        # Plugin load runs wherever the host's loader does: no thread yet.
        assert audit.started == [] and audit.denied == []
        assert module._DEFERRED_BACKGROUND == {
            "bambu revoke retry", "Bambu bridge", "stock alerts",
        }

        page.get_ui()

        names = [name for name, _on_ui in audit.started]
        assert names[0] == "filamenthub-test-worker"
        assert audit.started[0][1] is True
        assert "filamenthub-bambu-revoke" in names
        assert "filamenthub-bambu-bridge" in names
        assert "filamenthub-stock-alerts" in names
        assert module._DEFERRED_BACKGROUND == set()
    finally:
        module.stop_plugin_runtime()
        module.BAMBU_REVOKE_SCHEDULER.stop()
        module.BACKGROUND_WORKER.stop()


def test_declined_prompt_returns_only_when_the_tab_is_opened_again(monkeypatch):
    module, instances = _audited_module(monkeypatch)
    page, _action = _page_and_action(module, instances)
    audit = ThreadAudit(monkeypatch, allowed=False)
    monkeypatch.setattr(module, "BACKGROUND_WORKER", module.ReusableDaemonWorker(
        "filamenthub-test-worker", idle_timeout=0.2,
    ))

    page.get_ui()
    page._catalog.on_message({"source": "other"})
    page._catalog.on_message({"source": "other"})

    assert len(audit.denied) == 1
    page.get_ui()
    assert len(audit.denied) == 2
    assert module.background_threads_permitted() is False


def test_background_features_wait_without_a_grant_and_do_not_ask(monkeypatch):
    module, _instances = _audited_module(monkeypatch)
    audit = ThreadAudit(monkeypatch, allowed=False)
    worker = SimpleNamespace(submit=lambda *a, **k: pytest.fail("no thread without a grant"))
    monkeypatch.setattr(module, "BACKGROUND_WORKER", worker)
    monkeypatch.setattr(module, "_slice_delivery_target", lambda: object())
    runtime = module.BambuBridgeRuntime()

    assert module._push_pending_slice_reports() is False
    runtime.start()

    assert runtime._thread is None
    assert audit.denied == []


def test_revoke_timer_survives_a_refused_thread(monkeypatch):
    module, _instances = _audited_module(monkeypatch)
    audit = ThreadAudit(monkeypatch, allowed=False)
    monkeypatch.setattr(module, "_THREAD_GRANT_SEEN", True)
    monkeypatch.setattr(module, "_next_pending_bambu_revoke_at", lambda: time.time() + 60)
    scheduler = module.BambuRevokeScheduler()

    assert scheduler.start() is True

    assert scheduler._timer is None
    assert audit.denied == ["filamenthub-bambu-revoke"]


def test_bridge_thread_survives_a_refused_thread(monkeypatch):
    module, _instances = _audited_module(monkeypatch)
    audit = ThreadAudit(monkeypatch, allowed=False)
    monkeypatch.setattr(module, "_THREAD_GRANT_SEEN", True)
    runtime = module.BambuBridgeRuntime()

    runtime.start()

    assert runtime._thread is None
    assert audit.denied == ["filamenthub-bambu-bridge"]


def test_bambu_stream_thread_refusal_is_a_timeout_not_a_crash(monkeypatch):
    module, _instances = _audited_module(monkeypatch)
    audit = ThreadAudit(monkeypatch, allowed=False)
    runtime = module.BambuBridgeRuntime()
    config = {
        "host": "192.0.2.5", "serial": "S", "access_code": "12345678",
        "bridge_token": "t", "physical_printer_id": 1, "material_system_id": 2,
    }

    with pytest.raises(TimeoutError):
        runtime._stream_observation(config)

    assert runtime._streams == {}
    assert audit.denied == ["filamenthub-bambu-lan"]


def test_slice_parse_thread_refusal_reports_an_error_and_frees_the_lock(monkeypatch):
    module, _instances = _audited_module(monkeypatch)
    ThreadAudit(monkeypatch, allowed=False)
    monkeypatch.setattr(
        module, "slice_entry_for_key", lambda _key: {"path": "slice.gcode", "name": "slice"}
    )
    monkeypatch.setattr(
        module.BACKGROUND_WORKER, "current_job_generation", lambda: None
    )
    catalog = module.FilamentHubCatalog()
    results = []
    monkeypatch.setattr(catalog, "_deliver_slice_result", results.append)

    catalog._do_parse_slice("key", "token")

    assert results == [{"sourceKey": "key", "error": "read"}]
    assert module._SLICE_PARSE_LOCK.acquire(False)
    module._SLICE_PARSE_LOCK.release()


def test_printer_identity_reads_fall_back_to_sequential_when_the_pool_is_refused(
    monkeypatch,
):
    module, _instances = _audited_module(monkeypatch)
    audit = ThreadAudit(monkeypatch, allowed=False)
    monkeypatch.setattr(module, "_observe_moonraker_identity", lambda _c: "instance-1")

    items = module._observations_for_sync(
        [{"print_host": "http://printer.local", "host_type": "moonraker"}],
        discovery_key="k" * 64,
        local_connections=[{"print_host": "http://printer.local"}],
    )

    assert items[0]["device_identity"]["kind"] == "moonraker_instance"
    assert audit.denied


def _refused_session(monkeypatch):
    """A page whose first thread the user refused, with a real worker and a spying host."""
    module, instances = _audited_module(monkeypatch)
    page, _action = _page_and_action(module, instances)
    audit = ThreadAudit(monkeypatch, allowed=False)
    ran = []
    monkeypatch.setattr(module, "BACKGROUND_WORKER", module.ReusableDaemonWorker(
        "filamenthub-test-worker", idle_timeout=0.5,
    ))
    monkeypatch.setattr(module, "_THREADS_REFUSED", False)
    monkeypatch.setattr(module, "_DEFERRED_BACKGROUND", set())
    monkeypatch.setattr(module, "_BACKGROUND_DENIED_PUSHED", False)
    monkeypatch.setattr(module, "load_saved_auth", lambda: {"accessToken": "token"})
    monkeypatch.setattr(module, "_PLUGIN_SETTINGS", dict(module.PLUGIN_SETTINGS_DEFAULTS))
    monkeypatch.setattr(
        module.FilamentHubCatalog, "_prepare_sync",
        lambda self, token, scope, announce, operation_id, trigger: (
            token, set(), announce, [], {}, [], "", [], None, scope, operation_id, trigger,
        ),
    )
    monkeypatch.setattr(
        module.FilamentHubCatalog, "_do_sync", lambda self, *args: ran.append(args)
    )
    monkeypatch.setattr(page._catalog, "_saved_preset_scope", lambda _name: "filament")
    monkeypatch.setattr(page._catalog, "_deliver", lambda *_a, **_k: True)
    monkeypatch.setattr(module, "repair_local_bundle_parents", lambda: 0)
    monkeypatch.setattr(
        module, "load_bambu_config", lambda: {"printers": [{"bridge_token": "t"}]}
    )
    monkeypatch.setattr(
        module, "_next_pending_bambu_revoke_at", lambda: time.time() + 3600
    )
    monkeypatch.setattr(
        module.BAMBU_BRIDGE_RUNTIME, "_run", lambda generation=None: None, raising=False
    )
    monkeypatch.setattr(
        module.STOCK_ALERT_RUNTIME, "_run", lambda generation=None: None, raising=False
    )
    monkeypatch.setattr(module, "_PLUGIN_RUNTIME_ACTIVE", False)
    module.start_plugin_runtime(storage_initialized=True)
    page.get_ui()
    assert audit.denied == ["filamenthub-test-worker"]
    return module, page, audit, ran


def _stop(module):
    module.stop_plugin_runtime()
    module.BAMBU_REVOKE_SCHEDULER.stop()
    module.BACKGROUND_WORKER.stop()


def test_after_a_refusal_automatic_triggers_make_no_thread_attempts(monkeypatch):
    module, page, audit, _ran = _refused_session(monkeypatch)
    pushed = []
    monkeypatch.setattr(
        module, "push_native_notification",
        lambda level, text: pushed.append((level, text)) or True,
    )
    try:
        for _ in range(3):
            page._catalog._on_preset_saved(SimpleNamespace(name="Fil"))
        page._catalog._auto_sync(announce=True, scope="all", trigger="session-auth")
        module.BAMBU_BRIDGE_RUNTIME.wake()
        module.BAMBU_REVOKE_SCHEDULER.start()
        assert module._push_pending_slice_reports() is False

        assert audit.denied == ["filamenthub-test-worker"]
        assert audit.started == []
        assert pushed == [
            ("WarningNotificationLevel", module.ui_text("backgroundDenied"))
        ]
    finally:
        _stop(module)


def test_explicit_sync_after_a_refusal_retries_and_resumes_deferred_work(monkeypatch):
    module, page, audit, ran = _refused_session(monkeypatch)
    session = "bridge-session"
    page._catalog._direct_bridge_session = session
    assert module._DEFERRED_BACKGROUND == {
        "bambu revoke retry", "Bambu bridge", "stock alerts",
    }
    audit.allowed = True
    try:
        page._catalog.on_message({
            "source": "filamenthub-plugin", "type": "sync", "scope": "filament",
            "operationId": "op-1", "bridgeSession": session,
        })

        names = [name for name, _on_ui in audit.started]
        assert names[0] == "filamenthub-test-worker"
        assert "filamenthub-bambu-bridge" in names
        assert "filamenthub-bambu-revoke" in names
        assert module._DEFERRED_BACKGROUND == set()
        assert module._THREADS_REFUSED is False
    finally:
        _stop(module)
