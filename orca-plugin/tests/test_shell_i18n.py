"""Embedded shell, localization and filename contracts."""

from .filamenthub_plugin_test_support import (
    json,
    _load_module,
    LOCALE_VALIDATOR_PATH,
    PLUGIN_PATH,
    PLUGIN_ROOT,
    pytest,
    SimpleNamespace,
)


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
