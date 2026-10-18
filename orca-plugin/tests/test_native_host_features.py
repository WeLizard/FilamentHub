"""OrcaSlicer 2.5.0-alpha host features: PresetSaved sync, native notices,
the Speed Dial action, the host version in reports and the bundle listing."""

from .filamenthub_plugin_test_support import (
    _module_with_pages,
    fake_app_info,
    fake_preset_bundle,
    json,
    lifecycle_context,
    LIFECYCLE_EVENT_NAMES,
    pytest,
    remove_host_attr,
    set_host_attr,
    SimpleNamespace,
    threading,
)


class RecordingWorker:
    """Stands in for BACKGROUND_WORKER: queues jobs so a test decides when they run."""

    def __init__(self):
        self.jobs = []

    def submit(self, function, *args, **kwargs):
        self.jobs.append((function, args, kwargs))
        return True

    def run_if_current(self, function, *args, **kwargs):
        return function(*args, **kwargs)

    def run_all(self):
        jobs, self.jobs = self.jobs, []
        for function, args, kwargs in jobs:
            function(*args, **kwargs)


class Harness:
    def __init__(self, module, registered, monkeypatch):
        self.module = module
        self.registered = registered
        self.instances = [cls() for cls in registered]
        self.worker = RecordingWorker()
        self.token = {"accessToken": "token"}
        self.events = []
        self.ran = []
        monkeypatch.setattr(module, "BACKGROUND_WORKER", self.worker)
        monkeypatch.setattr(module, "load_saved_auth", lambda: self.token)
        monkeypatch.setattr(module, "_PLUGIN_SETTINGS", dict(module.PLUGIN_SETTINGS_DEFAULTS))
        monkeypatch.setattr(module, "refresh_ui_language", lambda: "en")

        def prepare(catalog, token, scope, announce, operation_id, trigger):
            self.events.append(("prepare", scope))
            snapshot = "snapshot-%d" % len(self.events)
            return (
                token, snapshot, announce, [], {}, [], "", [], None,
                scope, operation_id, trigger,
            )

        monkeypatch.setattr(module.FilamentHubCatalog, "_prepare_sync", prepare)
        monkeypatch.setattr(
            module.FilamentHubCatalog, "_do_sync",
            lambda catalog, *args: self.ran.append(args),
        )
        self.monkeypatch = monkeypatch

    @property
    def page(self):
        return next(i for i in self.instances if isinstance(i, self.module.FilamentHubPage))

    def set_presets(self, filaments=(), prints=(), printers=()):
        set_host_attr(
            self.monkeypatch, self.module.orca.host, "preset_bundle",
            lambda: fake_preset_bundle(filaments, prints, printers),
        )

    def dispatch(self, event_name, name="", instances=None):
        orca = self.module.orca
        event = getattr(orca.LifecycleEvent, event_name)
        context = lifecycle_context(orca, name)
        for instance in self.instances if instances is None else instances:
            handler = getattr(instance, "on_lifecycle_event", None)
            if handler is not None:
                handler(event, context)

    def save(self, name):
        self.dispatch("PresetSaved", name)


@pytest.fixture
def harness(monkeypatch):
    module, registered = _module_with_pages(
        native_lifecycle=True, lifecycle_events=True, slicing=True
    )
    module.FilamentHubPlugin().register_capabilities()
    return Harness(module, registered, monkeypatch)


def test_one_preset_save_with_every_capability_registered_submits_one_sync(harness):
    harness.set_presets(filaments=["My PETG"], prints=["My process"])
    assert {cls.__name__ for cls in harness.registered} == {
        "FilamentHubPage", "FilamentHubSyncAction", "FilamentHubSliceReporter",
    }

    harness.save("My PETG")

    assert len(harness.worker.jobs) == 1
    harness.worker.run_all()
    (args,) = harness.ran
    token, snapshot, announce, _, _, _, _, _, _, scope, operation_id, trigger = args
    assert (token, scope, announce, operation_id, trigger) == (
        "token", "filament", False, "", "preset-saved",
    )
    assert snapshot == "snapshot-1"


def test_only_preset_saved_starts_a_sync_and_other_events_do_no_work(
    harness, monkeypatch
):
    harness.set_presets(filaments=["My PETG"])
    module = harness.module
    # Nothing but the comparison may run for the other events: no log line, no
    # host read, no settings or token lookup.
    harness.dispatch("PresetSaved", "My PETG")
    assert len(harness.worker.jobs) == 1
    harness.worker.jobs.clear()
    monkeypatch.setattr(module, "fh_log", pytest.fail)
    monkeypatch.setattr(module, "load_saved_auth", pytest.fail)
    monkeypatch.setattr(module, "read_capability_settings", pytest.fail)
    set_host_attr(monkeypatch, module.orca.host, "preset_bundle", pytest.fail)

    for name in LIFECYCLE_EVENT_NAMES:
        if name != "PresetSaved":
            harness.dispatch(name, "My PETG")

    assert harness.worker.jobs == []


def test_preset_saved_needs_auto_sync_and_a_saved_token(harness):
    harness.set_presets(filaments=["My PETG"])
    page = harness.page

    page.get_config = lambda: json.dumps({"auto_sync": False})
    harness.save("My PETG")
    assert harness.worker.jobs == []

    page.get_config = lambda: json.dumps({"auto_sync": True})
    harness.token = None
    harness.save("My PETG")
    assert harness.worker.jobs == []

    harness.token = {"accessToken": "token"}
    harness.save("My PETG")
    assert len(harness.worker.jobs) == 1


def test_preset_saved_picks_the_collection_and_skips_what_it_cannot_tell(harness):
    harness.set_presets(
        filaments=["Fil", "Same"], prints=["Proc", "Same"], printers=["Printer"]
    )
    for name in ("Printer", "Same", "Nothing like it", ""):
        harness.save(name)
    assert harness.worker.jobs == []
    assert harness.events == []

    harness.save("Proc")
    harness.save("Fil")
    harness.worker.run_all()
    assert [args[9] for args in harness.ran] == ["process", "filament"]


def test_filament_and_process_saved_back_to_back_both_sync(harness):
    harness.set_presets(filaments=["Fil"], prints=["Proc"])

    harness.save("Fil")
    harness.save("Proc")
    harness.worker.run_all()

    assert sorted(args[9] for args in harness.ran) == ["filament", "process"]


def test_saves_queued_behind_a_running_sync_collapse_to_one_follow_up(harness):
    harness.set_presets(filaments=["Fil"], prints=["Proc"])

    for _ in range(3):
        harness.save("Fil")
    harness.save("Proc")
    # Each save took its own snapshot on the UI thread; only the newest of a
    # kind is worth uploading.
    assert [event for event in harness.events if event[0] == "prepare"] == [
        ("prepare", "filament")
    ] * 3 + [("prepare", "process")]
    harness.worker.run_all()

    assert [(args[9], args[1]) for args in harness.ran] == [
        ("filament", "snapshot-3"), ("process", "snapshot-4"),
    ]


def test_preset_saved_never_sleeps_the_serial_worker(harness, monkeypatch):
    harness.set_presets(filaments=["Fil"])
    monkeypatch.setattr(harness.module.time, "sleep", pytest.fail)

    harness.save("Fil")
    harness.save("Fil")
    harness.worker.run_all()

    assert len(harness.ran) == 1


def test_old_host_catalog_capability_also_reacts_to_preset_saved(monkeypatch):
    module, registered = _module_with_pages(lifecycle_events=True, pages=False)
    module.FilamentHubPlugin().register_capabilities()
    assert registered == [module.FilamentHubCatalog]
    harness = Harness(module, registered, monkeypatch)
    harness.set_presets(prints=["Proc"])

    harness.save("Proc")
    harness.dispatch("ObjectChanged", "Proc")

    assert len(harness.worker.jobs) == 1
    assert harness.worker.jobs[0][1][0] == "process"


def test_host_without_lifecycle_events_never_reacts(plugin_module):
    assert not hasattr(plugin_module.orca, "LifecycleEvent")
    assert plugin_module._PRESET_SAVED_EVENT is None
    catalog = plugin_module.FilamentHubCatalog()
    catalog.on_lifecycle_event("PresetSaved", SimpleNamespace(name="x"))


@pytest.mark.parametrize("trigger", ["manual", "profile-change", "session-auth", "auto"])
def test_other_triggers_never_use_native_notifications(plugin_module, trigger):
    for status in ("success", "warning", "error"):
        assert plugin_module.native_sync_notice(trigger, status, True, True) is None


def test_preset_saved_notice_speaks_only_about_failure_warning_or_restart(plugin_module):
    notice = plugin_module.native_sync_notice
    ui_text = plugin_module.ui_text

    assert notice("preset-saved", "success", False, False) is None
    assert notice("preset-saved", "warning", False, False) is None
    assert notice("preset-saved", "error", False, False) == (
        "ErrorNotificationLevel", ui_text("syncPartialTitle"),
    )
    assert notice("preset-saved", "warning", True, False) == (
        "WarningNotificationLevel", ui_text("syncAttentionTitle"),
    )
    assert notice("preset-saved", "success", False, True) == (
        "WarningNotificationLevel",
        ui_text("syncCompleteTitle") + "\n" + ui_text("dropdownRestart"),
    )


def test_speed_dial_notice_reports_success_too(plugin_module):
    ui_text = plugin_module.ui_text

    assert plugin_module.native_sync_notice("speed-dial", "success", False, False) == (
        "RegularNotificationLevel", ui_text("syncCompleteTitle"),
    )
    assert plugin_module.native_sync_notice("speed-dial", "error", False, False) == (
        "ErrorNotificationLevel", ui_text("syncPartialTitle"),
    )


def _process_sync(module, monkeypatch, trigger, operation_id="", complete=False):
    monkeypatch.setattr(module, "load_sync_state", lambda: {})
    monkeypatch.setattr(module, "save_sync_state", lambda _state: None)
    monkeypatch.setattr(module, "push_user_profiles", lambda *a, **k: (0, 0))
    monkeypatch.setattr(module, "_sync_preferences", lambda _token: {
        "available": True, "allow_print_profiles_import": True,
    })
    catalog = module.FilamentHubCatalog()
    delivered = []
    monkeypatch.setattr(catalog, "_deliver", lambda kind, **data: delivered.append(kind))
    catalog._do_sync(
        "token", set(), announce=False,
        host_profiles={"process": {"items": [], "complete": complete}},
        scope="process", operation_id=operation_id, trigger=trigger,
    )
    return delivered


def test_finished_syncs_push_a_notice_only_for_preset_saved_and_speed_dial(
    plugin_module, monkeypatch
):
    pushed = []
    monkeypatch.setattr(
        plugin_module, "push_native_notification",
        lambda level, text: pushed.append((level, text)) or True,
    )

    delivered = _process_sync(plugin_module, monkeypatch, "preset-saved")
    assert pushed == [(
        "WarningNotificationLevel", plugin_module.ui_text("syncAttentionTitle"),
    )]
    assert delivered == []

    pushed.clear()
    _process_sync(plugin_module, monkeypatch, "preset-saved", complete=True)
    assert pushed == []

    _process_sync(plugin_module, monkeypatch, "speed-dial", complete=True)
    assert pushed == [(
        "RegularNotificationLevel", plugin_module.ui_text("syncCompleteTitle"),
    )]

    pushed.clear()
    delivered = _process_sync(
        plugin_module, monkeypatch, "manual", operation_id="sync-page"
    )
    assert pushed == []
    assert delivered == ["sync-result"]


@pytest.mark.parametrize("trigger, pushes", [("speed-dial", True), ("preset-saved", False)])
def test_unreachable_server_is_pushed_only_for_the_speed_dial_run(
    plugin_module, monkeypatch, trigger, pushes
):
    pushed = []
    monkeypatch.setattr(
        plugin_module, "push_native_notification",
        lambda level, text: pushed.append((level, text)) or True,
    )
    monkeypatch.setattr(
        plugin_module, "_sync_preferences", lambda _token: {"available": False}
    )

    plugin_module.FilamentHubCatalog()._do_sync(
        "token", set(), announce=False, scope="process", trigger=trigger
    )

    assert pushed == (
        [("WarningNotificationLevel", plugin_module.ui_text("syncUnreachable"))]
        if pushes else []
    )


def test_native_notification_uses_the_host_api_when_present(plugin_module, monkeypatch):
    host = plugin_module.orca.host
    shown = []
    set_host_attr(
        monkeypatch, host, "ui.push_notification",
        lambda level, text: shown.append((level, text)),
    )
    set_host_attr(
        monkeypatch, host, "ui.NotificationLevel",
        SimpleNamespace(WarningNotificationLevel="warning-level"),
    )

    assert plugin_module.push_native_notification("WarningNotificationLevel", "Hello")
    assert shown == [("warning-level", "Hello")]
    assert not plugin_module.push_native_notification("NoSuchLevel", "Hello")
    assert not plugin_module.push_native_notification("WarningNotificationLevel", "")
    assert shown == [("warning-level", "Hello")]


def test_native_notification_is_safe_without_the_host_api(plugin_module, monkeypatch):
    host = plugin_module.orca.host
    remove_host_attr(monkeypatch, host, "ui.push_notification")
    remove_host_attr(monkeypatch, host, "ui.NotificationLevel")
    assert plugin_module.push_native_notification("WarningNotificationLevel", "x") is False

    set_host_attr(monkeypatch, host, "ui.push_notification", pytest.fail)
    assert plugin_module.push_native_notification("WarningNotificationLevel", "x") is False

    def refuse(_level, _text):
        raise RuntimeError("OrcaSlicer is closing")

    set_host_attr(monkeypatch, host, "ui.push_notification", refuse)
    set_host_attr(
        monkeypatch, host, "ui.NotificationLevel",
        SimpleNamespace(WarningNotificationLevel="warning-level"),
    )
    assert plugin_module.push_native_notification("WarningNotificationLevel", "x") is False


def test_slice_reporting_never_pushes_a_native_notification(harness, monkeypatch):
    module = harness.module
    monkeypatch.setattr(module, "push_native_notification", pytest.fail)
    reporter = next(
        i for i in harness.instances if isinstance(i, module.FilamentHubSliceReporter)
    )

    result = reporter.execute(SimpleNamespace(
        step="psGCodePostProcess", gcode_path="", output_name="", host="",
    ))

    assert result[0] == "skipped"


def test_speed_dial_action_has_a_fixed_unlocalized_name(harness, monkeypatch):
    action = next(
        i for i in harness.instances if isinstance(i, harness.module.FilamentHubSyncAction)
    )
    assert action.get_name() == "FilamentHub Sync"
    monkeypatch.setattr(harness.module, "_CACHED_UI_LANGUAGE", "ru")
    assert action.get_name() == "FilamentHub Sync"


def test_speed_dial_action_without_a_token_asks_to_sign_in(harness):
    module = harness.module
    action = next(i for i in harness.instances if isinstance(i, module.FilamentHubSyncAction))
    module._set_slice_delivery_target(harness.page._catalog)
    harness.token = None

    assert action.execute() == ("skipped", module.ui_text("syncSignIn"))
    assert harness.worker.jobs == []


def test_speed_dial_action_with_a_token_starts_a_full_sync(harness):
    module = harness.module
    action = next(i for i in harness.instances if isinstance(i, module.FilamentHubSyncAction))
    module._set_slice_delivery_target(harness.page._catalog)

    assert action.execute() == module.ui_text("syncStarted")
    harness.worker.run_all()

    (args,) = harness.ran
    token, _, announce, *_rest, scope, operation_id, trigger = args
    assert (token, announce, scope, operation_id, trigger) == (
        "token", False, "all", "", "speed-dial",
    )


def test_speed_dial_action_without_a_loaded_page_does_not_start_anything(harness):
    module = harness.module
    action = next(i for i in harness.instances if isinstance(i, module.FilamentHubSyncAction))
    module._set_slice_delivery_target(None)

    assert action.execute() == ("skipped", module.ui_text("syncUnavailable"))
    assert harness.worker.jobs == []


def test_problem_report_names_the_orcaslicer_version(plugin_module, monkeypatch, tmp_path):
    monkeypatch.setattr(plugin_module, "SYNC_LOG_FILE", str(tmp_path / "missing.log"))
    monkeypatch.setattr(plugin_module, "_CACHED_HOST_VERSION", "")
    monkeypatch.setattr(plugin_module, "_CACHED_HOST_BUILD", "")
    host = plugin_module.orca.host
    assert "OrcaSlicer unknown (unknown)\n" in plugin_module.diagnostic_report_text()

    set_host_attr(
        monkeypatch, host, "app_info",
        fake_app_info("en", version="2.5.0-alpha", build="Release-1234"),
    )
    plugin_module.refresh_ui_language()
    assert "OrcaSlicer 2.5.0-alpha (Release-1234)\n" in plugin_module.diagnostic_report_text()

    # A worker thread cannot read app_info(): the last good values stay.
    results = []
    thread = threading.Thread(target=lambda: results.append(plugin_module.refresh_ui_language()))
    thread.start()
    thread.join(2)
    assert "OrcaSlicer 2.5.0-alpha (Release-1234)\n" in plugin_module.diagnostic_report_text()

    set_host_attr(
        monkeypatch, host, "app_info", fake_app_info("en", version="", build=""),
    )
    plugin_module.refresh_ui_language()
    assert "OrcaSlicer 2.5.0-alpha (Release-1234)\n" in plugin_module.diagnostic_report_text()


def _bundle_host(monkeypatch, plugin_module, listed, reload_calls, logged):
    host = plugin_module.orca.host
    set_host_attr(
        monkeypatch, host, "preset.bundles.reload_local",
        lambda bundle_id: reload_calls.append(bundle_id),
    )
    if listed is not None:
        set_host_attr(monkeypatch, host, "preset.bundles.list_ids", listed)
    else:
        remove_host_attr(monkeypatch, host, "preset.bundles.list_ids")
    monkeypatch.setattr(plugin_module, "fh_log", logged.append)


def test_reload_is_skipped_with_a_reason_when_the_host_does_not_list_the_bundle(
    plugin_module, monkeypatch
):
    reload_calls, logged = [], []
    _bundle_host(monkeypatch, plugin_module, lambda: ["other"], reload_calls, logged)

    assert plugin_module.reload_managed_local_bundle_if_available() is False
    assert reload_calls == []
    assert any("not offered by the host" in line for line in logged)


def test_reload_runs_when_the_host_lists_the_bundle(plugin_module, monkeypatch):
    reload_calls, logged = [], []
    _bundle_host(
        monkeypatch, plugin_module, lambda: ["other", plugin_module.BUNDLE_ID],
        reload_calls, logged,
    )

    assert plugin_module.reload_managed_local_bundle_if_available() is True
    assert reload_calls == [plugin_module.BUNDLE_ID]


def test_reload_without_the_listing_api_keeps_the_direct_call(plugin_module, monkeypatch):
    reload_calls, logged = [], []
    _bundle_host(monkeypatch, plugin_module, None, reload_calls, logged)

    assert plugin_module.reload_managed_local_bundle_if_available() is True
    assert reload_calls == [plugin_module.BUNDLE_ID]


def test_reload_still_tries_when_the_listing_itself_fails(plugin_module, monkeypatch):
    reload_calls, logged = [], []

    def broken():
        raise RuntimeError("OrcaSlicer is closing")

    _bundle_host(monkeypatch, plugin_module, broken, reload_calls, logged)

    assert plugin_module.reload_managed_local_bundle_if_available() is True
    assert reload_calls == [plugin_module.BUNDLE_ID]
    assert any("listing failed" in line for line in logged)
