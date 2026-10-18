"""Embedded shell, localization and filename contracts."""

import threading

from .filamenthub_plugin_test_support import (
    fake_app_info,
    json,
    _load_module,
    LOCALE_VALIDATOR_PATH,
    PLUGIN_ROOT,
    pytest,
    remove_host_attr,
    set_host_attr,
    SimpleNamespace,
)


@pytest.fixture
def host_language(plugin_module, monkeypatch):
    """Install the strict-host app_info() and start from an empty language cache."""
    monkeypatch.setattr(plugin_module, "_CACHED_UI_LANGUAGE", "")

    def install(language):
        set_host_attr(
            monkeypatch, plugin_module.orca.host, "app_info", fake_app_info(language)
        )

    return install



def test_direct_page_bootstrap_keeps_a_localized_service_failure_state(plugin_module):
    rendered = plugin_module.render_direct_page("b" * 32)

    assert plugin_module.EMBED_URL in rendered
    assert "fh_bridge=" in rendered
    assert "fetch(target" in rendered
    assert "location.replace(target)" in rendered
    assert plugin_module.ui_text("unavailableTitle") in rendered
    assert plugin_module.ui_text("unavailableMessage") in rendered
    assert "127.0.0.1" not in rendered


def test_local_dialog_contains_only_host_owned_forms(plugin_module):
    action = {
        "type": "configure-bambu",
        "physicalPrinterId": 7,
        "materialSystemId": 8,
        "pairingCode": "one-time-code",
    }
    rendered = plugin_module.render_local_dialog(action, "d" * 32)

    assert "localDialogSession" in rendered
    assert "prepare-bambu-local" in rendered
    assert "configure-bambu-local" in rendered
    assert "<iframe" not in rendered
    assert plugin_module.SITE_URL not in rendered
    assert "127.0.0.1" not in rendered


# Values of GUI_App::current_language_code_safe() at OrcaSlicer 3880f2c58ec3
# (src/slic3r/GUI/GUI_App.cpp): full locales, one fixed region per language,
# and "en_US" for everything it has no mapping for (including ca, eu, hu).
UPSTREAM_LANGUAGE_CODES = [
    ("cs_CZ", "cs"), ("de_DE", "de"), ("nl_NL", "nl"), ("sv_SE", "sv"),
    ("es_ES", "es"), ("fr_FR", "fr"), ("it_IT", "it"), ("ja_JP", "ja"),
    ("ko_KR", "ko"), ("pl_PL", "pl"), ("uk_UA", "uk"), ("zh_CN", "zh_CN"),
    ("ru_RU", "ru"), ("tr_TR", "tr"), ("pt_BR", "pt_BR"), ("lt_LT", "lt"),
    ("vi_VN", "vi"), ("th_TH", "th"), ("en_US", "en"),
]


@pytest.mark.parametrize(("code", "locale"), UPSTREAM_LANGUAGE_CODES)
def test_every_code_orca_reports_maps_to_a_bundled_catalog(
    plugin_module, code, locale
):
    assert plugin_module.normalize_ui_language(code) == locale
    assert locale in plugin_module.ORCA_UI_LOCALES
    assert locale in plugin_module.UI_COPY


@pytest.mark.parametrize(
    ("code", "locale"),
    [
        ("zh_TW", "zh_TW"),
        ("zh-TW", "zh_TW"),
        ("zh_Hant", "zh_TW"),
        ("ca_ES", "ca"),
        ("eu_ES", "eu"),
        ("hu_HU", "hu"),
        ("xx_XX", "en"),
        ("unsupported", "en"),
        ("", ""),
        (None, ""),
    ],
)
def test_other_language_spellings_keep_their_catalog_or_fall_back(
    plugin_module, code, locale
):
    assert plugin_module.normalize_ui_language(code) == locale


@pytest.mark.parametrize(
    ("code", "expected", "site_language"),
    [
        ("ru_RU", "ru", "ru"),
        ("zh_CN", "zh_CN", "zh"),
        ("pt_BR", "pt_BR", "en"),
        ("en_US", "en", "en"),
        ("de_DE", "de", "en"),
    ],
)
def test_direct_page_uses_orca_ui_language(
    plugin_module, host_language, code, expected, site_language
):
    host_language(code)

    rendered = plugin_module.render_direct_page("b" * 32)

    assert f"&lng={site_language}" in rendered
    assert "fh_bridge=" in rendered
    assert json.dumps(
        plugin_module.resolved_ui_catalog(expected)["unavailableTitle"],
        ensure_ascii=False,
    ) in rendered


def test_direct_page_language_falls_back_on_older_hosts(
    plugin_module, monkeypatch, host_language
):
    remove_host_attr(monkeypatch, plugin_module.orca.host, "app_info")
    rendered = plugin_module.render_direct_page("b" * 32)
    assert "&lng=" not in rendered

    def unavailable():
        raise RuntimeError("OrcaSlicer application is not initialized")

    set_host_attr(monkeypatch, plugin_module.orca.host, "app_info", unavailable)
    rendered = plugin_module.render_direct_page("b" * 32)
    assert "&lng=" not in rendered


def test_orca_never_exposes_the_language_as_a_host_function(plugin_module):
    # Only app_info()["language"] exists upstream; the strict host refuses the rest.
    with pytest.raises(AttributeError):
        plugin_module.orca.host.app_language
    assert plugin_module.host_ui_language() == ""


def test_language_comes_from_app_info_and_ignores_malformed_answers(
    plugin_module, monkeypatch
):
    host = plugin_module.orca.host
    set_host_attr(monkeypatch, host, "app_info", fake_app_info("ru_RU"))
    assert plugin_module.host_ui_language() == "ru"
    set_host_attr(monkeypatch, host, "app_info", fake_app_info(""))
    assert plugin_module.host_ui_language() == ""
    set_host_attr(monkeypatch, host, "app_info", lambda: None)
    assert plugin_module.host_ui_language() == ""
    set_host_attr(monkeypatch, host, "app_info", lambda: {"language": None})
    assert plugin_module.host_ui_language() == ""


def test_worker_thread_reads_never_overwrite_the_cached_language(
    plugin_module, host_language
):
    host_language("ru_RU")
    assert plugin_module.refresh_ui_language() == "ru"

    seen = []
    # app_info() raises RuntimeError off the UI thread, exactly like upstream.
    worker = threading.Thread(
        target=lambda: seen.append(
            (plugin_module.host_ui_language(), plugin_module.refresh_ui_language())
        )
    )
    worker.start()
    worker.join(5)

    assert seen == [("", "ru")]
    assert plugin_module.ui_text("connectTitle") == (
        plugin_module.resolved_ui_catalog("ru")["connectTitle"]
    )


def test_unreadable_language_keeps_the_last_good_value_on_the_ui_thread(
    plugin_module, monkeypatch, host_language
):
    host_language("zh_CN")
    assert plugin_module.refresh_ui_language() == "zh_CN"
    set_host_attr(
        monkeypatch, plugin_module.orca.host, "app_info", fake_app_info("")
    )
    assert plugin_module.refresh_ui_language() == "zh_CN"


def test_embed_url_without_an_explicit_language_follows_the_cached_host_language(
    plugin_module, host_language
):
    host_language("ru_RU")
    assert plugin_module.localized_embed_url().endswith("&lng=ru")


def test_native_plugin_messages_follow_orca_ui_language(
    plugin_module, monkeypatch, host_language
):
    messages = []
    host_language("ru_RU")
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
        {"operation_id": "", "scope": "all", "status": "warning"},
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
    catalog._direct_bridge_session = "test-session"
    monkeypatch.setattr(catalog, "_known_filament_preset_names", lambda: {"Known"})

    catalog.on_message({
        "source": "filamenthub-plugin",
        "bridgeSession": "test-session",
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
    assert delivered[0][2]["status"] == "success"
    assert delivered[0][2]["contours"] == [{
        "kind": "filament",
        "status": "success",
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
    assert delivered[0]["status"] == "warning"
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
    plugin_module, tmp_path, monkeypatch, host_language
):
    for locale in plugin_module.ORCA_UI_LOCALES:
        assert plugin_module.normalize_ui_language(locale) == locale
        host_language(locale)
        rendered = plugin_module.render_direct_page("b" * 32)
        site_language = (
            "ru" if locale == "ru"
            else "zh" if locale in {"zh_CN", "zh_TW"}
            else "en"
        )
        assert f"&lng={site_language}" in rendered
        assert json.dumps(
            plugin_module.resolved_ui_catalog(locale)["unavailableTitle"],
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
        f"&lng={site_language}"
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
