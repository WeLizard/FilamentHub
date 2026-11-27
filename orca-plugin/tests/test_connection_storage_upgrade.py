import builtins
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from . import filamenthub_plugin_test_support as host_support
from .filamenthub_plugin_test_support import _module_with_pages, set_host_attr


BAMBU = {
    "version": 1,
    "source_instance_id": "bambu-source-test-001",
    "printers": [{
        "physical_printer_id": 11,
        "material_system_id": 21,
        "host": "printer.invalid",
        "serial": "BAMBU-TEST-001",
        "access_code": "fixture-code",
        "bridge_token": "fhpb_fixture_bambu",
    }],
}
FLASHFORGE = {
    "version": 1,
    "printers": [{
        "physical_printer_id": 12,
        "material_system_id": 22,
        "serial": "FLASHTEST001",
        "bridge_token": "fhpb_fixture_flashforge",
        "device_identity": {"kind": "flashforge_serial", "token": "f" * 64},
    }],
}
PENDING_REVOKE = {
    "token": "fhpb_fixture_pending_revoke",
    "created_at": 100.0,
    "next_retry_at": 200.0,
    "attempts": 3,
}
SOURCE_ID = "shared-source-test-001"
NEW_WHEEL = "filamenthub-0.3.0-py3-none-any"
OLD_WHEEL = "filamenthub-0.2.10-py3-none-any"
USAGE_FOLDERS = (
    "bambu_usage", "flashforge_usage", "creality_usage", "sdcp_usage",
    "elegoo_mqtt_usage", "anycubic_usage", "prusalink_usage", "moonraker_usage",
)


def _write_state(root, files):
    for name, value in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")


def _saved_bytes(root):
    return {item.relative_to(root): item.read_bytes() for item in root.rglob("*") if item.is_file()}


def _load_for_install(monkeypatch, data_root, install_name, native_name):
    plugin, _ = _module_with_pages(native_lifecycle=True)
    install = data_root / "orca_plugins" / install_name
    native = data_root / "orca_plugins" / "plugin_data" / native_name
    install.mkdir(parents=True, exist_ok=True)
    native.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(plugin, "DEV_CONTOUR", False)
    monkeypatch.setattr(plugin, "DATA_DIR", str(data_root))
    monkeypatch.setattr(plugin, "PLUGIN_DIR", str(install))
    set_host_attr(monkeypatch, plugin.orca.host, "plugin.storage", lambda: str(native))
    return plugin, native


def test_manual_wheel_upgrade_keeps_provider_bindings_and_pending_usage(tmp_path, monkeypatch):
    plugin, _ = _load_for_install(monkeypatch, tmp_path, NEW_WHEEL + ".whl", NEW_WHEEL)
    previous = tmp_path / "orca_plugins" / "plugin_data" / OLD_WHEEL
    destination = tmp_path / ".filamenthub" / "orca-plugin-local"
    _write_state(previous, {
        ".auth.json": {"accessToken": "fixture-auth"},
        ".fh_sync.json": {"_source_instance_id": SOURCE_ID},
        ".fh_bambu.json": BAMBU,
        ".fh_bambu_revoke.json": {"version": 1, "pending": [PENDING_REVOKE]},
        ".fh_flashforge.json": FLASHFORGE,
        ".fh_printer_connections.json": {"version": 1, "connections": []},
        ".fh_creality.json": {"version": 1, "printers": []},
        ".fh_sdcp.json": {"version": 1, "printers": []},
        ".fh_elegoo_mqtt.json": {"version": 1, "printers": []},
        ".fh_anycubic.json": {"version": 1, "printers": []},
        ".fh_prusalink.json": {"version": 1, "printers": []},
        ".fh_moonraker_usage.json": {"version": 1, "printers": []},
        ".fh_slice_reports.json": [{"source_key": "pending-slice"}],
        **{
            f"{folder}/{'a' * 64}.json": {"version": 1, "next_sequence": 7, "events": []}
            for folder in USAGE_FOLDERS
        },
    })
    original = _saved_bytes(previous)

    assert plugin.configure_plugin_storage() is True

    assert Path(plugin.PLUGIN_STORAGE_DIR) == destination
    assert _saved_bytes(previous) == original
    for path, content in original.items():
        assert (destination / path).read_bytes() == content, path
    assert plugin.load_bambu_config_diagnostic() == (BAMBU, "valid")
    assert plugin._load_flashforge_bindings() == FLASHFORGE["printers"]
    assert plugin.plugin_source_instance_id() == SOURCE_ID
    assert plugin._load_pending_bambu_revokes(now=150.0) == [PENDING_REVOKE]
    assert plugin._load_slice_report_outbox() == [{"source_key": "pending-slice"}]


def test_cloud_install_uses_its_own_native_data_without_manual_wheel_state(tmp_path, monkeypatch):
    plugin, native = _load_for_install(monkeypatch, tmp_path, "_subscribed/filamenthub", "filamenthub")
    manual = tmp_path / ".filamenthub" / "orca-plugin-local"
    _write_state(native, {".fh_bambu.json": BAMBU})
    _write_state(manual, {".fh_flashforge.json": FLASHFORGE})

    assert plugin.configure_plugin_storage() is True

    assert Path(plugin.PLUGIN_STORAGE_DIR) == native
    assert plugin.load_bambu_config() == BAMBU
    assert plugin._load_flashforge_bindings() == []
    assert plugin.configure_plugin_storage() is True
    assert plugin.load_bambu_config() == BAMBU


def test_manual_upgrade_does_not_merge_stale_fallback_or_restore_removed_auth(tmp_path, monkeypatch):
    plugin, native = _load_for_install(monkeypatch, tmp_path, NEW_WHEEL + ".whl", NEW_WHEEL)
    fallback = tmp_path / ".filamenthub" / "orca-plugin"
    _write_state(native, {
        ".fh_bambu.json": BAMBU,
        ".auth.json": {"accessToken": "fixture-auth"},
    })
    _write_state(fallback, {".fh_flashforge.json": FLASHFORGE})

    assert plugin.configure_plugin_storage() is True

    assert Path(plugin.PLUGIN_STORAGE_DIR) == tmp_path / ".filamenthub" / "orca-plugin-local"
    assert plugin.load_bambu_config() == BAMBU
    assert plugin._load_flashforge_bindings() == []
    assert plugin.load_saved_auth()["accessToken"] == "fixture-auth"
    plugin.clear_auth()
    assert not plugin.load_saved_auth()

    next_wheel = "filamenthub-0.3.1-py3-none-any"
    plugin, _ = _load_for_install(monkeypatch, tmp_path, next_wheel + ".whl", next_wheel)
    assert plugin.configure_plugin_storage() is True

    assert Path(plugin.PLUGIN_STORAGE_DIR) == tmp_path / ".filamenthub" / "orca-plugin-local"
    assert not plugin.load_saved_auth()
    assert plugin.load_bambu_config() == BAMBU
    assert (native / ".auth.json").is_file()


def test_second_orca_waits_for_storage_migration(tmp_path, monkeypatch):
    first, _ = _load_for_install(monkeypatch, tmp_path, NEW_WHEEL + ".whl", NEW_WHEEL)
    second, _ = _load_for_install(monkeypatch, tmp_path, NEW_WHEEL + ".whl", NEW_WHEEL)
    target = tmp_path / ".filamenthub" / "orca-plugin-local"
    target.mkdir(parents=True)
    previous = tmp_path / "orca_plugins" / "plugin_data" / OLD_WHEEL
    _write_state(previous, {".fh_bambu.json": BAMBU})
    entered = Event()
    sleep = second.time.sleep

    def wait_for_lock(seconds):
        entered.set()
        sleep(seconds)

    monkeypatch.setattr(
        second, "time", SimpleNamespace(monotonic=second.time.monotonic, sleep=wait_for_lock)
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        with first._lock_storage_migration(str(target)):
            result = executor.submit(second.configure_plugin_storage)
            assert entered.wait(timeout=5)
            assert not result.done()
        assert result.result(timeout=5) is True

    assert second.load_bambu_config_diagnostic() == (BAMBU, "valid")


def test_failed_migration_retries_the_same_prior_state(tmp_path, monkeypatch):
    plugin, _ = _load_for_install(monkeypatch, tmp_path, NEW_WHEEL + ".whl", NEW_WHEEL)
    previous = tmp_path / "orca_plugins" / "plugin_data" / OLD_WHEEL
    _write_state(previous, {".fh_bambu.json": BAMBU, ".fh_flashforge.json": FLASHFORGE})
    original = _saved_bytes(previous)
    denied = previous / ".fh_flashforge.json"
    open_file = builtins.open

    def fail_read(path, *args, **kwargs):
        if not isinstance(path, int) and Path(path) == denied:
            raise PermissionError("simulated unavailable migration source")
        return open_file(path, *args, **kwargs)

    storage_before = plugin.PLUGIN_STORAGE_DIR
    with monkeypatch.context() as failure:
        failure.setattr(builtins, "open", fail_read)
        with pytest.raises(PermissionError, match="simulated unavailable migration source"):
            plugin.configure_plugin_storage()

    assert plugin.PLUGIN_STORAGE_DIR == storage_before
    assert _saved_bytes(previous) == original

    assert plugin.configure_plugin_storage() is True

    assert plugin.load_bambu_config() == BAMBU
    assert plugin._load_flashforge_bindings() == FLASHFORGE["printers"]
    assert _saved_bytes(previous) == original


def _load_explicit_wheel(monkeypatch, wheel, data_root):
    wheel = Path(wheel)
    install = data_root / "orca_plugins" / wheel.name
    modules = install / "__whl_extracted__"
    modules.mkdir(parents=True)
    with ZipFile(wheel) as archive:
        for name in archive.namelist():
            if "/" not in name and name.startswith("filamenthub") and name.endswith(".py"):
                (modules / name).write_bytes(archive.read(name))
    native = data_root / "orca_plugins" / "plugin_data" / wheel.stem
    native.mkdir(parents=True)
    with monkeypatch.context() as imports:
        imports.syspath_prepend(str(modules))
        imports.setattr(host_support, "PLUGIN_PATH", modules / "filamenthub_plugin.py")
        plugin, _ = _module_with_pages(native_lifecycle=True)
    set_host_attr(monkeypatch, plugin.orca.host, "plugin.storage", lambda: str(native))
    return plugin, native


def _start_wheel_page(monkeypatch, plugin):
    started = []
    monkeypatch.setattr(
        plugin,
        "start_plugin_runtime",
        lambda *, storage_initialized: started.append((storage_initialized, plugin.PLUGIN_STORAGE_DIR)),
    )
    plugin.FilamentHubPage().on_load()
    assert started == [(True, plugin.PLUGIN_STORAGE_DIR)]


def test_explicit_release_wheels_preserve_existing_connection(tmp_path, monkeypatch):
    old_wheel = os.environ.get("FH_UPGRADE_FROM_WHEEL")
    new_wheel = os.environ.get("FH_UPGRADE_TO_WHEEL")
    if not old_wheel or not new_wheel:
        pytest.skip("set FH_UPGRADE_FROM_WHEEL and FH_UPGRADE_TO_WHEEL for the artifact test")

    old, old_native = _load_explicit_wheel(monkeypatch, old_wheel, tmp_path)
    assert old.PLUGIN_VERSION == "0.2.10"
    _start_wheel_page(monkeypatch, old)
    assert Path(old.PLUGIN_STORAGE_DIR) == old_native
    old.save_bambu_config(BAMBU)
    old._save_flashforge_bindings(FLASHFORGE["printers"])
    assert old.save_auth("fixture-auth")
    old._write_pending_bambu_revokes([PENDING_REVOKE])
    old._queue_slice_report({"source_key": "pending-slice"})
    old.save_sync_state({"_source_instance_id": SOURCE_ID})
    old_source = old.plugin_source_instance_id()
    assert old_source == SOURCE_ID
    flashforge = FLASHFORGE["printers"][0]
    old_journal = Path(old._flashforge_usage_journal(flashforge, old_source))
    pending_usage = {"version": 1, "next_sequence": 7, "events": [{"event_id": "fixture-event"}]}
    _write_state(old_native, {old_journal.relative_to(old_native): pending_usage})
    old_files = _saved_bytes(old_native)

    new, _ = _load_explicit_wheel(monkeypatch, new_wheel, tmp_path)
    assert new.PLUGIN_VERSION == "0.3.0"
    _start_wheel_page(monkeypatch, new)
    assert new.load_bambu_config_diagnostic() == (BAMBU, "valid")
    assert new._load_flashforge_bindings() == FLASHFORGE["printers"]
    assert new.plugin_source_instance_id() == old_source
    assert new.load_saved_auth()["accessToken"] == "fixture-auth"
    assert new._load_pending_bambu_revokes(now=150.0) == [PENDING_REVOKE]
    assert new._load_slice_report_outbox() == [{"source_key": "pending-slice"}]
    new_journal = new._usage_journal(new.FLASHFORGE_CONFIG_FILE, "flashforge_usage", flashforge, old_source)
    assert new._load_usage_books(new_journal) == pending_usage
    assert _saved_bytes(old_native) == old_files


def test_migration_rebases_owned_slice_cache_path_only(tmp_path, monkeypatch):
    plugin, _ = _load_for_install(monkeypatch, tmp_path, NEW_WHEEL + ".whl", NEW_WHEEL)
    previous = tmp_path / "orca_plugins" / "plugin_data" / OLD_WHEEL
    destination = tmp_path / ".filamenthub" / "orca-plugin-local"
    key = "b" * 64
    external_key = "c" * 64
    old_cache = previous / "slices" / f"{key}.gcode"
    external = tmp_path / "user-export.gcode"
    external.write_text("G28", encoding="utf-8")
    _write_state(previous, {
        ".fh_slices.json": {
            key: {"path": str(old_cache), "name": "cached.gcode"},
            external_key: {"path": str(external), "name": external.name},
        },
    })
    old_cache.parent.mkdir()
    old_cache.write_bytes(b"G90\n")
    original = _saved_bytes(previous)

    assert plugin.configure_plugin_storage() is True

    expected_cache = destination / "slices" / old_cache.name
    assert Path(plugin.slice_path_for_key(key)) == expected_cache
    assert expected_cache.read_bytes() == b"G90\n"
    assert Path(plugin.slice_path_for_key(external_key)) == external
    assert _saved_bytes(previous) == original


def test_subscribed_install_does_not_import_state_from_package(tmp_path, monkeypatch):
    plugin, native = _load_for_install(monkeypatch, tmp_path, "_subscribed/filamenthub", "filamenthub")
    install = Path(plugin.PLUGIN_DIR)
    _write_state(install, {
        ".fh_bambu.json": BAMBU,
        ".auth.json": {"accessToken": "package-sentinel"},
    })
    original = _saved_bytes(install)

    assert plugin.configure_plugin_storage() is True

    assert Path(plugin.PLUGIN_STORAGE_DIR) == native
    assert plugin.load_bambu_config_diagnostic()[1] == "missing"
    assert plugin.load_saved_auth() is None
    assert _saved_bytes(install) == original


def test_completed_migration_never_reads_inaccessible_prior_store(tmp_path, monkeypatch):
    plugin, _ = _load_for_install(monkeypatch, tmp_path, NEW_WHEEL + ".whl", NEW_WHEEL)
    previous = tmp_path / "orca_plugins" / "plugin_data" / OLD_WHEEL
    _write_state(previous, {".fh_bambu.json": BAMBU})

    assert plugin.configure_plugin_storage() is True
    assert plugin.load_bambu_config() == BAMBU

    next_wheel = "filamenthub-0.3.1-py3-none-any"
    plugin, _ = _load_for_install(monkeypatch, tmp_path, next_wheel + ".whl", next_wheel)
    lstat = os.lstat
    prior_accesses = []

    def deny_lstat(path, *args, **kwargs):
        if not isinstance(path, int):
            checked = Path(path)
            if checked == previous or previous in checked.parents:
                prior_accesses.append(checked)
                raise PermissionError("simulated unavailable previous native store")
        return lstat(path, *args, **kwargs)

    with monkeypatch.context() as failure:
        failure.setattr(os, "lstat", deny_lstat)
        assert plugin.configure_plugin_storage() is True

    assert not prior_accesses
    assert Path(plugin.PLUGIN_STORAGE_DIR) == tmp_path / ".filamenthub" / "orca-plugin-local"
    assert plugin.load_bambu_config() == BAMBU
