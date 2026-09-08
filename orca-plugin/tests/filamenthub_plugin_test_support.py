# ruff: noqa: F401
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

import urllib.parse

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

@pytest.fixture
def setup_flow(plugin_module, monkeypatch, tmp_path):
    plugin = plugin_module
    monkeypatch.setattr(plugin, "AUTH_FILE", str(tmp_path / "auth.json"))
    monkeypatch.setattr(plugin, "BAMBU_CONFIG_FILE", str(tmp_path / "bambu.json"))
    monkeypatch.setattr(plugin, "discover_lan_printers", lambda: ([], True))
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

def setup_bind_and_activate(catalog, context, probe):
    context["bindings"] = [{"connection_ref": probe["connection"]["connection_ref"],
                            "physical_printer_id": 7, "status": "bound"}]
    catalog._do_printer_setup({"operation": "activate", "requestId": "activate",
                              "physicalPrinterId": 7, "probeId": probe["probeId"]}, "token", [])

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

def _slice_storage(module, tmp_path, monkeypatch):
    """Index and cache in a scratch dir, and a temp root nothing else lives in."""
    monkeypatch.setattr(module, "_SLICE_INDEX_FILE", str(tmp_path / "slices.json"))
    monkeypatch.setattr(module, "_SLICE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path / "no-temp-here"))

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

class _BambuMqttSocket:
    def __init__(self, packets, terminal_error=None):
        self._incoming = bytearray().join(packets)
        self._terminal_error = terminal_error or TimeoutError("inert Bambu socket")
        self.sent = []
        self.timeouts = []
        self.closed = False

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def recv(self, length):
        if not self._incoming:
            raise self._terminal_error
        chunk = self._incoming[:length]
        del self._incoming[:length]
        return bytes(chunk)

    def sendall(self, payload):
        self.sent.append(payload)

    def close(self):
        self.closed = True

def _bambu_mqtt_packet(plugin_module, header, body=b""):
    return bytes([header]) + plugin_module._mqtt_len(len(body)) + body

def _bambu_mqtt_report(plugin_module, serial, payload, topic_suffix="report"):
    topic = f"device/{serial}/{topic_suffix}".encode("utf-8")
    body = plugin_module._mqtt_field(topic) + payload
    return _bambu_mqtt_packet(plugin_module, 0x30, body)

def _bambu_snapshot_socket(plugin_module, *reports, terminal_error=None, connack_code=0):
    packets = [
        _bambu_mqtt_packet(plugin_module, 0x20, bytes([0, connack_code])),
        _bambu_mqtt_packet(plugin_module, 0x90, b"\x00\x01\x00"),
        *reports,
    ]
    return _BambuMqttSocket(packets, terminal_error=terminal_error)

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

def _immediate_commit(provider_index=1, revision=4):
    return {
        "materialSlotId": 71,
        "providerIndex": provider_index,
        "assignmentRevision": revision,
        "desired": {
            "presetId": 41,
            "spoolId": 301,
            "sourceTs": "2026-09-05T12:00:00Z",
        },
    }

def _immediate_device(provider="bambu", provider_index=1, revision=4):
    return {
        "id": 3,
        "inventory_key_digest": "a" * 64,
        "connection_refs": ["fh-ref"],
        "material_systems": [{
            "id": 7,
            "provider": provider,
            "slots": [{
                "material_slot_id": 71,
                "provider_index": provider_index,
                "assignment_revision": revision,
                "preset_id": 41,
                "spool_id": 301,
                "source_ts": "2026-09-05T12:00:00Z",
            }],
        }],
    }

def _active_revoke_scheduler(plugin_module, monkeypatch, tmp_path):
    state_path = tmp_path / ".fh_bambu_revoke.json"
    scheduler = plugin_module.BambuRevokeScheduler()
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(state_path))
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_SCHEDULER", scheduler)
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_ACTIVE", True)
    monkeypatch.setattr(plugin_module, "_PLUGIN_RUNTIME_EPOCH", 1)
    return scheduler

__all__ = [name for name in globals() if not name.startswith('__')]
