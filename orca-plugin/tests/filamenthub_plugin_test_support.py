# ruff: noqa: F401
from __future__ import annotations

import base64

import csv

from enum import Enum

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

# --------------------------------------------------------------------------- #
# Strict fake of the official `orca.host` surface
# --------------------------------------------------------------------------- #
# Every attribute path below exists in the official OrcaSlicer tag
# v2.5.0-alpha, commit 3880f2c58ec392ed2bd5938ab31c9c7c496c0eb2. The source is
# src/slic3r/plugin/host/<file> at that commit. A path that is not listed here
# does not exist in any official build: reading it raises AttributeError and
# assigning it raises AttributeError, so a test cannot invent a host API (this
# is how `orca.host.app_language` and `orca.host.reload_local_bundle` passed
# CI while not existing). Refresh the list from upstream and update the SHA
# together; never add a path only to make a test pass.
UPSTREAM_ORCA_SHA = "3880f2c58ec392ed2bd5938ab31c9c7c496c0eb2"

# Submodules: present on the fake by default, never reassigned.
HOST_SUBMODULES = {
    "plugin": 'PluginHost.cpp register_plugin: host.def_submodule("plugin")',
    "preset": 'PluginHostPresets.cpp register_presets: host.def_submodule("preset")',
    "preset.bundles": 'PluginHostPresets.cpp register_presets: preset.def_submodule("bundles")',
    "ui": 'PluginHostUi.cpp PluginHostUi::RegisterBindings: host.def_submodule("ui")',
}

# Leaves: callables, classes, enums and constants. Absent until a test sets one.
HOST_LEAVES = {
    # PluginHost.cpp
    "plugin.storage": 'PluginHost.cpp register_plugin: plugin_host.def("storage")',
    # PluginHostPresets.cpp
    "preset.bundles.reload_local": 'PluginHostPresets.cpp: bundles.def("reload_local")',
    "preset.bundles.list_ids": 'PluginHostPresets.cpp: bundles.def("list_ids")',
    "PresetType": "PluginHostPresets.cpp: py::enum_<Preset::Type>",
    "Preset": "PluginHostPresets.cpp: py::class_<Preset>",
    "PresetCollection": "PluginHostPresets.cpp: py::class_<PresetCollection>",
    "PresetBundle": "PluginHostPresets.cpp: py::class_<PresetBundle>",
    # PluginHostApp.cpp
    "Plater": "PluginHostApp.cpp register_app: py::class_<GUI::Plater>",
    "plater": 'PluginHostApp.cpp register_app: host.def("plater")',
    "model": 'PluginHostApp.cpp register_app: host.def("model")',
    "preset_bundle": 'PluginHostApp.cpp register_app: host.def("preset_bundle")',
    "app_info": 'PluginHostApp.cpp register_app: host.def("app_info"), UI thread only',
    "gl_info": 'PluginHostApp.cpp register_app: host.def("gl_info")',
    "selected_printer": 'PluginHostApp.cpp register_app: host.def("selected_printer")',
    # PluginHostGeometry.cpp
    "BoundingBox": "PluginHostGeometry.cpp: py::class_<BoundingBoxf3>",
    "Point": "PluginHostGeometry.cpp: py::class_<Point>",
    "Polygon": "PluginHostGeometry.cpp: py::class_<Polygon>",
    "ExPolygon": "PluginHostGeometry.cpp: py::class_<ExPolygon>",
    # PluginHostMesh.cpp
    "TriangleMesh": "PluginHostMesh.cpp: py::class_<TriangleMesh>",
    # PluginHostModel.cpp
    "ModelVolumeType": "PluginHostModel.cpp: py::enum_<ModelVolumeType>",
    "ModelVolume": "PluginHostModel.cpp: py::class_<ModelVolume>",
    "ModelInstance": "PluginHostModel.cpp: py::class_<ModelInstance>",
    "ModelObject": "PluginHostModel.cpp: py::class_<ModelObject>",
    "Model": "PluginHostModel.cpp: py::class_<Model>",
    # PluginHostSlicing.cpp
    "SurfaceType": "PluginHostSlicing.cpp: py::enum_<SurfaceType>",
    "Surface": "PluginHostSlicing.cpp: py::class_<Surface>",
    "SurfaceCollection": "PluginHostSlicing.cpp: py::class_<SurfaceCollection>",
    "ExtrusionEntity": "PluginHostSlicing.cpp: py::class_<ExtrusionEntity>",
    "ExtrusionPath": "PluginHostSlicing.cpp: py::class_<ExtrusionPath>",
    "ExtrusionLoop": "PluginHostSlicing.cpp: py::class_<ExtrusionLoop>",
    "ExtrusionMultiPath": "PluginHostSlicing.cpp: py::class_<ExtrusionMultiPath>",
    "ExtrusionEntityCollection": "PluginHostSlicing.cpp: py::class_<ExtrusionEntityCollection>",
    "PrintRegion": "PluginHostSlicing.cpp: py::class_<PrintRegion>",
    "LayerRegion": "PluginHostSlicing.cpp: py::class_<LayerRegion>",
    "Layer": "PluginHostSlicing.cpp: py::class_<Layer>",
    "PrintObject": "PluginHostSlicing.cpp: py::class_<PrintObject>",
    "Print": "PluginHostSlicing.cpp: py::class_<Print>",
    # PluginHostUi.cpp (ui submodule)
    "ui.message": 'PluginHostUi.cpp: ui.def("message")',
    "ui.create_window": 'PluginHostUi.cpp: ui.def("create_window"); on_message runs on the UI thread',
    "ui.create_dock_panel": 'PluginHostUi.cpp: ui.def("create_dock_panel")',
    "ui.create_progress_dialog": 'PluginHostUi.cpp: ui.def("create_progress_dialog")',
    "ui.push_notification": 'PluginHostUi.cpp: ui.def("push_notification")',
    "ui.UiWindow": 'PluginHostUi.cpp: py::class_<UiWindowHandle>(ui, "UiWindow")',
    "ui.UiDockPanel": 'PluginHostUi.cpp: py::class_<UiDockPanelHandle>(ui, "UiDockPanel")',
    "ui.ProgressDialog": 'PluginHostUi.cpp: py::class_<UiProgressHandle>(ui, "ProgressDialog")',
    "ui.NotificationLevel": "PluginHostUi.cpp: py::enum_<NotificationLevel>(ui, ...)",
    **{
        f"ui.{name}": f'PluginHostUi.cpp: ui.attr("{name}")'
        for name in (
            "PD_APP_MODAL", "PD_AUTO_HIDE", "PD_CAN_ABORT", "PD_CAN_SKIP",
            "PD_ELAPSED_TIME", "PD_ESTIMATED_TIME", "PD_REMAINING_TIME",
            "WINDOW_MODELESS", "WINDOW_MODAL",
        )
    },
}

class StrictHostNode:
    """An `orca.host` module node that only accepts attribute paths seen upstream."""

    def __init__(self, path=""):
        object.__setattr__(self, "_path", path)

    def _full(self, name):
        return f"{self._path}.{name}" if self._path else name

    def __setattr__(self, name, value):
        full = self._full(name)
        if full in HOST_SUBMODULES:
            raise AttributeError(
                f"orca.host.{full} is a submodule; set one of its leaves instead"
            )
        if full not in HOST_LEAVES:
            raise AttributeError(
                f"orca.host.{full} does not exist in official OrcaSlicer "
                f"{UPSTREAM_ORCA_SHA}"
            )
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name not in self.__dict__:
            raise AttributeError(f"orca.host.{self._full(name)} is not set")
        object.__delattr__(self, name)

    def __getattr__(self, name):
        # Only reached when normal lookup failed: the attribute is not set.
        raise AttributeError(f"orca.host.{self._full(name)} does not exist or is not set")

def make_strict_host():
    """Build `orca.host` with its submodules present and no callables set."""
    host = StrictHostNode()
    for path in sorted(HOST_SUBMODULES):
        *parents, leaf = path.split(".")
        node = host
        for part in parents:
            node = getattr(node, part)
        object.__setattr__(node, leaf, StrictHostNode(path))
    return host

def _host_leaf(host, path):
    *parents, leaf = path.split(".")
    node = host
    for part in parents:
        node = getattr(node, part)
    return node, leaf

def set_host_attr(monkeypatch, host, path, value):
    """Install `value` at a dotted leaf path of the strict host for one test."""
    if path not in HOST_LEAVES:
        raise AttributeError(
            f"orca.host.{path} does not exist in official OrcaSlicer {UPSTREAM_ORCA_SHA}"
        )
    node, leaf = _host_leaf(host, path)
    monkeypatch.setattr(node, leaf, value, raising=False)

def remove_host_attr(monkeypatch, host, path):
    """Make one dotted leaf path absent, as on a host that lacks that API."""
    node, leaf = _host_leaf(host, path)
    if leaf in node.__dict__:
        monkeypatch.delattr(node, leaf)
    else:
        assert path in HOST_LEAVES, path

def fake_app_info(language, *, strict_thread=True, **overrides):
    """`orca.host.app_info` as upstream returns it, UI thread only (PluginHostApp.cpp)."""
    def app_info():
        if strict_thread and threading.current_thread() is not threading.main_thread():
            raise RuntimeError("app_info() must be called from the UI thread")
        info = {
            "version": "2.5.0-alpha", "build": "", "mode": "editor",
            "language": language, "app_config_version": "", "stealth_mode": False,
            "is_signed_in": False, "is_bambu_signed_in": False,
            "network_plugin_version": "", "network_plugin_error": "",
        }
        info.update(overrides)
        return info
    return app_info

# Top-level `orca` enums (not `orca.host` leaves). Members and their order are
# those registered in PythonPluginBridge.cpp at the same upstream commit:
# py::enum_<LifecycleEvent> lines 389-423 and py::enum_<LifecycleEvtCode> lines
# 425-429, both with export_values().
LIFECYCLE_EVENT_NAMES = (
    "NewProject", "ProjectOpened", "ProjectBeforeSave", "ProjectAfterSave",
    "ProjectClosed", "ProjectDirtyChanged", "SliceStarted",
    "SliceGeometryFinished", "GCodeExportStarted", "GCodeExportFinished",
    "SlicingJobComplete", "ObjectAdded", "ObjectDeleted", "ObjectTransformed",
    "ObjectChanged", "ObjectRenamed", "PlateCreated", "PlateDeleted",
    "PlateSelected", "PlateRenamed", "PresetSelected", "PresetSaved",
    "PrintStateChanged", "DeviceOnline", "DeviceOffline", "DeviceDiscovered",
    "DeviceSelected", "UploadStarted", "UploadFinished", "PrintJobStarted",
    "PrintJobFinished", "SendJobStarted", "SendJobFinished",
)
LIFECYCLE_EVT_CODE_NAMES = ("Ok", "Error", "Warn")


def install_lifecycle_enums(fake_orca):
    """Expose `orca.LifecycleEvent` / `orca.LifecycleEvtCode` as the host does.

    PluginManager::dispatch_lifecycle_event (PluginManager.cpp) hands
    on_lifecycle_event a LifecycleEvent member and a LifecycleEventContext whose
    fields are read-only (PythonPluginBridge.cpp:441-451).
    """
    fake_orca.LifecycleEvent = Enum("LifecycleEvent", LIFECYCLE_EVENT_NAMES)
    fake_orca.LifecycleEvtCode = Enum("LifecycleEvtCode", LIFECYCLE_EVT_CODE_NAMES)


def lifecycle_context(orca_module, name="", msg="new"):
    """A LifecycleEventContext as PresetSaved delivers it (Preset.cpp save_current_preset)."""
    return SimpleNamespace(
        name=name, code=orca_module.LifecycleEvtCode.Ok, msg=msg, id="",
        previous_name="", device_id="", job_id="", source="", index=-1,
        dirty=False,
    )


class FakePresetCollection:
    """`PresetCollection.size()` / `.preset(i)` as bound in PluginHostPresets.cpp."""

    def __init__(self, *names):
        self._presets = [SimpleNamespace(name=name) for name in names]

    def size(self):
        return len(self._presets)

    def preset(self, index):
        return self._presets[index]


def fake_preset_bundle(filaments=(), prints=(), printers=()):
    """`orca.host.preset_bundle()` result with the three collections the plugin reads."""
    return SimpleNamespace(
        filaments=FakePresetCollection(*filaments),
        prints=FakePresetCollection(*prints),
        printers=FakePresetCollection(*printers),
    )


# Thread creation under OrcaSlicer 2.5.0-alpha (PluginAuditManager.cpp,
# report_denied): a refused `_thread.start_new_thread` audit event surfaces from
# Thread.start() as PermissionError("Plugin attempted audited operation ...").
AUDIT_THREAD_DENIAL = (
    'Plugin attempted audited operation "_thread.start_new_thread" without '
    "permission: audit permission required"
)


class ThreadAudit:
    """Fake of the host's thread permission for plugin-owned threads.

    Only threads the plugin names (its own prefix, Timer, ThreadPoolExecutor)
    are audited, so pytest's own threads are untouched. `allowed` is the user's
    answer: False raises PermissionError from start(), True lets it through.
    """

    PREFIXES = ("filamenthub", "ThreadPoolExecutor")

    def __init__(self, monkeypatch, allowed=False):
        self.allowed = allowed
        self.started = []
        self.denied = []
        real_start = threading.Thread.start
        audit = self

        def start(thread):
            if thread.name.startswith(audit.PREFIXES) and not audit.allowed:
                audit.denied.append(thread.name)
                raise PermissionError(AUDIT_THREAD_DENIAL)
            audit.started.append((
                thread.name,
                threading.current_thread() is threading.main_thread(),
            ))
            return real_start(thread)

        monkeypatch.setattr(threading.Thread, "start", start)


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
    fake_orca.host = make_strict_host()
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
    fake_orca.host = make_strict_host()
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

def _module_with_pages(
    native_lifecycle=False, lifecycle_events=False, slicing=False, pages=True
):
    """The plugin as it loads on the PR #14992 Pages artifact.

    `lifecycle_events` adds the top-level orca.LifecycleEvent enums and
    `slicing` the slicing pipeline base; `pages=False` leaves out the Pages base,
    as on a host that has lifecycle events but no Pages capability. The preset-saved event is resolved when
    the module loads, so a test cannot add either after the import.
    """
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
    if pages:
        fake_orca.pages = SimpleNamespace(PagesPluginCapabilityBase=PagesCapabilityBase)
    fake_orca.host = make_strict_host()
    fake_orca.ExecutionResult = SimpleNamespace(
        success=lambda message: message,
        skipped=lambda message: ("skipped", message),
    )
    if lifecycle_events:
        install_lifecycle_enums(fake_orca)
    if slicing:
        fake_orca.slicing = SimpleNamespace(
            SlicingPipelineCapabilityBase=object,
            Step=SimpleNamespace(psGCodePostProcess="psGCodePostProcess"),
        )
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
    """Index and cache in a scratch dir; temp-directory probing is forbidden."""
    monkeypatch.setattr(module, "_SLICE_INDEX_FILE", str(tmp_path / "slices.json"))
    monkeypatch.setattr(
        module, "_SLICE_REPORT_OUTBOX_FILE", str(tmp_path / "slice-reports.json")
    )
    monkeypatch.setattr(module, "_SLICE_CACHE_DIR", str(tmp_path / "cache"))
    def fail_if_probed():
        raise AssertionError("slice storage must not probe tempfile.gettempdir()")

    monkeypatch.setattr(module.tempfile, "gettempdir", fail_if_probed)

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
