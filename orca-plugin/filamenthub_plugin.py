# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub"
# name = "FilamentHub"
# description = "Browse and sync community-rated filament profiles from FilamentHub, with spool inventory and print-cost tools."
# author = "FilamentHub"
# version = "0.2.0"
#
# # Proposed forward-looking key (see README gap). The current
# # host reads only name/description/author/version/dependencies and ignores unknown
# # keys, so declaring this today is harmless and documents intent.
# network = ["filamenthub.ru", "*.filamenthub.ru", "filamenthub.club", "*.filamenthub.club"]
# ///
"""FilamentHub plugin for OrcaSlicer's Python plugin system.

Current Pages hosts receive a small bootstrap from ``get_ui`` and navigate the
top-level plugin WebView to the real React catalog. The catalog renders the
compact plugin toolbar and talks to Python through OrcaSlicer's official injected
``window.orca`` bridge. Every command carries a random per-tab binding and the
plugin never starts a local HTTP server. LAN addresses and credentials are
collected in a separate host-owned window with its own binding, so they never
enter the remote document. Older hosts use the same direct page in a managed
plugin window. Python syncs the authenticated exports into the user preset
folder and reports the result back to the page. A separate explicit
Recovery Center can restore selected managed machine and process profile copies;
they are never pulled automatically and never overwrite unmanaged or differently
scoped Orca profiles.

The React embed renders an Orca-themed toolbar (host --orca-* CSS variables,
same role as the native Catalog/Profile/Wiki buttons of the C++ fork panel) and
switches its own routes without an iframe. The catalog reports the signed-in
user (auth-state) for the toolbar label, and hands tokens over (auth-token) so
Python persists the scoped plugin capability in .auth.json next to the plugin.

External-browser OAuth: Google/Yandex refuse their consent pages inside an
embedded WebView, so the plugin creates a short-lived server handoff, opens its
HTTPS URL in the user's real browser and polls the matching one-shot HTTPS
endpoint. No local listener or browser callback to localhost is involved.

  React catalog
      --window.orca.postMessage({source:'filamenthub-plugin', bridgeSession,...})-->
          Python on_message
          --GET /presets/{id}/export/orcaslicer.json (Bearer token from the page)-->
              write {data_dir}/user/<active>/_local/filamenthub/filament/<name>.json
                  --> sync-result message shown by the page

Runtime surface used (confirmed against the current upstream plugin API):
  * orca.pages.PagesPluginCapabilityBase                    — native page
  * orca.script.ScriptPluginCapabilityBase.execute()        — old-host fallback
  * capability on_load/on_cancelled/on_unload hooks         — runtime lifecycle
  * orca.host.ui.create_window(...)                         — fallback UI/local dialogs
  * orca.host.plugin.storage(), app_language()              — private state/locale
  * the injected window.orca bridge (PluginWebDialog.cpp:ORCA_BRIDGE_JS)

Login/token: the user signs in inside the embedded page on our own site.
The page mints a short-lived, plugin-scoped capability for preset read/write
and reading an explicitly selected owned printer bundle;
the account access/refresh credentials never cross the plugin bridge. The
capability may be cached locally until expiry so a reopened window can resume.
"""

import csv
import ftplib
import io
import math
import posixpath
import zipfile
from xml.etree import ElementTree
import datetime
import hashlib
import hmac
import ipaddress
import json
import os
import platform
import queue
import random
import re
import secrets
import select
import shutil
import socket
import ssl
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import orca


class PluginLifecycleStopped(RuntimeError):
    """Abort a side effect from a worker generation retired by unload/reload."""


class ReusableDaemonWorker:
    """Run background jobs serially on one short-lived, reusable daemon thread.

    Orca's UI callback must stay responsive, but creating a fresh Python thread
    for every sync/import/result check produces unnecessary runtime events. The
    worker remains alive while the plugin is active and retires after an idle
    period, so reload/exit never waits for it.
    """

    def __init__(self, name, idle_timeout=60.0):
        self._name = name
        self._idle_timeout = idle_timeout
        self._jobs = queue.Queue()
        self._lock = threading.RLock()
        self._thread = None
        self._generation = 0
        self._stopping = False
        self._local = threading.local()

    def activate(self):
        """Accept work for a new plugin lifecycle generation."""
        with self._lock:
            if self._stopping:
                self._generation += 1
                self._stopping = False

    def current_job_is_active(self):
        """Whether the calling worker job still belongs to the loaded plugin."""
        generation = getattr(self._local, "generation", None)
        if generation is None:
            return True
        with self._lock:
            return not self._stopping and generation == self._generation

    def current_job_generation(self):
        return getattr(self._local, "generation", None)

    def authorize_external_operation(self):
        """Linearize one actual I/O start against lifecycle stop()."""
        generation = self.current_job_generation()
        if generation is None:
            return None
        with self._lock:
            if self._stopping or generation != self._generation:
                raise PluginLifecycleStopped(
                    "plugin lifecycle generation has stopped"
                )
            return generation

    def run_if_current(self, function, *args, **kwargs):
        """Authorize one host transition, then call it without holding the lock."""
        self.authorize_external_operation()
        return function(*args, **kwargs)

    def run_in_generation(self, generation, function, *args, **kwargs):
        """Propagate a parent job generation into a bounded helper thread."""
        if generation is None:
            return function(*args, **kwargs)
        marker = object()
        previous = getattr(self._local, "generation", marker)
        self._local.generation = generation
        try:
            return function(*args, **kwargs)
        finally:
            if previous is marker:
                try:
                    del self._local.generation
                except AttributeError:
                    pass
            else:
                self._local.generation = previous

    def current_job_has_side_effect_permit(self):
        generation = getattr(self._local, "generation", None)
        return (
            generation is not None
            and getattr(self._local, "side_effect_generation", None) == generation
            and getattr(self._local, "side_effect_depth", 0) > 0
        )

    def begin_side_effect_transaction(self):
        """Grant a running generation a narrow, nestable mutation transaction."""
        generation = getattr(self._local, "generation", None)
        if generation is None:
            return None
        if self.current_job_has_side_effect_permit():
            self._local.side_effect_depth += 1
            return generation
        with self._lock:
            if self._stopping or generation != self._generation:
                raise PluginLifecycleStopped(
                    "plugin lifecycle generation has stopped"
                )
            self._local.side_effect_generation = generation
            self._local.side_effect_depth = 1
        return generation

    def end_side_effect_transaction(self, generation):
        if generation is None:
            return
        if getattr(self._local, "side_effect_generation", None) != generation:
            return
        depth = getattr(self._local, "side_effect_depth", 0) - 1
        if depth > 0:
            self._local.side_effect_depth = depth
            return
        for name in ("side_effect_generation", "side_effect_depth"):
            try:
                delattr(self._local, name)
            except AttributeError:
                pass

    def submit(self, function, *args, **kwargs):
        with self._lock:
            if self._stopping:
                return False
            generation = self._generation
            self._jobs.put((generation, function, args, kwargs))
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run,
                    name=self._name,
                    daemon=True,
                )
                self._thread.start()
        return True

    def stop(self, wait_timeout=0.25):
        """Reject new work and discard jobs that have not started yet."""
        with self._lock:
            if not self._stopping:
                self._stopping = True
                self._generation += 1
            thread = self._thread
            while True:
                try:
                    self._jobs.get_nowait()
                except queue.Empty:
                    break
                else:
                    self._jobs.task_done()
            self._jobs.put(None)
        if (
            thread is not None
            and thread is not threading.current_thread()
            and wait_timeout > 0
        ):
            thread.join(wait_timeout)

    def shutdown(self, wait_timeout=0.25):
        """Backward-compatible alias for existing internal callers."""
        self.stop(wait_timeout=wait_timeout)

    def _run(self):
        current = threading.current_thread()
        while True:
            try:
                job = self._jobs.get(timeout=self._idle_timeout)
            except queue.Empty:
                with self._lock:
                    if self._jobs.empty():
                        if self._thread is current:
                            self._thread = None
                        return
                continue
            if job is None:
                self._jobs.task_done()
                with self._lock:
                    if self._stopping:
                        if self._thread is current:
                            self._thread = None
                        return
                continue
            generation, function, args, kwargs = job
            with self._lock:
                should_run = not self._stopping and generation == self._generation
            if not should_run:
                self._jobs.task_done()
                continue
            try:
                self._local.generation = generation
                function(*args, **kwargs)
            except PluginLifecycleStopped:
                pass
            except Exception as exc:
                logger = globals().get("fh_log")
                if logger is not None:
                    logger("background job failed: %s" % exc)
            finally:
                for name in (
                    "generation",
                    "side_effect_generation",
                    "side_effect_depth",
                ):
                    try:
                        delattr(self._local, name)
                    except AttributeError:
                        pass
                self._jobs.task_done()


BACKGROUND_WORKER = ReusableDaemonWorker("filamenthub-worker")
_BOUND_LIFECYCLE = threading.local()


@contextmanager
def bind_lifecycle_generation(authority, generation):
    """Bind a non-worker runtime generation to its own thread's I/O."""
    marker = object()
    previous = getattr(_BOUND_LIFECYCLE, "binding", marker)
    _BOUND_LIFECYCLE.binding = (authority, generation)
    try:
        yield
    finally:
        if previous is marker:
            try:
                del _BOUND_LIFECYCLE.binding
            except AttributeError:
                pass
        else:
            _BOUND_LIFECYCLE.binding = previous


def authorize_bound_lifecycle_operation():
    binding = getattr(_BOUND_LIFECYCLE, "binding", None)
    if binding is None:
        return
    authority, generation = binding
    authority.authorize_external_operation(generation)


def ensure_worker_generation_active():
    """Fail closed when an old worker generation reaches an I/O boundary.

    UI callbacks, the independent Bambu observer and other non-worker callers
    have no worker generation and remain unaffected. A job that outlived
    unload/reload raises before it can start another network, printer or
    persistent-state operation.
    """
    worker = globals().get("BACKGROUND_WORKER")
    is_active = getattr(worker, "current_job_is_active", None)
    if callable(is_active) and not is_active():
        raise PluginLifecycleStopped("plugin lifecycle generation has stopped")


@contextmanager
def external_operation():
    """Authorize exactly one I/O operation under the worker lifecycle lock."""
    worker = globals().get("BACKGROUND_WORKER")
    authorize = getattr(worker, "authorize_external_operation", None)
    if callable(authorize):
        authorize()
    else:
        ensure_worker_generation_active()
    authorize_bound_lifecycle_operation()
    yield


def ensure_side_effect_allowed():
    """Allow a local mutation only for an active or already-permitted job."""
    worker = globals().get("BACKGROUND_WORKER")
    has_permit = getattr(worker, "current_job_has_side_effect_permit", None)
    if not (callable(has_permit) and has_permit()):
        ensure_worker_generation_active()
    authorize_bound_lifecycle_operation()


@contextmanager
def side_effect_transaction():
    """Keep one already-authorized local mutation atomic across unload."""
    worker = globals().get("BACKGROUND_WORKER")
    generation = None
    begin = getattr(worker, "begin_side_effect_transaction", None)
    end = getattr(worker, "end_side_effect_transaction", None)
    if callable(begin):
        generation = begin()
    else:
        ensure_side_effect_allowed()
    try:
        authorize_bound_lifecycle_operation()
        yield
    finally:
        if callable(end):
            end(generation)


def post_window(window, payload):
    """Best-effort host push, safe against a window closing during a worker job."""
    worker = globals().get("BACKGROUND_WORKER")

    def push():
        post = getattr(window, "post", None)
        if window is None or not window.is_open() or not callable(post):
            return False
        post(payload)
        return True

    try:
        run_if_current = getattr(worker, "run_if_current", None)
        if callable(run_if_current):
            return run_if_current(push)
        ensure_worker_generation_active()
        return push()
    except PluginLifecycleStopped:
        return False
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
PLUGIN_VERSION = "0.2.0"
PLUGIN_CAPABILITIES = (
    "printer-bundle-install",
    "printer-bundle-result-v1",
    "printer-bundle-toggle-v1",
    "printer-recovery-v1",
    "bambu-lan-bridge",
    "profile-sync",
    "profile-sync-scopes-v1",
    "bambu-material-write",
    "happy-hare-moonraker",
    "material-assignment-v1",
    "material-observation-refresh-v1",
    "printer-setup-v1",
    "printer-discovery-v1",
    "open-external",
)
PROD_SITE_URL = "https://filamenthub.ru"
PROD_SITE_URLS = {"ru": PROD_SITE_URL, "club": "https://filamenthub.club"}
SITE_URL = os.environ.get("FILAMENTHUB_SITE_URL", "http://localhost:3000").rstrip("/")
DEV_CONTOUR = SITE_URL not in PROD_SITE_URLS.values()
EMBED_URL = SITE_URL + "/embed/catalog"
API_BASE = SITE_URL + "/api/v1"
PLUGIN_SETTINGS_DEFAULTS = {
    "server": "ru",
    "auto_sync": True,
    "sync_success_notice": True,
    "developer_mode": False,
}
_PLUGIN_SETTINGS = dict(PLUGIN_SETTINGS_DEFAULTS)
HTTP_TIMEOUT = 20
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_TOKEN_LENGTH = 8192
MAX_FILENAME_LENGTH = 120
MAX_MACHINE_BUNDLE_PROFILES = 32
MAX_PROCESS_BUNDLE_PROFILES = 200
SYNC_REPORT_CHUNK_SIZE = 500
SYNC_REPORT_CHUNK_RETRIES = 3
SYNC_REPORT_RETRY_SECONDS = 0.25
BAMBU_REVOKE_ATTEMPTS = 3
BAMBU_REVOKE_STATE_MAX_BYTES = 32 * 1024
BAMBU_REVOKE_MAX_PENDING = 16
BAMBU_REVOKE_BACKOFF_INITIAL_SECONDS = 60
BAMBU_REVOKE_BACKOFF_MAX_SECONDS = 6 * 60 * 60
_SSL_CTX = ssl.create_default_context()


def normalize_plugin_settings(raw):
    settings = dict(PLUGIN_SETTINGS_DEFAULTS)
    if not isinstance(raw, dict):
        return settings
    if raw.get("server") in PROD_SITE_URLS:
        settings["server"] = raw["server"]
    for key in ("auto_sync", "sync_success_notice", "developer_mode"):
        if isinstance(raw.get(key), bool):
            settings[key] = raw[key]
    return settings


def read_capability_settings(capability):
    """Read the settings Orca keeps for this capability; hosts without them get defaults."""
    get_config = getattr(capability, "get_config", None)
    if not callable(get_config):
        return dict(PLUGIN_SETTINGS_DEFAULTS)
    try:
        return normalize_plugin_settings(json.loads(get_config()))
    except Exception as exc:
        fh_log("plugin settings unreadable: %s" % exc)
        return dict(PLUGIN_SETTINGS_DEFAULTS)


def apply_plugin_settings(settings, apply_server=False):
    """Adopt new settings; the server switches only at load, before any page or request uses it."""
    global _PLUGIN_SETTINGS, SITE_URL, EMBED_URL, API_BASE
    _PLUGIN_SETTINGS = dict(settings)
    if apply_server and not DEV_CONTOUR and "FILAMENTHUB_SITE_URL" not in os.environ:
        SITE_URL = PROD_SITE_URLS[settings["server"]]
        EMBED_URL = SITE_URL + "/embed/catalog"
        API_BASE = SITE_URL + "/api/v1"


def plugin_setting(key):
    return _PLUGIN_SETTINGS.get(key, PLUGIN_SETTINGS_DEFAULTS[key])


def account_origin():
    """Both production domains front one service, so account-scoped state keeps one origin."""
    return PROD_SITE_URL if SITE_URL in PROD_SITE_URLS.values() else SITE_URL


def host_ui_language():
    """Return Orca's canonical UI locale, or defer to the WebView."""
    app_language = getattr(getattr(orca, "host", None), "app_language", None)
    if not callable(app_language):
        return ""
    try:
        language = app_language()
    except (AttributeError, RuntimeError):
        return ""
    return normalize_ui_language(language)


ORCA_UI_LOCALES = (
    "ca", "cs", "de", "en", "es", "eu", "fr", "hu", "it", "ja", "ko",
    "lt", "nl", "pl", "pt_BR", "ru", "sv", "th", "tr", "uk", "vi",
    "zh_CN", "zh_TW",
)
_CANONICAL_UI_LOCALES = {locale.lower(): locale for locale in ORCA_UI_LOCALES}
_UI_LOCALE_ALIASES = {
    "zh": "zh_CN",
    "zh_hans": "zh_CN",
    "zh_hans_cn": "zh_CN",
    "zh_hant": "zh_TW",
    "zh_hant_tw": "zh_TW",
}
# build_package.py replaces this empty mapping in release artifacts. Keeping the
# editable JSON files authoritative in the source tree makes community
# translations reviewable, while embedding them here keeps Orca's officially
# supported single-file plugin format fully functional.
_EMBEDDED_UI_COPY = {}
_LOCALE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "filamenthub_locales",
)


def normalize_ui_language(language):
    """Return Orca's canonical locale, preserving regional variants."""
    if not language:
        return ""
    token = str(language).strip().replace("-", "_")
    lowered = token.lower()
    alias = _UI_LOCALE_ALIASES.get(lowered)
    if alias:
        return alias
    exact = _CANONICAL_UI_LOCALES.get(lowered)
    if exact:
        return exact
    base = lowered.split("_", 1)[0]
    return _CANONICAL_UI_LOCALES.get(base, "en")


def load_ui_catalogs(directory=None):
    """Load bundled UTF-8 catalogs; invalid optional files cannot break startup."""
    root = directory or _LOCALE_DIR
    catalogs = {
        locale: dict(data)
        for locale, data in _EMBEDDED_UI_COPY.items()
        if locale in ORCA_UI_LOCALES and isinstance(data, dict)
    }
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    for name in names:
        if not name.endswith(".json"):
            continue
        locale = name[:-5]
        if locale not in ORCA_UI_LOCALES:
            continue
        try:
            with open(os.path.join(root, name), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in data.items()
        ):
            continue
        catalogs[locale] = data
    catalogs.setdefault("en", {})
    return catalogs


def resolved_ui_catalog(language):
    """Overlay exact and base catalogs on English for per-key fallback."""
    locale = normalize_ui_language(language) or "en"
    resolved = dict(UI_COPY.get("en", {}))
    base = locale.split("_", 1)[0]
    if base != "en":
        resolved.update(UI_COPY.get(base, {}))
    if locale not in {"en", base}:
        resolved.update(UI_COPY.get(locale, {}))
    return resolved


UI_COPY = load_ui_catalogs()

_CACHED_UI_LANGUAGE = ""


def refresh_ui_language():
    """Read the host on its UI thread and cache the result for worker messages."""
    global _CACHED_UI_LANGUAGE
    language = host_ui_language()
    if language:
        _CACHED_UI_LANGUAGE = language
    return language


def ui_text(key, **values):
    language = _CACHED_UI_LANGUAGE or "en"
    template = resolved_ui_catalog(language).get(key, key)
    return template.format(**values)


def localized_embed_url(language=None):
    language = host_ui_language() if language is None else language
    if not language:
        return EMBED_URL
    locale = normalize_ui_language(language)
    if locale == "ru":
        site_language = "ru"
    elif locale in {"zh_CN", "zh_TW"}:
        site_language = "zh"
    else:
        site_language = "en"
    separator = "&" if "?" in EMBED_URL else "?"
    return EMBED_URL + separator + urllib.parse.urlencode({"lng": site_language})


def open_in_system_browser(url):
    # Mirror how OrcaSlicer itself opens URLs: wxLaunchDefaultBrowser(), which
    # on Windows is ShellExecute("open", url). os.startfile is that same call
    # and works inside Orca's embedded Python, where webbrowser.open can report
    # success without actually launching anything. Fall back to webbrowser on
    # non-Windows or if startfile is unavailable/raises.
    try:
        startfile = getattr(os, "startfile", None)
        if startfile is not None:
            startfile(url)
            return True
        return bool(webbrowser.open(url))
    except Exception:
        try:
            return bool(webbrowser.open(url))
        except Exception:
            return False


def _temporary_path(path):
    return "%s.tmp.%d.%d" % (path, os.getpid(), threading.get_ident())


def _write_bytes_atomic_unchecked(path, payload, mode=None):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary = _temporary_path(path)
    try:
        with open(temporary, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            try:
                os.chmod(temporary, mode)
            except OSError:
                pass
        os.replace(temporary, path)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


def write_bytes_atomic(path, payload, mode=None):
    with side_effect_transaction():
        _write_bytes_atomic_unchecked(path, payload, mode=mode)


def write_json_atomic(path, payload, mode=None):
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    write_bytes_atomic(path, encoded, mode=mode)


def ensure_directory(path, mode=0o777):
    with side_effect_transaction():
        os.makedirs(path, mode=mode, exist_ok=True)


def _read_response_limited(response):
    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("FilamentHub response exceeds %d bytes" % MAX_RESPONSE_BYTES)
    return payload


# --------------------------------------------------------------------------- #
# Filesystem — resolve OrcaSlicer's data_dir from this file's location. Writes
# land under data_dir(), the one globally-allowed root during plugin execution
# (PluginAuditManager.cpp:install_hook).
# --------------------------------------------------------------------------- #
def resolve_data_dir():
    here = os.path.abspath(__file__).replace("\\", "/")
    parts = here.split("/")
    if "orca_plugins" in parts:
        return "/".join(parts[: parts.index("orca_plugins")])
    return os.path.dirname(os.path.dirname(here))


DATA_DIR = resolve_data_dir()


# Active user's preset folder under {data_dir}/user/<folder>/, derived from a
# user preset's file path via preset_bundle — the audit blocks OrcaSlicer.conf.
_user_preset_folder = None


def _preset_folder_from_file(preset_file):
    parts = os.path.normpath(preset_file or "").replace("\\", "/").split("/")
    if "user" in parts:
        idx = parts.index("user")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def refresh_user_preset_folder():
    """Resolve and cache the folder. UI thread only (reads preset_bundle)."""
    global _user_preset_folder
    try:
        bundle = orca.host.preset_bundle()
        for collection in (bundle.filaments, bundle.printers, bundle.prints):
            for i in range(collection.size()):
                preset = collection.preset(i)
                if preset.is_user():
                    folder = _preset_folder_from_file(preset.file)
                    if folder:
                        _user_preset_folder = folder
                        return folder
    except Exception:
        pass
    return _user_preset_folder


def resolve_user_preset_folder():
    """Use the folder observed from the live host, otherwise Orca's default.

    An old signed-in account directory may remain as the only non-default
    directory after Orca switches back to its ``default`` preset folder. Using
    that stale directory makes a successful sync write files into a bundle the
    running host never loads.
    """
    if _user_preset_folder:
        return _user_preset_folder
    return "default"


BUNDLE_ID = "filamenthub"
BUNDLE_NAME = "FilamentHub"


def user_bundle_dir():
    # {data_dir}/user/<active-user>/_local/filamenthub/ — a registered "local
    # bundle". The slicer groups a preset in the dropdown by the bundle it belongs
    # to, and membership comes from this directory layout, not from any JSON field:
    # a bundle is a folder under _local/ that holds bundle_metadata.json plus a
    # filament/ subfolder (PresetBundle.cpp bundle loading). Presets written here
    # show under the "FilamentHub" group instead of "User presets".
    return os.path.join(DATA_DIR, "user", resolve_user_preset_folder(), "_local", BUNDLE_ID)


def profile_identity_registry_path():
    """Plugin-owned identity state, outside Orca's preset file collections."""
    return os.path.join(
        DATA_DIR,
        "user",
        resolve_user_preset_folder(),
        ".filamenthub",
        "profile_identity.json",
    )


def user_filament_dir():
    return os.path.join(user_bundle_dir(), "filament")


def user_machine_dir():
    return os.path.join(user_bundle_dir(), "machine")


def user_process_dir():
    return os.path.join(user_bundle_dir(), "process")


def ensure_bundle_metadata():
    # bundle_metadata.json registers _local/filamenthub/ as a bundle named
    # "FilamentHub"; without it the loader skips the folder entirely.
    bundle_dir = user_bundle_dir()
    meta_path = os.path.join(bundle_dir, "bundle_metadata.json")
    try:
        if not os.path.exists(meta_path):
            write_json_atomic(
                meta_path,
                {
                    "id": BUNDLE_ID,
                    "name": BUNDLE_NAME,
                    "version": "1.0.0",
                    "description": "FilamentHub community presets",
                    "author": "FilamentHub",
                },
            )
    except OSError:
        pass


def reload_managed_local_bundle_if_available():
    """Make the completed FilamentHub bundle live when the host supports it."""
    reload_bundle = getattr(
        getattr(orca, "host", None), "reload_local_bundle", None
    )
    if not callable(reload_bundle):
        return False
    def reload_bundle_now():
        try:
            reload_bundle(BUNDLE_ID)
        except Exception as exc:
            fh_log("managed local-bundle reload failed: %s" % type(exc).__name__)
            return False
        fh_log("managed local bundle reloaded")
        return True

    worker = globals().get("BACKGROUND_WORKER")
    run_if_current = getattr(worker, "run_if_current", None)
    try:
        if callable(run_if_current):
            return run_if_current(reload_bundle_now)
        ensure_worker_generation_active()
        return reload_bundle_now()
    except PluginLifecycleStopped:
        return False


def resolve_plugin_dir():
    """The plugin's install dir (orca_plugins/<name>), stable across package
    formats. A wheel runs from __whl_extracted__/<pkg>/ INSIDE the install dir
    and that cache is wiped on update.  This path is used to find legacy state;
    configure_plugin_storage() moves mutable files outside the replaceable
    install directory before normal plugin work starts."""
    here = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
    parts = here.split("/")
    if "__whl_extracted__" in parts:
        return "/".join(parts[: parts.index("__whl_extracted__")])
    return here


PLUGIN_DIR = resolve_plugin_dir()
PLUGIN_STORAGE_DIR = PLUGIN_DIR
# Use a packaged adjacent icon when one exists. A wheel/single-file install falls
# back to Orca's default instead of writing an asset during normal plugin load.
ICON_PATH = os.path.join(PLUGIN_DIR, "filamenthub.svg")
PACKAGED_ICON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "filamenthub.svg",
)
_ICON_SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20" stroke-width="1.25"><path d="M8.19,2.15c-3.11.84-5.49,3.22-6.15,6.18-.7,3.16.86,5.68,1.21,6.21" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-miterlimit:10"/><line x1="8.19" y1="10" x2="1.87" y2="10" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-miterlimit:10"/><line x1="10.95" y1="2.15" x2="10.95" y2="17.85" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-miterlimit:10"/><path d="M16.91,6c.37.65,1.08,2.08,1.09,4.01.02,2.28-.94,3.92-1.35,4.54" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-miterlimit:10"/><line x1="10.95" y1="10" x2="18" y2="10" style="fill:none;stroke:#fff;stroke-miterlimit:10"/></svg>'''


def ensure_icon():
    for candidate in (PACKAGED_ICON_PATH, ICON_PATH):
        if os.path.isfile(candidate):
            return candidate
    target = os.path.join(PLUGIN_STORAGE_DIR, "filamenthub.svg")
    try:
        write_bytes_atomic(target, _ICON_SVG)
    except OSError:
        return ""
    return target if os.path.isfile(target) else ""


def fallback_plugin_storage_dir():
    """Stable data root for hosts that do not expose private plugin storage.

    Orca replaces ``orca_plugins/<plugin>`` during an update, so mutable state
    must not remain inside that install directory.  Current plugin-capable
    builds keep it directly below the Orca data root instead.  An unfamiliar
    layout deliberately has no fallback: writing outside a known data root
    would be a worse failure than asking the user to reconnect.
    """
    plugins_root = os.path.dirname(os.path.abspath(PLUGIN_DIR))
    if os.path.basename(plugins_root).lower() != "orca_plugins":
        return ""
    data_root = os.path.dirname(plugins_root)
    return os.path.join(data_root, ".filamenthub", "orca-plugin")


def configure_plugin_storage():
    """Use durable private storage without depending on a particular host API.

    Prefer ``orca.host.plugin.storage()`` when the host exposes it, with a
    stable directory outside the replaceable plugin package for compatible
    older hosts.  Existing sidecar state is copied once and retained as a
    rollback fallback.
    """
    global PLUGIN_STORAGE_DIR
    global SYNC_LOG_FILE, AUTH_FILE, BAMBU_CONFIG_FILE, BAMBU_REVOKE_FILE
    global IMPORTED_DRAFTS_FILE, SYNC_STATE_FILE
    global PRINTER_BUNDLE_STATE_FILE
    global _SLICE_INDEX_FILE, _SLICE_REPORT_OUTBOX_FILE, _SLICE_CACHE_DIR

    fallback_root = fallback_plugin_storage_dir()
    target_root = ""
    plugin_host = getattr(getattr(orca, "host", None), "plugin", None)
    storage = getattr(plugin_host, "storage", None)
    if callable(storage):
        try:
            target_root = os.path.abspath(storage())
        except (OSError, RuntimeError, TypeError, ValueError):
            target_root = ""
    if not target_root:
        target_root = fallback_root
    if not target_root:
        return False
    try:
        os.makedirs(target_root, mode=0o700, exist_ok=True)
        try:
            os.chmod(target_root, 0o700)
        except OSError:
            pass
    except OSError:
        return False

    file_names = (
        ".fh_sync.log",
        ".auth.json",
        ".fh_imported.json",
        ".fh_sync.json",
        ".fh_slices.json",
        ".fh_slice_reports.json",
        ".fh_bambu.json",
        ".fh_bambu_revoke.json",
        ".fh_printer_bundles.json",
    )
    source_roots = []
    for candidate in (fallback_root, PLUGIN_DIR):
        if candidate and os.path.abspath(candidate) != os.path.abspath(target_root):
            source_roots.append(candidate)
    for name in file_names:
        target = os.path.join(target_root, name)
        if os.path.exists(target):
            continue
        for source_root in source_roots:
            source = os.path.join(source_root, name)
            if not os.path.isfile(source):
                continue
            try:
                shutil.copy2(source, target)
            except OSError:
                pass
            break

    target_cache = os.path.join(target_root, "slices")
    if not os.path.exists(target_cache):
        for source_root in source_roots:
            legacy_cache = os.path.join(source_root, "slices")
            if not os.path.isdir(legacy_cache):
                continue
            try:
                shutil.copytree(legacy_cache, target_cache)
            except OSError:
                pass
            break

    PLUGIN_STORAGE_DIR = target_root
    SYNC_LOG_FILE = os.path.join(target_root, ".fh_sync.log")
    AUTH_FILE = os.path.join(target_root, ".auth.json")
    BAMBU_CONFIG_FILE = os.path.join(target_root, ".fh_bambu.json")
    BAMBU_REVOKE_FILE = os.path.join(target_root, ".fh_bambu_revoke.json")
    IMPORTED_DRAFTS_FILE = os.path.join(target_root, ".fh_imported.json")
    SYNC_STATE_FILE = os.path.join(target_root, ".fh_sync.json")
    PRINTER_BUNDLE_STATE_FILE = os.path.join(target_root, ".fh_printer_bundles.json")
    _SLICE_INDEX_FILE = os.path.join(target_root, ".fh_slices.json")
    _SLICE_REPORT_OUTBOX_FILE = os.path.join(target_root, ".fh_slice_reports.json")
    _SLICE_CACHE_DIR = target_cache
    return True


SYNC_LOG_FILE = os.path.join(PLUGIN_DIR, ".fh_sync.log")
SYNC_LOG_MAX_BYTES = 256 * 1024
SYNC_LOG_KEEP_BYTES = 128 * 1024


def redact_home(text):
    """Replace the user's home directory with ~ so a shared log carries no name."""
    home = os.path.expanduser("~")
    if not home or home == "~":
        return text
    return text.replace(home, "~").replace(home.replace("\\", "/"), "~")


def trim_sync_log():
    """Keep only the tail once the log grows past its cap."""
    try:
        if os.path.getsize(SYNC_LOG_FILE) <= SYNC_LOG_MAX_BYTES:
            return
        with open(SYNC_LOG_FILE, "rb") as fh:
            fh.seek(-SYNC_LOG_KEEP_BYTES, os.SEEK_END)
            tail = fh.read()
        write_bytes_atomic(SYNC_LOG_FILE, tail)
    except OSError:
        pass


def fh_log(msg):
    """Append one timestamped diagnostic line. Best-effort, never raises."""
    try:
        with side_effect_transaction():
            import datetime
            trim_sync_log()
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(SYNC_LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write("%s %s\n" % (stamp, redact_home(str(msg))))
    except (OSError, PluginLifecycleStopped):
        pass


def read_sync_log():
    """The log as text, empty when nothing has been written yet."""
    try:
        with open(SYNC_LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


DIAGNOSTIC_REPORT_MAX_BYTES = 64 * 1024
# The log is written without credentials; these are a second line of defence
# for anything an exception message might have carried into it.
_DIAGNOSTIC_SECRET_PATTERNS = (
    (re.compile(r"(?i)\bbearer\s+\S+"), "Bearer [redacted]"),
    (re.compile(r"\bfhpb_[A-Za-z0-9_-]+"), "fhpb_[redacted]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"), "[redacted]"),
    (
        re.compile(
            r"(?i)\b(access[_ -]?code|api[_-]?key|password|passwd|secret|token)"
            r"(\s*[=:]\s*)[^\s,;]+"
        ),
        r"\1\2[redacted]",
    ),
)
_DIAGNOSTIC_UNSAFE_CHARACTERS = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f‎‏‪-‮⁦-⁩]"
)


def diagnostic_report_text():
    """The newest part of the log, prepared for a user-sent problem report."""
    header = "FilamentHub plugin %s\nPython %s\nOS %s\nLanguage %s\n\n" % (
        PLUGIN_VERSION,
        platform.python_version(),
        platform.platform(terse=True),
        _CACHED_UI_LANGUAGE or "en",
    )
    text = redact_home(read_sync_log()).replace("\r\n", "\n")
    for pattern, replacement in _DIAGNOSTIC_SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    text = _DIAGNOSTIC_UNSAFE_CHARACTERS.sub("", text)
    budget = DIAGNOSTIC_REPORT_MAX_BYTES - len(header.encode("utf-8"))
    encoded = text.encode("utf-8")
    if len(encoded) > budget:
        tail = encoded[-budget:].decode("utf-8", errors="ignore")
        text = tail.split("\n", 1)[1] if "\n" in tail else tail
    return header + text


# These are import-time legacy locations. configure_plugin_storage() redirects
# them to durable private storage during capability registration. The page's
# own storage is partitioned and dies with the window.
AUTH_FILE = os.path.join(PLUGIN_DIR, ".auth.json")
BAMBU_CONFIG_FILE = os.path.join(PLUGIN_DIR, ".fh_bambu.json")
BAMBU_REVOKE_FILE = os.path.join(PLUGIN_DIR, ".fh_bambu_revoke.json")
PRINTER_BUNDLE_STATE_FILE = os.path.join(PLUGIN_DIR, ".fh_printer_bundles.json")


def load_saved_auth():
    if not os.path.isfile(AUTH_FILE):
        return None
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get("accessToken"):
            return {"accessToken": data["accessToken"], "refreshToken": ""}
    except (OSError, ValueError):
        pass
    return None


def save_auth(access_token, _refresh_token=""):
    if not isinstance(access_token, str) or not (0 < len(access_token) <= MAX_TOKEN_LENGTH):
        return False
    try:
        write_json_atomic(AUTH_FILE, {"accessToken": access_token}, mode=0o600)
        return True
    except OSError:
        return False


def clear_auth():
    with side_effect_transaction():
        try:
            os.remove(AUTH_FILE)
        except OSError:
            pass


def clear_auth_if_current(rejected_token):
    """Forget a rejected capability unless the page has already saved a newer one."""
    saved = (load_saved_auth() or {}).get("accessToken") or ""
    if saved and rejected_token and secrets.compare_digest(saved, rejected_token):
        clear_auth()


def safe_filename(name):
    cleaned = "".join(
        "_" if ch in '<>[]:"/\\|?*' or ord(ch) < 32 else ch
        for ch in (name or "preset")
    ).strip(" ._")
    cleaned = cleaned[:MAX_FILENAME_LENGTH].rstrip(" ._") or "preset"
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update("COM%d" % index for index in range(1, 10))
    reserved.update("LPT%d" % index for index in range(1, 10))
    if cleaned.split(".", 1)[0].upper() in reserved:
        cleaned = "_" + cleaned
    return cleaned


def preset_id_from_sync_info(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.startswith("filamenthub:preset:"):
        tail = value[len("filamenthub:preset:"):]
        return int(tail) if tail.isdigit() else None
    if value.startswith("fhub:") and value.endswith(":filamenthub"):
        tail = value[len("fhub:"):-len(":filamenthub")]
        return int(tail) if tail.isdigit() else None
    return None


def preset_id_from_info_content(content):
    if not isinstance(content, str):
        return None
    for line in content.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "sync_info":
            return preset_id_from_sync_info(value)
    return None


def preset_version_id_from_info_content(content):
    if not isinstance(content, str):
        return None
    for line in content.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "fhub_version_id":
            normalized = value.strip()
            return int(normalized) if normalized.isdigit() else None
    return None


def preset_id_from_info_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return preset_id_from_info_content(fh.read())
    except OSError:
        pass
    return None


def preset_version_id_from_info_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return preset_version_id_from_info_content(fh.read())
    except OSError:
        return None


def managed_info_bytes(preset_id, version_id=None):
    content = "sync_info = filamenthub:preset:%d\n" % preset_id
    if isinstance(version_id, int) and version_id > 0:
        content += "fhub_version_id = %d\n" % version_id
    return content.encode("utf-8")


def write_managed_info(base, preset_id, token, version_id=None):
    """Persist durable identity even if the optional server .info is unavailable."""
    target = base + ".info"
    write_bytes_atomic(target, managed_info_bytes(preset_id, version_id))
    try:
        status, info = http_get(
            "/presets/%d/export/orcaslicer.info" % preset_id,
            token=token,
        )
        if status != 200:
            return
        decoded = info.decode("utf-8")
        if preset_id_from_info_content(decoded) == preset_id:
            lines = [
                line for line in decoded.splitlines()
                if not line.strip().startswith("fhub_version_id")
            ]
            if isinstance(version_id, int) and version_id > 0:
                lines.append("fhub_version_id = %d" % version_id)
            write_bytes_atomic(target, ("\n".join(lines) + "\n").encode("utf-8"))
    except (OSError, UnicodeDecodeError):
        pass


def managed_preset_id(json_path, profile):
    pid = preset_id_from_bundle(profile.get("bundle_id")) if isinstance(profile, dict) else None
    if pid is not None:
        return pid
    return preset_id_from_info_file(json_path[:-len(".json")] + ".info")


def _managed_info_claim(path):
    """Return (is_filamenthub_owned, preset_id) for one Orca .info file."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return False, None
    for line in content.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key.strip() != "sync_info":
            continue
        value = value.strip()
        claimed = (
            value.startswith("filamenthub:preset:")
            or value.startswith("fhub:") and value.endswith(":filamenthub")
        )
        return claimed, preset_id_from_sync_info(value)
    return False, None


def preset_file_stems(folder):
    """Preset names in a folder: a preset is a .json plus an optional .info."""
    try:
        names = os.listdir(folder)
    except OSError:
        return set()
    return {
        name[:-len(extension)]
        for name in names
        for extension in (".json", ".info")
        if name.endswith(extension)
    }


def scan_managed_preset_artifacts(folder):
    """Inventory every strongly marked FilamentHub material artifact.

    Unlike ``scan_local_fh_presets``, this also sees orphan ``.info`` markers,
    malformed managed JSON and conflicting markers. Those cannot be used as a
    sync source, but they are still safe to remove from Orca's live bundle.
    """
    stems = preset_file_stems(folder)
    artifacts = []
    for stem in sorted(stems, key=str.casefold):
        json_path = os.path.join(folder, stem + ".json")
        info_path = os.path.join(folder, stem + ".info")
        profile = None
        bundle_claimed = False
        bundle_id = None
        if os.path.isfile(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as fh:
                    decoded = json.load(fh)
                if isinstance(decoded, dict):
                    profile = decoded
                    bundle_value = decoded.get("bundle_id")
                    bundle_claimed = (
                        isinstance(bundle_value, str)
                        and bundle_value.startswith("filamenthub:")
                    )
                    bundle_id = preset_id_from_bundle(bundle_value)
            except (OSError, ValueError):
                pass
        info_claimed, info_id = _managed_info_claim(info_path)
        claimed_ids = {value for value in (bundle_id, info_id) if value is not None}
        managed = bundle_claimed or info_claimed
        if not managed:
            continue
        markers_valid = (
            (not bundle_claimed or bundle_id is not None)
            and (not info_claimed or info_id is not None)
        )
        preset_id = next(iter(claimed_ids)) if len(claimed_ids) == 1 else None
        artifacts.append({
            "json_path": json_path if os.path.isfile(json_path) else None,
            "info_path": info_path if os.path.isfile(info_path) else None,
            "profile": profile,
            "preset_id": preset_id,
            "claimed_ids": claimed_ids,
            "healthy": (
                profile is not None
                and preset_id is not None
                and len(claimed_ids) == 1
                and markers_valid
            ),
        })
    return artifacts


def managed_preset_quarantine_dir():
    return os.path.join(
        os.path.dirname(profile_identity_registry_path()),
        "removed-presets",
    )


def _artifact_stems(artifact):
    return {
        os.path.basename(path)[:-len(extension)]
        for path, extension in (
            (artifact.get("json_path"), ".json"),
            (artifact.get("info_path"), ".info"),
        )
        if path
    }


def _quarantine_managed_preset_artifact(artifact, reason):
    with side_effect_transaction():
        return _quarantine_managed_preset_artifact_transaction(artifact, reason)


def _quarantine_managed_preset_artifact_transaction(artifact, reason):
    paths = [
        path for path in (artifact.get("json_path"), artifact.get("info_path"))
        if path and os.path.isfile(path)
    ]
    if not paths:
        return False
    batch = os.path.join(
        managed_preset_quarantine_dir(),
        "%s-%s-%s" % (
            time.strftime("%Y%m%d-%H%M%S"),
            safe_filename(reason),
            secrets.token_hex(4),
        ),
    )
    try:
        os.makedirs(batch, mode=0o700, exist_ok=False)
    except OSError as exc:
        fh_log("managed preset quarantine unavailable: %r" % exc)
        return False
    moved = []
    for source in paths:
        target = os.path.join(batch, os.path.basename(source))
        try:
            os.replace(source, target)
        except OSError as exc:
            fh_log("managed preset quarantine move failed: %r" % exc)
            for original, quarantined in reversed(moved):
                try:
                    os.replace(quarantined, original)
                except OSError as rollback_exc:
                    fh_log("managed preset quarantine rollback failed: %r" % rollback_exc)
            return False
        else:
            moved.append((source, target))
    fh_log("managed preset quarantined: reason=%s files=%d" % (reason, len(moved)))
    return len(moved) == len(paths)


def is_orca_transportable_value(value):
    """Whether ConfigBase::load_from_json can read this JSON value.

    Upstream accepts a string, or an array whose elements are all strings or all
    arrays (recursively) — parse_str_arr rejects a mixed-type array and any
    element that is neither string nor array.
    """
    if isinstance(value, str):
        return True
    if not isinstance(value, list):
        return False
    kinds = set("list" if isinstance(item, list) else type(item).__name__ for item in value)
    if len(kinds) > 1:
        return False
    return all(is_orca_transportable_value(item) for item in value)


def orca_transport_violations(profile):
    """Keys whose JSON value OrcaSlicer's config loader refuses.

    Orca reads the object in sorted key order. A bad array logs "invalid json
    array for <key>" and breaks the loop, silently dropping every
    alphabetically later key — name and type included — while still reporting
    success; a bad scalar type drops only that option. Either way the user sees
    a missing or quietly wrong preset, so the payload is checked again here
    before anything is written over a working file.
    """
    return sorted(
        key
        for key, value in profile.items()
        if not is_orca_transportable_value(value)
    )


def validate_filament_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError("Preset export must be a JSON object")
    name = profile.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise ValueError("Preset name must be a non-empty string")
    rejected = orca_transport_violations(profile)
    if rejected:
        raise ValueError(
            "OrcaSlicer cannot load these values: %s" % ", ".join(rejected))
    return profile


def _parent_name(profile):
    inherits = profile.get("inherits") if isinstance(profile, dict) else None
    if isinstance(inherits, list):
        inherits = inherits[0] if inherits else ""
    return inherits.strip() if isinstance(inherits, str) else ""


def _is_internal_fdm_parent(name):
    """Whether an Orca parent is a vendor-bundle implementation detail.

    Names beginning with ``fdm_`` are abstract/intermediate presets resolved only
    while Orca loads the vendor bundle that declares them. They are not present in
    the global user-preset collection, so a profile copied into our local bundle
    cannot inherit one even when another vendor contains the same name.
    """
    return isinstance(name, str) and name.startswith("fdm_")


def normalize_local_bundle_parent(profile, known_presets=None):
    """Keep only a parent that Orca can resolve from a local user bundle.

    A missing parent is valid: Orca starts from the type's default configuration
    and applies the profile overrides. ``known_presets`` is supplied for filament
    imports, where the host exposes the concrete installed preset names.
    """
    inherits = _parent_name(profile)
    unavailable = known_presets is not None and inherits not in known_presets
    if not inherits or _is_internal_fdm_parent(inherits) or unavailable:
        return profile.pop("inherits", None) is not None
    profile["inherits"] = inherits
    return False


FILAMENT_DISPLAY_SEPARATOR = " • "


def _filament_profile_text(profile, key):
    value = profile.get(key) if isinstance(profile, dict) else None
    if isinstance(value, list):
        value = value[0] if value else ""
    return value.strip() if isinstance(value, str) else ""


def _filament_material_type(profile):
    return _filament_profile_text(profile, "filament_type")


def _filament_brand(profile):
    return _filament_profile_text(profile, "filament_vendor")


def _filament_display_prefixes(profile):
    material_type = _filament_material_type(profile)
    brand = _filament_brand(profile)
    current_parts = [part for part in (material_type, brand) if part]
    prefixes = []
    if current_parts:
        prefixes.append(FILAMENT_DISPLAY_SEPARATOR.join(current_parts) + FILAMENT_DISPLAY_SEPARATOR)
    if material_type:
        legacy = material_type + FILAMENT_DISPLAY_SEPARATOR
        if legacy not in prefixes:
            prefixes.append(legacy)
    return prefixes


def filament_display_name(profile, source_name=None):
    """Return ``Type • Brand • Name`` without changing server identity."""
    name = source_name
    if not isinstance(name, str) or not name.strip():
        name = profile.get("name") if isinstance(profile, dict) else ""
    name = name.strip() if isinstance(name, str) else ""
    name = filament_source_name(profile, name)
    parts = [
        part
        for part in (_filament_material_type(profile), _filament_brand(profile), name)
        if part
    ]
    if not parts:
        return name
    return FILAMENT_DISPLAY_SEPARATOR.join(parts)


def filament_source_name(profile, display_name=None):
    """Remove only current/legacy automatic prefixes before an FH upload."""
    name = display_name
    if not isinstance(name, str) or not name.strip():
        name = profile.get("name") if isinstance(profile, dict) else ""
    name = name.strip() if isinstance(name, str) else ""
    for prefix in _filament_display_prefixes(profile):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _legacy_material_display_name(profile, source_name):
    name = filament_source_name(profile, source_name)
    material_type = _filament_material_type(profile)
    return (
        material_type + FILAMENT_DISPLAY_SEPARATOR + name
        if material_type and name
        else name
    )


def preset_file_path(folder, name, preset_id):
    """Path for a managed preset file. OrcaSlicer displays user presets by the
    file stem, so the stem must be the clean preset name; identity lives in the
    bundle_id inside the JSON. If the name is already taken by a file we don't
    own (the user's own preset, or another FilamentHub id), disambiguate with a
    short stable suffix instead of overwriting it."""
    stem = safe_filename(name) or ("FilamentHub preset %d" % int(preset_id))
    candidate = os.path.join(folder, stem + ".json")
    if not os.path.exists(candidate):
        return candidate
    try:
        with open(candidate, "r", encoding="utf-8") as fh:
            existing = json.load(fh)
        if isinstance(existing, dict) and managed_preset_id(candidate, existing) == int(preset_id):
            return candidate
    except (OSError, ValueError):
        pass
    return os.path.join(folder, "%s (FH-%d).json" % (stem, int(preset_id)))


def apply_managed_filename_identity(profile, path):
    """Keep Orca's JSON identity aligned with the filesystem-safe display stem."""
    name = os.path.basename(path)[:-len(".json")]
    profile["name"] = name
    profile["filament_settings_id"] = [name]
    return name


def remove_stale_preset_files(folder, preset_id, keep_path):
    """Move aside other files carrying this preset's managed identity — the old
    `__fh_<id>`-suffixed naming and leftovers from a rename on FilamentHub —
    so one preset never shows up twice in the dropdown. Touches only files
    whose bundle_id or .info sync marker we own. Quarantine keeps cleanup
    recoverable without leaving the broken copy in Orca's live preset folder."""
    ensure_side_effect_allowed()
    keep = os.path.normcase(os.path.abspath(keep_path))
    removed = 0
    for artifact in scan_managed_preset_artifacts(folder):
        path = artifact.get("json_path")
        if path and os.path.normcase(os.path.abspath(path)) == keep:
            continue
        if (
            artifact.get("preset_id") != int(preset_id)
            and int(preset_id) not in artifact.get("claimed_ids", set())
        ):
            continue
        ensure_side_effect_allowed()
        if _quarantine_managed_preset_artifact(artifact, "duplicate-%d" % int(preset_id)):
            removed += 1
    return removed


def rename_managed_preset_artifact(source, target, info_payload):
    """Atomically start a managed rename and finish its paired identity write."""
    with side_effect_transaction():
        try:
            os.replace(source, target)
        except OSError:
            return False
        try:
            write_bytes_atomic(target[:-len(".json")] + ".info", info_payload)
        except OSError:
            pass
        return True


def migrate_managed_filament_display_name(folder, preset_id, local_entry, remote):
    """Rename an untouched managed preset to ``Type • Brand • Name``.

    Bare server names and the earlier ``Type • Name`` labels are recognized.
    A name edited by the user in Orca remains a local change and follows the
    normal push path.
    """
    profile = local_entry.get("profile") if isinstance(local_entry, dict) else None
    path = local_entry.get("path") if isinstance(local_entry, dict) else None
    remote_name = (remote or {}).get("name")
    if not isinstance(profile, dict) or not path or not isinstance(remote_name, str):
        return False
    remote_name = remote_name.strip()
    if not remote_name or not _filament_material_type(profile):
        return False

    legacy_names = set()
    for candidate in (
        safe_filename(remote_name),
        safe_filename(_legacy_material_display_name(profile, remote_name)),
    ):
        if not candidate:
            continue
        legacy_names.add(candidate)
        legacy_names.add("%s (FH-%d)" % (candidate, int(preset_id)))
    current_name = str(profile.get("name") or "")
    current_stem = os.path.basename(path)[:-len(".json")]
    if current_name not in legacy_names or current_stem not in legacy_names:
        return False

    target = preset_file_path(
        folder,
        filament_display_name(profile, remote_name),
        preset_id,
    )
    if os.path.normcase(os.path.abspath(target)) == os.path.normcase(os.path.abspath(path)):
        return False

    with side_effect_transaction():
        migrated_profile = dict(profile)
        name = apply_managed_filename_identity(migrated_profile, target)
        validate_filament_profile(migrated_profile)
        write_json_atomic(target, migrated_profile)
        write_bytes_atomic(
            target[:-len(".json")] + ".info",
            managed_info_bytes(preset_id, local_entry.get("version_id")),
        )
        remove_stale_preset_files(folder, preset_id, target)
        local_entry.update({
            "path": target,
            "profile": migrated_profile,
            "hash": preset_content_hash(migrated_profile),
        })
    return name


def quarantine_unwanted_managed_preset_files(folder, remote_ids):
    """Remove FilamentHub-owned artifacts absent from authoritative desired state.

    State-cache membership is deliberately irrelevant: old plugin versions and
    interrupted writes can lose that cache while leaving durable ownership in
    ``bundle_id`` or ``sync_info``. Unmarked files are never touched.
    """
    ensure_side_effect_allowed()
    wanted = {int(value) for value in remote_ids}
    removed = 0
    removed_ids = set()
    kept_stems = set()
    for artifact in scan_managed_preset_artifacts(folder):
        preset_id = artifact.get("preset_id")
        if artifact.get("healthy") and preset_id in wanted:
            kept_stems.update(_artifact_stems(artifact))
            continue
        reason = "invalid-managed" if preset_id is None else "not-in-profile-%d" % preset_id
        ensure_side_effect_allowed()
        if _quarantine_managed_preset_artifact(artifact, reason):
            removed += 1
            if preset_id is not None:
                removed_ids.add(preset_id)

    # Everything left in this folder is ours too: Orca groups presets by bundle
    # directory, the user's own presets live elsewhere, and only this plugin writes
    # here. Older plugin versions wrote no ownership marker, so the scan above
    # cannot see those files and they would stay in the FilamentHub tab forever.
    for stem in preset_file_stems(folder) - kept_stems:
        json_path = os.path.join(folder, stem + ".json")
        info_path = os.path.join(folder, stem + ".info")
        leftover = {
            "json_path": json_path if os.path.isfile(json_path) else None,
            "info_path": info_path if os.path.isfile(info_path) else None,
        }
        ensure_side_effect_allowed()
        if _quarantine_managed_preset_artifact(leftover, "unmarked-bundle-file"):
            removed += 1
    return removed, removed_ids


def _managed_profile_info_claim(path, kind):
    prefix = "filamenthub:%s:" % kind
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                key, separator, value = line.partition("=")
                if separator and key.strip() == "sync_info":
                    value = value.strip()
                    claimed = (
                        value.startswith("filamenthub:machine:")
                        or value.startswith("filamenthub:process:")
                    )
                    if value.startswith(prefix):
                        tail = value[len(prefix):]
                        return claimed, int(tail) if tail.isdigit() else None
                    return claimed, None
    except OSError:
        pass
    return False, None


def _managed_profile_id_from_info(path, kind):
    return _managed_profile_info_claim(path, kind)[1]


MAX_BAMBU_BRIDGES = 8
_BAMBU_CONFIG_LOCK = threading.RLock()


def _normalized_bambu_serial(serial):
    value = str(serial or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{4,80}", value):
        return ""
    return value.upper()


def _valid_bambu_device_identity(identity):
    if not isinstance(identity, dict):
        return None
    kind = identity.get("kind")
    token = identity.get("token")
    if kind != "bambu_serial" or not re.fullmatch(r"[0-9a-f]{64}", str(token or "")):
        return None
    return {"kind": kind, "token": token}


def _bambu_device_identity(discovery_key, serial):
    canonical_serial = _normalized_bambu_serial(serial)
    if not canonical_serial:
        return None
    token = _printer_evidence_token(
        discovery_key,
        "device",
        "bambu_serial\0" + canonical_serial,
    )
    if token is None:
        return None
    return {"kind": "bambu_serial", "token": token}


def _assert_bambu_binding_available(
    payload,
    physical_printer_id,
    serial,
    device_identity=None,
):
    canonical_serial = _normalized_bambu_serial(serial)
    if serial and not canonical_serial:
        raise ValueError("invalid serial")
    identity = _valid_bambu_device_identity(device_identity)
    for item in payload.get("printers") or []:
        if item.get("physical_printer_id") == physical_printer_id:
            continue
        existing_serial = _normalized_bambu_serial(item.get("serial"))
        if canonical_serial and existing_serial == canonical_serial:
            raise ValueError("Bambu printer is already linked")
        existing_identity = _valid_bambu_device_identity(item.get("device_identity"))
        if identity and existing_identity == identity:
            raise ValueError("Bambu printer is already linked")


def _empty_bambu_config():
    return {
        "version": 1,
        "source_instance_id": secrets.token_urlsafe(24),
        "printers": [],
    }


def load_bambu_config():
    """Read the private local bridge file without ever logging its contents."""
    try:
        with open(BAMBU_CONFIG_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return _empty_bambu_config()
    if not isinstance(payload, dict):
        return _empty_bambu_config()
    instance_id = payload.get("source_instance_id")
    if not isinstance(instance_id, str) or not (16 <= len(instance_id) <= 100):
        instance_id = secrets.token_urlsafe(24)
    printers = []
    for item in payload.get("printers") or []:
        if not isinstance(item, dict):
            continue
        physical_id = item.get("physical_printer_id")
        system_id = item.get("material_system_id")
        host = item.get("host")
        access_code = item.get("access_code")
        serial = item.get("serial") or ""
        bridge_token = item.get("bridge_token") or ""
        device_identity = _valid_bambu_device_identity(item.get("device_identity"))
        if (
            isinstance(serial, str)
            and serial
            and not re.fullmatch(r"[A-Za-z0-9._-]{4,80}", serial)
        ):
            serial = ""
        if (
            isinstance(physical_id, int)
            and physical_id > 0
            and isinstance(system_id, int)
            and system_id > 0
            and isinstance(host, str)
            and host
            and isinstance(access_code, str)
            and access_code
            and isinstance(serial, str)
            and isinstance(bridge_token, str)
        ):
            printer = {
                "physical_printer_id": physical_id,
                "material_system_id": system_id,
                "host": host[:253],
                "access_code": access_code[:128],
                "serial": serial[:80],
                "bridge_token": bridge_token[:256],
            }
            if device_identity is not None:
                printer["device_identity"] = device_identity
            printers.append(printer)
        if len(printers) >= MAX_BAMBU_BRIDGES:
            break
    return {
        "version": 1,
        "source_instance_id": instance_id,
        "printers": printers,
    }


def save_bambu_config(payload):
    write_json_atomic(BAMBU_CONFIG_FILE, payload, mode=0o600)


def configure_bambu_bridge(
    physical_printer_id,
    material_system_id,
    host,
    access_code,
    serial="",
    bridge_token="",
    device_identity=None,
):
    """Create or replace one local-only Bambu LAN binding."""
    if not isinstance(physical_printer_id, int) or physical_printer_id <= 0:
        raise ValueError("invalid physical printer")
    if not isinstance(material_system_id, int) or material_system_id <= 0:
        raise ValueError("invalid material system")
    host = str(host or "").strip()
    access_code = str(access_code or "").strip()
    serial = str(serial or "").strip()
    bridge_token = str(bridge_token or "").strip()
    if not host or len(host) > 253 or any(ch in host for ch in "/\\?#@"):
        raise ValueError("invalid LAN address")
    if not access_code or len(access_code) > 128:
        raise ValueError("invalid access code")
    if serial and not re.fullmatch(r"[A-Za-z0-9._-]{4,80}", serial):
        raise ValueError("invalid serial")
    if bridge_token and (not bridge_token.startswith("fhpb_") or len(bridge_token) > 256):
        raise ValueError("invalid bridge token")
    identity = _valid_bambu_device_identity(device_identity)
    if device_identity is not None and identity is None:
        raise ValueError("invalid Bambu device identity")

    with _BAMBU_CONFIG_LOCK:
        payload = load_bambu_config()
        _assert_bambu_binding_available(
            payload,
            physical_printer_id,
            serial,
            identity,
        )
        printers = [
            item
            for item in payload["printers"]
            if item["physical_printer_id"] != physical_printer_id
        ]
        printer = {
            "physical_printer_id": physical_printer_id,
            "material_system_id": material_system_id,
            "host": host,
            "access_code": access_code,
            "serial": serial,
            "bridge_token": bridge_token,
        }
        if identity is not None:
            printer["device_identity"] = identity
        printers.append(printer)
        if len(printers) > MAX_BAMBU_BRIDGES:
            raise ValueError("too many Bambu bridges")
        payload["printers"] = printers
        save_bambu_config(payload)
        return payload


def remove_bambu_bridge(physical_printer_id):
    with _BAMBU_CONFIG_LOCK:
        payload = load_bambu_config()
        before = len(payload["printers"])
        payload["printers"] = [
            item
            for item in payload["printers"]
            if item["physical_printer_id"] != physical_printer_id
        ]
        if len(payload["printers"]) != before:
            save_bambu_config(payload)
            return True
        return False


def remove_interrupted_bambu_binding(
    physical_printer_id, fresh_bridge_token, previous_payload
):
    """Remove only local credentials invalidated by an interrupted server pair.

    A successful pair replaces the server-side token hash, so restoring the
    previous local token would only manufacture a dead "paired" connection.
    The lifecycle bypass removes the exact fresh binding, or the byte-for-byte
    previous binding when persistence had not started yet. A later lifecycle's
    different binding is never touched.
    """
    if (
        not isinstance(physical_printer_id, int)
        or physical_printer_id <= 0
        or not isinstance(fresh_bridge_token, str)
        or not fresh_bridge_token.startswith("fhpb_")
        or not isinstance(previous_payload, dict)
    ):
        return False
    previous_binding = next(
        (
            dict(item)
            for item in previous_payload.get("printers") or []
            if item.get("physical_printer_id") == physical_printer_id
        ),
        None,
    )
    with _BAMBU_CONFIG_LOCK:
        current = load_bambu_config()
        current_binding = next(
            (
                item
                for item in current["printers"]
                if item.get("physical_printer_id") == physical_printer_id
            ),
            None,
        )
        if current_binding is None:
            return False
        if (
            current_binding.get("bridge_token") != fresh_bridge_token
            and current_binding != previous_binding
        ):
            return False
        current["printers"] = [
            item
            for item in current["printers"]
            if item.get("physical_printer_id") != physical_printer_id
        ]
        encoded = json.dumps(current, ensure_ascii=False, indent=2).encode("utf-8")
        _write_bytes_atomic_unchecked(BAMBU_CONFIG_FILE, encoded, mode=0o600)
        return True


def managed_profile_id(json_path, profile, kind):
    pid = preset_id_from_bundle(profile.get("bundle_id")) if isinstance(profile, dict) else None
    if pid is not None:
        return pid
    return _managed_profile_id_from_info(json_path[:-len(".json")] + ".info", kind)


def managed_profile_file_path(folder, name, profile_id, kind):
    stem = safe_filename(name) or ("FilamentHub %s %d" % (kind, int(profile_id)))
    candidate = os.path.join(folder, stem + ".json")
    if not os.path.exists(candidate):
        return candidate
    try:
        with open(candidate, "r", encoding="utf-8") as fh:
            existing = json.load(fh)
        if managed_profile_id(candidate, existing, kind) == int(profile_id):
            return candidate
    except (OSError, ValueError):
        pass
    return os.path.join(
        folder,
        "%s (FH-%s-%d).json" % (stem, kind.capitalize(), int(profile_id)),
    )


def write_managed_profile_info(base, kind, profile_id):
    write_bytes_atomic(
        base + ".info",
        ("sync_info = filamenthub:%s:%d\n" % (kind, int(profile_id))).encode("utf-8"),
    )


def remove_stale_managed_profile_files(folder, profile_id, kind, keep_path):
    with side_effect_transaction():
        return _remove_stale_managed_profile_files_transaction(
            folder, profile_id, kind, keep_path
        )


def _remove_stale_managed_profile_files_transaction(
    folder, profile_id, kind, keep_path
):
    try:
        names = os.listdir(folder)
    except OSError:
        return
    keep = os.path.normcase(os.path.abspath(keep_path))
    for filename in names:
        if not filename.endswith(".json"):
            continue
        path = os.path.join(folder, filename)
        if os.path.normcase(os.path.abspath(path)) == keep:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                profile = json.load(fh)
        except (OSError, ValueError):
            continue
        if managed_profile_id(path, profile, kind) != int(profile_id):
            continue
        for stale in (path, path[:-len(".json")] + ".info"):
            try:
                os.remove(stale)
            except OSError:
                pass


def repair_local_bundle_parents():
    """Repair legacy FilamentHub files that reference vendor-private parents.

    Only profiles carrying our durable ``bundle_id``/``.info`` identity are
    touched. The change becomes visible on this startup when plugins register
    before user presets are loaded; otherwise Orca picks it up on the next one.
    """
    repaired = 0
    for kind, folder in (
        ("filament", user_filament_dir()),
        ("machine", user_machine_dir()),
        ("process", user_process_dir()),
    ):
        try:
            filenames = os.listdir(folder)
        except OSError:
            continue
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            path = os.path.join(folder, filename)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    profile = json.load(fh)
            except (OSError, ValueError):
                continue
            if not isinstance(profile, dict):
                continue
            if kind == "filament":
                profile_id = managed_preset_id(path, profile)
            else:
                profile_id = managed_profile_id(path, profile, kind)
            if profile_id is None or not _is_internal_fdm_parent(_parent_name(profile)):
                continue
            normalize_local_bundle_parent(profile)
            try:
                write_json_atomic(path, profile)
            except OSError:
                continue
            repaired += 1
    return repaired


def _validated_bundle_entries(bundle, key, kind, maximum):
    entries = bundle.get(key)
    if not isinstance(entries, list) or len(entries) > maximum:
        raise ValueError("Invalid %s profile list" % kind)
    validated = []
    expected_type = "machine" if kind == "machine" else "process"
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid %s profile entry" % kind)
        profile_id = entry.get("id")
        profile = entry.get("profile")
        if (
            isinstance(profile_id, bool)
            or not isinstance(profile_id, int)
            or profile_id <= 0
            or not isinstance(profile, dict)
        ):
            raise ValueError("Invalid %s profile identity" % kind)
        profile = dict(profile)
        name = profile.get("name") or entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Invalid %s profile name" % kind)
        profile_type = profile.get("type")
        if profile_type not in (None, expected_type):
            raise ValueError("Invalid %s profile type" % kind)
        profile["type"] = expected_type
        normalize_local_bundle_parent(profile)
        profile["bundle_id"] = "filamenthub:%d" % profile_id
        rejected = orca_transport_violations(profile)
        if rejected:
            raise ValueError(
                "OrcaSlicer cannot load these %s profile values: %s"
                % (kind, ", ".join(rejected))
            )
        validated.append({"id": profile_id, "name": name.strip(), "profile": profile})
    return validated


MAX_TRACKED_PRINTER_BUNDLES = 100
MAX_TRACKED_RECOVERY_ARTIFACTS = (
    MAX_MACHINE_BUNDLE_PROFILES + MAX_PROCESS_BUNDLE_PROFILES
)


def _empty_printer_bundle_state():
    return {"version": 2, "printers": [], "scopes": []}


def _validated_profile_ids(values, maximum):
    if not isinstance(values, list) or len(values) > maximum:
        return None
    result = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        if value not in result:
            result.append(value)
    return result


def load_printer_bundle_state():
    """Load scoped ownership state; v1 remains readable for local cleanup."""
    try:
        with open(PRINTER_BUNDLE_STATE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return _empty_printer_bundle_state()
    if not isinstance(payload, dict) or payload.get("version") not in (1, 2):
        return _empty_printer_bundle_state()
    printers = []
    seen = set()
    for item in payload.get("printers") or []:
        if not isinstance(item, dict):
            continue
        physical_id = item.get("physical_printer_id")
        machines = _validated_profile_ids(
            item.get("machine_profile_ids"), MAX_MACHINE_BUNDLE_PROFILES
        )
        processes = _validated_profile_ids(
            item.get("process_profile_ids"), MAX_PROCESS_BUNDLE_PROFILES
        )
        if (
            isinstance(physical_id, bool)
            or not isinstance(physical_id, int)
            or physical_id <= 0
            or physical_id in seen
            or machines is None
            or processes is None
            or (not machines and not processes)
        ):
            continue
        seen.add(physical_id)
        printers.append({
            "physical_printer_id": physical_id,
            "machine_profile_ids": machines,
            "process_profile_ids": processes,
        })
        if len(printers) >= MAX_TRACKED_PRINTER_BUNDLES:
            break
    scopes = []
    if payload.get("version") == 2:
        for raw_scope in payload.get("scopes") or []:
            if not isinstance(raw_scope, dict):
                continue
            owner_user_id = raw_scope.get("owner_user_id")
            source_instance_id = raw_scope.get("source_instance_id")
            account_id = _valid_uuid(raw_scope.get("account_id"))
            server_origin = raw_scope.get("server_origin")
            if (
                isinstance(owner_user_id, bool)
                or not isinstance(owner_user_id, int)
                or owner_user_id <= 0
                or not isinstance(source_instance_id, str)
                or not 16 <= len(source_instance_id) <= 100
                or account_id is None
                or not isinstance(server_origin, str)
                or not server_origin
            ):
                continue
            artifacts = []
            seen_artifacts = set()
            for artifact in raw_scope.get("artifacts") or []:
                if not isinstance(artifact, dict):
                    continue
                kind = artifact.get("kind")
                profile_id = artifact.get("profile_id")
                key = (kind, profile_id)
                content_hash = artifact.get("content_hash")
                name = artifact.get("name")
                if (
                    kind not in ("machine", "process")
                    or isinstance(profile_id, bool)
                    or not isinstance(profile_id, int)
                    or profile_id <= 0
                    or key in seen_artifacts
                    or not isinstance(content_hash, str)
                    or len(content_hash) != 64
                    or not isinstance(name, str)
                ):
                    continue
                seen_artifacts.add(key)
                artifacts.append({
                    "kind": kind,
                    "profile_id": profile_id,
                    "name": name[:200],
                    "content_hash": content_hash,
                })
                if len(artifacts) >= MAX_TRACKED_RECOVERY_ARTIFACTS:
                    break
            scopes.append({
                "server_origin": server_origin.rstrip("/"),
                "owner_user_id": owner_user_id,
                "source_instance_id": source_instance_id,
                "account_id": account_id,
                "artifacts": artifacts,
            })
            if len(scopes) >= 20:
                break
    return {"version": 2, "printers": printers, "scopes": scopes}


def save_printer_bundle_state(payload):
    write_json_atomic(PRINTER_BUNDLE_STATE_FILE, payload, mode=0o600)


def printer_bundle_profile_ids(bundle):
    if not isinstance(bundle, dict):
        raise ValueError("Printer bundle must be a JSON object")
    if bundle.get("format") not in (
        "filamenthub.orcaslicer.printer-bundle",
        "filamenthub.orcaslicer.printer-recovery",
    ) or bundle.get("version") != 1:
        raise ValueError("Unsupported printer bundle format")
    machines = _validated_bundle_entries(
        bundle, "machine_profiles", "machine", MAX_MACHINE_BUNDLE_PROFILES
    )
    processes = _validated_bundle_entries(
        bundle, "process_profiles", "process", MAX_PROCESS_BUNDLE_PROFILES
    )
    if not machines and not processes:
        raise ValueError("Printer bundle has no profiles")
    return {
        "machine": [entry["id"] for entry in machines],
        "process": [entry["id"] for entry in processes],
    }


def remember_installed_printer_bundle(physical_printer_id, profile_ids):
    state = load_printer_bundle_state()
    state["printers"] = [
        item for item in state["printers"]
        if item["physical_printer_id"] != int(physical_printer_id)
    ]
    state["printers"].append({
        "physical_printer_id": int(physical_printer_id),
        "machine_profile_ids": list(profile_ids["machine"]),
        "process_profile_ids": list(profile_ids["process"]),
    })
    if len(state["printers"]) > MAX_TRACKED_PRINTER_BUNDLES:
        state["printers"] = state["printers"][-MAX_TRACKED_PRINTER_BUNDLES:]
    save_printer_bundle_state(state)


def _managed_profile_artifacts(folder, kind):
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    stems = {
        name[:-len(extension)]
        for name in names
        for extension in (".json", ".info")
        if name.endswith(extension)
    }
    artifacts = []
    for stem in stems:
        json_path = os.path.join(folder, stem + ".json")
        info_path = os.path.join(folder, stem + ".info")
        profile = None
        if os.path.isfile(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as handle:
                    candidate = json.load(handle)
                if isinstance(candidate, dict):
                    profile = candidate
            except (OSError, ValueError):
                pass
        json_id = (
            preset_id_from_bundle(profile.get("bundle_id"))
            if isinstance(profile, dict) else None
        )
        bundle_value = profile.get("bundle_id") if isinstance(profile, dict) else None
        bundle_claimed = (
            isinstance(bundle_value, str)
            and bundle_value.startswith("filamenthub:")
        )
        info_claimed, info_id = _managed_profile_info_claim(info_path, kind)
        if not bundle_claimed and not info_claimed:
            continue
        claimed = {value for value in (json_id, info_id) if value is not None}
        profile_id = next(iter(claimed)) if len(claimed) == 1 else None
        markers_valid = (
            (not bundle_claimed or json_id is not None)
            and (not info_claimed or info_id is not None)
        )
        artifacts.append({
            "json_path": json_path if os.path.isfile(json_path) else None,
            "info_path": info_path if os.path.isfile(info_path) else None,
            "profile": profile,
            "profile_id": profile_id,
            "healthy": (
                profile is not None
                and profile_id is not None
                and len(claimed) == 1
                and markers_valid
            ),
        })
    return artifacts


def installed_managed_profile_ids(folder, kind):
    return {
        artifact["profile_id"]
        for artifact in _managed_profile_artifacts(folder, kind)
        if artifact["healthy"]
    }


def installed_printer_bundle_ids(physical_printer_ids):
    wanted = set(physical_printer_ids)
    machines = installed_managed_profile_ids(user_machine_dir(), "machine")
    processes = installed_managed_profile_ids(user_process_dir(), "process")
    installed = set()
    for item in load_printer_bundle_state()["printers"]:
        if item["physical_printer_id"] not in wanted:
            continue
        if (
            set(item["machine_profile_ids"]).issubset(machines)
            and set(item["process_profile_ids"]).issubset(processes)
        ):
            installed.add(item["physical_printer_id"])
    return installed


def printer_bundle_profiles_present(profile_ids):
    return (
        set(profile_ids["machine"]).issubset(
            installed_managed_profile_ids(user_machine_dir(), "machine")
        )
        and set(profile_ids["process"]).issubset(
            installed_managed_profile_ids(user_process_dir(), "process")
        )
    )


def remove_installed_printer_bundle(physical_printer_id):
    with side_effect_transaction():
        return _remove_installed_printer_bundle_transaction(physical_printer_id)


def _remove_installed_printer_bundle_transaction(physical_printer_id):
    """Quarantine only FH-owned profiles no other installed printer needs."""
    state = load_printer_bundle_state()
    current = next(
        (
            item for item in state["printers"]
            if item["physical_printer_id"] == int(physical_printer_id)
        ),
        None,
    )
    if current is None:
        return {"machine": 0, "process": 0}

    others = [item for item in state["printers"] if item is not current]
    protected = {
        "machine": {
            profile_id for item in others for profile_id in item["machine_profile_ids"]
        },
        "process": {
            profile_id for item in others for profile_id in item["process_profile_ids"]
        },
    }
    wanted = {
        "machine": set(current["machine_profile_ids"]) - protected["machine"],
        "process": set(current["process_profile_ids"]) - protected["process"],
    }
    counts = {"machine": 0, "process": 0}
    for kind, folder in (
        ("machine", user_machine_dir()),
        ("process", user_process_dir()),
    ):
        for artifact in _managed_profile_artifacts(folder, kind):
            if artifact["profile_id"] not in wanted[kind]:
                continue
            if not _quarantine_managed_preset_artifact(
                artifact,
                "printer-%d-%s-%d" % (
                    int(physical_printer_id), kind, artifact["profile_id"]
                ),
            ):
                raise OSError("could not quarantine managed %s profile" % kind)
            counts[kind] += 1

    state["printers"] = others
    save_printer_bundle_state(state)
    return counts


def prepare_printer_bundle_install(bundle):
    if not isinstance(bundle, dict):
        raise ValueError("Printer bundle must be a JSON object")
    if bundle.get("format") not in (
        "filamenthub.orcaslicer.printer-bundle",
        "filamenthub.orcaslicer.printer-recovery",
    ) or bundle.get("version") != 1:
        raise ValueError("Unsupported printer bundle format")

    machines = _validated_bundle_entries(
        bundle, "machine_profiles", "machine", MAX_MACHINE_BUNDLE_PROFILES
    )
    processes = _validated_bundle_entries(
        bundle, "process_profiles", "process", MAX_PROCESS_BUNDLE_PROFILES
    )
    if not machines and not processes:
        raise ValueError("Printer bundle has no profiles")

    prepared = []
    machine_names = {}
    for entry in machines:
        path = managed_profile_file_path(
            user_machine_dir(), entry["name"], entry["id"], "machine"
        )
        local_name = os.path.basename(path)[:-len(".json")]
        machine_names[entry["profile"].get("name") or entry["name"]] = local_name
        entry["profile"]["name"] = local_name
        entry["profile"]["printer_settings_id"] = local_name
        prepared.append(("machine", entry["id"], path, entry["profile"]))

    for entry in processes:
        path = managed_profile_file_path(
            user_process_dir(), entry["name"], entry["id"], "process"
        )
        local_name = os.path.basename(path)[:-len(".json")]
        entry["profile"]["name"] = local_name
        entry["profile"]["print_settings_id"] = local_name
        compatible = entry["profile"].get("compatible_printers")
        if isinstance(compatible, list):
            entry["profile"]["compatible_printers"] = [
                machine_names.get(str(name), str(name)) for name in compatible
            ]
        prepared.append(("process", entry["id"], path, entry["profile"]))
    return prepared


def install_printer_bundle(
    bundle, physical_printer_id=None, replace_existing_ids=False
):
    with side_effect_transaction():
        return _install_printer_bundle_transaction(
            bundle,
            physical_printer_id=physical_printer_id,
            replace_existing_ids=replace_existing_ids,
        )


def _install_printer_bundle_transaction(
    bundle, physical_printer_id=None, replace_existing_ids=False
):
    profile_ids = printer_bundle_profile_ids(bundle)
    prepared = prepare_printer_bundle_install(bundle)
    ensure_bundle_metadata()
    counts = {"machine": 0, "process": 0}
    os.makedirs(user_bundle_dir(), mode=0o700, exist_ok=True)
    # Keep staging on the same volume as the live local bundle: os.replace is
    # atomic only within one filesystem (and Windows rejects cross-volume moves).
    stage_root = tempfile.mkdtemp(prefix=".printer-recovery-", dir=user_bundle_dir())
    staged = []
    backups = []
    installed = []
    try:
        for index, (kind, profile_id, path, profile) in enumerate(prepared):
            stage_base = os.path.join(stage_root, "%03d-%s-%d" % (index, kind, profile_id))
            staged_json = stage_base + ".json"
            staged_info = stage_base + ".info"
            write_json_atomic(staged_json, profile)
            write_managed_profile_info(stage_base, kind, profile_id)
            with open(staged_json, "r", encoding="utf-8") as handle:
                verified = json.load(handle)
            if managed_profile_id(staged_json, verified, kind) != profile_id:
                raise ValueError("Staged managed profile identity mismatch")
            staged.append((kind, profile_id, path, staged_json, staged_info))

        rollback_root = os.path.join(stage_root, "rollback")
        os.makedirs(rollback_root, mode=0o700, exist_ok=True)
        for kind, profile_id, path, staged_json, staged_info in staged:
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            target_info = path[:-len(".json")] + ".info"
            replacement_targets = [path, target_info]
            if replace_existing_ids:
                for artifact in _managed_profile_artifacts(
                    os.path.dirname(path), kind
                ):
                    if artifact.get("profile_id") != profile_id:
                        continue
                    replacement_targets.extend(
                        candidate
                        for candidate in (
                            artifact.get("json_path"),
                            artifact.get("info_path"),
                        )
                        if candidate
                    )
            seen_targets = set()
            for target in replacement_targets:
                normalized_target = os.path.normcase(os.path.abspath(target))
                if normalized_target in seen_targets:
                    continue
                seen_targets.add(normalized_target)
                if not os.path.isfile(target):
                    continue
                backup = os.path.join(
                    rollback_root,
                    "%03d-%s" % (len(backups), os.path.basename(target)),
                )
                os.replace(target, backup)
                backups.append((target, backup))
            os.replace(staged_json, path)
            installed.append((path, staged_json))
            os.replace(staged_info, target_info)
            installed.append((target_info, staged_info))
            counts[kind] += 1
        if backups:
            quarantine_root = managed_preset_quarantine_dir()
            os.makedirs(quarantine_root, mode=0o700, exist_ok=True)
            durable_rollback = os.path.join(
                quarantine_root,
                "%s-printer-recovery-replaced-%s" % (
                    time.strftime("%Y%m%d-%H%M%S"),
                    secrets.token_hex(4),
                ),
            )
            os.replace(rollback_root, durable_rollback)
    except Exception:
        for target, staged_path in reversed(installed):
            if os.path.isfile(target):
                try:
                    os.replace(target, staged_path)
                except OSError as exc:
                    fh_log("printer recovery rollback move failed: %r" % exc)
        for target, backup in reversed(backups):
            if os.path.isfile(backup):
                try:
                    os.replace(backup, target)
                except OSError as exc:
                    fh_log("printer recovery rollback restore failed: %r" % exc)
        raise
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
    if physical_printer_id is not None:
        remember_installed_printer_bundle(physical_printer_id, profile_ids)
    return counts


def _managed_profile_content_hash(profile):
    encoded = json.dumps(
        profile,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _recovery_scope_from_bundle(bundle):
    if (
        not isinstance(bundle, dict)
        or bundle.get("format") != "filamenthub.orcaslicer.printer-recovery"
        or bundle.get("version") != 1
    ):
        raise ValueError("Unsupported printer recovery format")
    raw = bundle.get("scope")
    if not isinstance(raw, dict):
        raise ValueError("Printer recovery scope is missing")
    owner_user_id = raw.get("owner_user_id")
    source_instance_id = raw.get("source_instance_id")
    account_id = _valid_uuid(raw.get("account_id"))
    if (
        isinstance(owner_user_id, bool)
        or not isinstance(owner_user_id, int)
        or owner_user_id <= 0
        or not isinstance(source_instance_id, str)
        or not 16 <= len(source_instance_id) <= 100
        or account_id is None
    ):
        raise ValueError("Invalid printer recovery scope")
    return {
        "server_origin": account_origin(),
        "owner_user_id": owner_user_id,
        "source_instance_id": source_instance_id,
        "account_id": account_id,
    }


def _scope_matches(left, right):
    return all(
        left.get(key) == right.get(key)
        for key in (
            "server_origin",
            "owner_user_id",
            "source_instance_id",
            "account_id",
        )
    )


def _recovery_bundle_journal_artifacts(bundle):
    artifacts = []
    seen = set()
    for key, kind, maximum in (
        ("machine_profiles", "machine", MAX_MACHINE_BUNDLE_PROFILES),
        ("process_profiles", "process", MAX_PROCESS_BUNDLE_PROFILES),
    ):
        entries = _validated_bundle_entries(bundle, key, kind, maximum)
        raw_by_id = {
            entry.get("id"): entry
            for entry in bundle.get(key) or []
            if isinstance(entry, dict)
        }
        for entry in entries:
            artifact_key = (kind, entry["id"])
            if artifact_key in seen:
                raise ValueError("Printer recovery contains duplicate profiles")
            seen.add(artifact_key)
            raw = raw_by_id.get(entry["id"]) or {}
            expected_hash = raw.get("content_hash")
            actual_hash = _managed_profile_content_hash(raw.get("profile"))
            if (
                not isinstance(expected_hash, str)
                or len(expected_hash) != 64
                or expected_hash != actual_hash
            ):
                raise ValueError("Printer recovery content hash mismatch")
            artifacts.append({
                "kind": kind,
                "profile_id": entry["id"],
                "name": entry["name"],
                "content_hash": expected_hash,
            })
    if not artifacts:
        raise ValueError("Printer recovery has no profiles")
    return artifacts


def remember_recovered_profiles(scope, artifacts):
    state = load_printer_bundle_state()
    current = next(
        (item for item in state["scopes"] if _scope_matches(item, scope)),
        None,
    )
    if current is None:
        current = dict(scope, artifacts=[])
        state["scopes"].append(current)
    merged = {
        (item["kind"], item["profile_id"]): item
        for item in current["artifacts"]
    }
    for artifact in artifacts:
        merged[(artifact["kind"], artifact["profile_id"])] = dict(artifact)
    current["artifacts"] = list(merged.values())[-MAX_TRACKED_RECOVERY_ARTIFACTS:]
    state["scopes"] = state["scopes"][-20:]
    save_printer_bundle_state(state)


def _assert_recovery_install_is_owned(scope, artifacts):
    """Refuse to adopt or overwrite managed files from an ambiguous scope."""
    wanted = {(item["kind"], item["profile_id"]) for item in artifacts}
    state = load_printer_bundle_state()
    current = next(
        (item for item in state["scopes"] if _scope_matches(item, scope)),
        None,
    )
    current_by_key = {
        (item["kind"], item["profile_id"]): item
        for item in (current or {}).get("artifacts", [])
    }
    foreign_keys = {
        (item["kind"], item["profile_id"])
        for saved_scope in state["scopes"]
        if not _scope_matches(saved_scope, scope)
        for item in saved_scope["artifacts"]
    }
    found = {}
    conflicts = set()
    for kind, folder in (
        ("machine", user_machine_dir()),
        ("process", user_process_dir()),
    ):
        for artifact in _managed_profile_artifacts(folder, kind):
            key = (kind, artifact.get("profile_id"))
            if key not in wanted:
                continue
            found[key] = found.get(key, 0) + 1
            if (
                key not in current_by_key
                or key in foreign_keys
                or not artifact.get("healthy")
            ):
                conflicts.add(key)
    conflicts.update(key for key, count in found.items() if count != 1)
    if conflicts:
        raise ValueError(
            "Conflicting local managed profiles must be removed before recovery"
        )
    return {
        key: current_by_key[key]["content_hash"]
        for key, count in found.items()
        if count == 1 and key in current_by_key
    }


def install_printer_recovery(bundle):
    with side_effect_transaction():
        return _install_printer_recovery_transaction(bundle)


def _install_printer_recovery_transaction(bundle):
    scope = _recovery_scope_from_bundle(bundle)
    if scope["source_instance_id"] != plugin_source_instance_id():
        raise ValueError("Printer recovery belongs to another Orca installation")
    registry = load_profile_identity_registry()
    if scope["account_id"] != registry["account_id"]:
        raise ValueError("Printer recovery belongs to another Orca account")
    artifacts = _recovery_bundle_journal_artifacts(bundle)
    installed_hashes = _assert_recovery_install_is_owned(scope, artifacts)
    unchanged = {
        (item["kind"], item["profile_id"])
        for item in artifacts
        if installed_hashes.get((item["kind"], item["profile_id"]))
        == item["content_hash"]
    }
    write_bundle = dict(bundle)
    write_bundle["machine_profiles"] = [
        item for item in bundle.get("machine_profiles") or []
        if ("machine", item.get("id")) not in unchanged
    ]
    write_bundle["process_profiles"] = [
        item for item in bundle.get("process_profiles") or []
        if ("process", item.get("id")) not in unchanged
    ]
    if write_bundle["machine_profiles"] or write_bundle["process_profiles"]:
        counts = install_printer_bundle(
            write_bundle, replace_existing_ids=True
        )
    else:
        counts = {"machine": 0, "process": 0}
    remember_recovered_profiles(scope, artifacts)
    return scope, [
        dict(
            item,
            unchanged=(item["kind"], item["profile_id"]) in unchanged,
        )
        for item in artifacts
    ], counts


def _recovery_artifact_key(kind, artifact):
    stems = sorted(_artifact_stems(artifact), key=str.casefold)
    encoded = (kind + "\0" + "\0".join(stems)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


def current_printer_recovery_state(owner_user_id, original_observations=None):
    registry = load_profile_identity_registry()
    save_profile_identity_registry(registry)
    scope = {
        "server_origin": account_origin(),
        "owner_user_id": int(owner_user_id),
        "source_instance_id": plugin_source_instance_id(),
        "account_id": registry["account_id"],
    }
    state = load_printer_bundle_state()
    current = next(
        (item for item in state["scopes"] if _scope_matches(item, scope)),
        None,
    )
    current_by_key = {
        (item["kind"], item["profile_id"]): item
        for item in (current or {}).get("artifacts", [])
    }
    foreign_keys = {
        (item["kind"], item["profile_id"])
        for saved_scope in state["scopes"]
        if not _scope_matches(saved_scope, scope)
        for item in saved_scope["artifacts"]
    }
    artifacts = []
    for kind, folder in (
        ("machine", user_machine_dir()),
        ("process", user_process_dir()),
    ):
        for artifact in _managed_profile_artifacts(folder, kind):
            profile_id = artifact.get("profile_id")
            key = (kind, profile_id)
            journal = current_by_key.get(key)
            ownership = (
                "current"
                if journal is not None
                else "foreign"
                if profile_id is not None and key in foreign_keys
                else "untracked"
            )
            profile = artifact.get("profile")
            artifacts.append({
                "artifactKey": _recovery_artifact_key(kind, artifact),
                "kind": kind,
                "profileId": profile_id,
                "name": (
                    profile.get("name")
                    if isinstance(profile, dict) and isinstance(profile.get("name"), str)
                    else (
                        sorted(_artifact_stems(artifact), key=str.casefold)[0]
                        if _artifact_stems(artifact)
                        else "Managed profile"
                    )
                ),
                "contentHash": journal.get("content_hash") if journal else None,
                "ownership": ownership,
                "healthy": bool(artifact.get("healthy")),
            })
    return {
        "context": scope,
        "artifacts": artifacts,
        "originalObservations": original_observations or {},
    }


def observe_recovery_originals():
    """Read original user profiles on the UI thread without contacting FH."""
    observed = {}
    for kind in ("machine", "process"):
        items, complete = scan_user_profiles_checked(kind)
        if not complete:
            observed[kind] = {"complete": False, "presentLocalProfileIds": []}
            continue
        _account_id, identified, saved = reconcile_local_profile_identities(
            kind, items, authoritative=True
        )
        observed[kind] = {
            "complete": bool(saved),
            "presentLocalProfileIds": [
                item["local_profile_id"] for item in identified
                if item.get("local_profile_id")
            ] if saved else [],
        }
    return observed


def remove_printer_recovery_artifacts(artifact_keys):
    with side_effect_transaction():
        return _remove_printer_recovery_artifacts_transaction(artifact_keys)


def _remove_printer_recovery_artifacts_transaction(artifact_keys):
    wanted = set(artifact_keys)
    removed = []
    failed = []
    for kind, folder in (
        ("machine", user_machine_dir()),
        ("process", user_process_dir()),
    ):
        for artifact in _managed_profile_artifacts(folder, kind):
            artifact_key = _recovery_artifact_key(kind, artifact)
            if artifact_key not in wanted:
                continue
            result = {
                "artifactKey": artifact_key,
                "kind": kind,
                "profileId": artifact.get("profile_id"),
            }
            if _quarantine_managed_preset_artifact(
                artifact, "printer-recovery-%s" % artifact_key
            ):
                removed.append(result)
            else:
                failed.append(result)

    remaining = {
        (kind, artifact.get("profile_id"))
        for kind, folder in (
            ("machine", user_machine_dir()),
            ("process", user_process_dir()),
        )
        for artifact in _managed_profile_artifacts(folder, kind)
        if artifact.get("profile_id") is not None
    }
    state = load_printer_bundle_state()
    for saved_scope in state["scopes"]:
        saved_scope["artifacts"] = [
            item
            for item in saved_scope["artifacts"]
            if (item["kind"], item["profile_id"]) in remaining
        ]
    state["printers"] = [
        dict(
            item,
            machine_profile_ids=[
                profile_id
                for profile_id in item["machine_profile_ids"]
                if ("machine", profile_id) in remaining
            ],
            process_profile_ids=[
                profile_id
                for profile_id in item["process_profile_ids"]
                if ("process", profile_id) in remaining
            ],
        )
        for item in state["printers"]
        if any(
            (kind, profile_id) in remaining
            for kind, ids_key in (
                ("machine", "machine_profile_ids"),
                ("process", "process_profile_ids"),
            )
            for profile_id in item[ids_key]
        )
    ]
    save_printer_bundle_state(state)
    return {"removed": removed, "failed": failed}


def ensure_parent_exists(profile, known_presets):
    """Remove a parent that the local FilamentHub bundle cannot resolve."""
    normalize_local_bundle_parent(profile, known_presets)


def restore_remote_parent_for_upload(profile, preset_id, token):
    """Restore a locally omitted parent before updating the canonical preset."""
    upload = dict(profile)
    inherits = _parent_name(upload)
    if inherits and not _is_internal_fdm_parent(inherits):
        return upload

    status, body = http_get(
        "/presets/%d/export/orcaslicer.json" % int(preset_id), token=token)
    if status != 200:
        return None
    try:
        remote = json.loads(body.decode("utf-8"))
    except (TypeError, ValueError):
        return None
    if not isinstance(remote, dict):
        return None
    remote_parent = _parent_name(remote)
    if remote_parent:
        upload["inherits"] = remote_parent
    else:
        upload.pop("inherits", None)
    return upload


def ensure_filament_colour(profile):
    """Orca colours the filament (swatch and plate) by `filament_colour`, but the
    export currently fills only `default_filament_colour`. Mirror whichever is set
    into the other so the shown colour matches what was picked on FilamentHub."""
    fc = profile.get("filament_colour")
    dc = profile.get("default_filament_colour")
    if not fc and dc:
        profile["filament_colour"] = dc
    elif not dc and fc:
        profile["default_filament_colour"] = fc


# --------------------------------------------------------------------------- #
# HTTP (stdlib only). Returns (status, bytes).
# --------------------------------------------------------------------------- #
def _urlopen_authorized(request, timeout):
    with external_operation():
        return urllib.request.urlopen(request, timeout=timeout, context=_SSL_CTX)


def http_get(path, token=None):
    headers = {"Accept": "application/json", "User-Agent": "FilamentHub-OrcaPlugin/" + PLUGIN_VERSION}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API_BASE + path, headers=headers, method="GET")
    try:
        with _urlopen_authorized(req, HTTP_TIMEOUT) as resp:
            return resp.getcode(), _read_response_limited(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_RESPONSE_BYTES)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return 0, str(exc).encode("utf-8", errors="replace")


def http_post_json(path, token, payload):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json",
               "User-Agent": "FilamentHub-OrcaPlugin/" + PLUGIN_VERSION}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API_BASE + path, data=data, headers=headers, method="POST")
    try:
        with _urlopen_authorized(req, HTTP_TIMEOUT) as resp:
            return resp.getcode(), _read_response_limited(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_RESPONSE_BYTES)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return 0, str(exc).encode("utf-8", errors="replace")


def begin_filament_sync_report(token, device_fingerprint):
    """Reserve the next version on the existing device sync contour."""
    status, body = http_post_json(
        "/orcaslicer/sync-plan",
        token,
        {
            "device_fingerprint": device_fingerprint,
            "preset_type": "filament",
            "include_changes": False,
            "chunked_report": True,
        },
    )
    if status != 200:
        fh_log("sync observation plan rejected: status=%s" % status)
        return None
    try:
        response = json.loads(body.decode("utf-8")) or {}
        sync_version = response.get("sync_version")
        report_id = str(uuid.UUID(str(response.get("report_id"))))
    except (AttributeError, UnicodeDecodeError, ValueError):
        sync_version = None
        report_id = None
    if not isinstance(sync_version, int) or sync_version < 1 or not report_id:
        fh_log("sync observation plan returned no usable report")
        return None
    return sync_version, report_id


def complete_filament_sync_report(
    token,
    device_fingerprint,
    sync_version,
    report_id,
    results,
):
    """Send retry-safe chunks without exposing paths or raw exceptions."""
    chunks = [
        results[offset:offset + SYNC_REPORT_CHUNK_SIZE]
        for offset in range(0, len(results), SYNC_REPORT_CHUNK_SIZE)
    ] or [[]]
    chunk_count = len(chunks)
    retryable_statuses = {0, 408, 425, 429, 500, 502, 503, 504}
    for chunk_index, chunk_results in enumerate(chunks):
        payload = {
            "device_fingerprint": device_fingerprint,
            "sync_version": sync_version,
            "report_id": report_id,
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "results": chunk_results,
        }
        accepted = None
        last_status = 0
        for attempt in range(SYNC_REPORT_CHUNK_RETRIES):
            last_status, body = http_post_json(
                "/orcaslicer/sync-complete/chunk",
                token,
                payload,
            )
            if last_status == 200:
                try:
                    candidate = json.loads(body.decode("utf-8")) or {}
                except (AttributeError, UnicodeDecodeError, ValueError):
                    candidate = None
                if (
                    isinstance(candidate, dict)
                    and candidate.get("sync_version") == sync_version
                    and candidate.get("report_id") == report_id
                    and candidate.get("chunk_index") == chunk_index
                    and candidate.get("chunk_count") == chunk_count
                ):
                    accepted = candidate
                    break
            if (
                last_status not in retryable_statuses
                or attempt + 1 >= SYNC_REPORT_CHUNK_RETRIES
            ):
                break
            time.sleep(SYNC_REPORT_RETRY_SECONDS * (2 ** attempt))
        if accepted is None:
            fh_log(
                "sync observation chunk %d/%d rejected: status=%s"
                % (chunk_index + 1, chunk_count, last_status)
            )
            return False
        if chunk_index + 1 == chunk_count and not accepted.get("complete"):
            fh_log("sync observation report remained incomplete after final chunk")
            return False
    return True


def mark_sync_report_failed(contours, overall_status):
    """Make a failed device report explicit without hiding local sync results."""
    if overall_status == "success":
        overall_status = "warning"
    for item in contours:
        if item.get("kind") != "filament":
            continue
        if item.get("status") == "success":
            item["status"] = "warning"
        item["summary"] = "%s, %s" % (
            item.get("summary") or ui_text("summaryNothing"),
            ui_text("summaryReportFailed"),
        )
        break
    return overall_status


def _bridge_retry_after_seconds(headers):
    """Read how long the server asked this adapter to wait, in seconds.

    FilamentHub answers a throttled bridge with a numeric Retry-After, so the
    HTTP-date form is not parsed: an unreadable value simply leaves the caller
    on its own backoff.
    """
    raw_value = headers.get("Retry-After") if headers is not None else None
    try:
        return max(0.0, float(raw_value))
    except (TypeError, ValueError):
        return None


def http_post_bridge_json(path, bridge_token, payload):
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "FilamentHub-OrcaPlugin/" + PLUGIN_VERSION,
        "X-FilamentHub-Bridge-Token": bridge_token,
    }
    req = urllib.request.Request(API_BASE + path, data=data, headers=headers, method="POST")
    try:
        with _urlopen_authorized(req, HTTP_TIMEOUT) as resp:
            return resp.getcode(), _read_response_limited(resp), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_RESPONSE_BYTES), _bridge_retry_after_seconds(exc.headers)
    except (OSError, ValueError, urllib.error.URLError):
        return 0, b"", None


def http_get_bridge_json(path, bridge_token):
    headers = {
        "Accept": "application/json",
        "User-Agent": "FilamentHub-OrcaPlugin/" + PLUGIN_VERSION,
        "X-FilamentHub-Bridge-Token": bridge_token,
    }
    req = urllib.request.Request(API_BASE + path, headers=headers, method="GET")
    try:
        with _urlopen_authorized(req, HTTP_TIMEOUT) as resp:
            return resp.getcode(), _read_response_limited(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_RESPONSE_BYTES)
    except (OSError, ValueError, urllib.error.URLError):
        return 0, b""


def _http_delete_bridge(path, bridge_token, allow_retired_generation=False):
    headers = {
        "Accept": "application/json",
        "User-Agent": "FilamentHub-OrcaPlugin/" + PLUGIN_VERSION,
        "X-FilamentHub-Bridge-Token": bridge_token,
    }
    req = urllib.request.Request(API_BASE + path, headers=headers, method="DELETE")
    try:
        opener = (
            urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=_SSL_CTX)
            if allow_retired_generation
            else _urlopen_authorized(req, HTTP_TIMEOUT)
        )
        with opener as resp:
            return resp.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError, ValueError, urllib.error.URLError):
        return 0


def http_delete_bridge(path, bridge_token):
    return _http_delete_bridge(path, bridge_token)


_BAMBU_REVOKE_LOCK = threading.RLock()


def _valid_fresh_bridge_token(bridge_token):
    return (
        isinstance(bridge_token, str)
        and bridge_token.startswith("fhpb_")
        and len(bridge_token) <= 256
    )


def _load_pending_bambu_revokes(now=None):
    """Read bounded compensation state without exposing tokens to diagnostics."""
    now = time.time() if now is None else float(now)
    try:
        if os.path.getsize(BAMBU_REVOKE_FILE) > BAMBU_REVOKE_STATE_MAX_BYTES:
            return []
        with open(BAMBU_REVOKE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, TypeError, ValueError):
        return []
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return []
    entries = []
    seen = set()
    for raw in payload.get("pending") or []:
        if not isinstance(raw, dict):
            continue
        token = raw.get("token")
        created_at = raw.get("created_at")
        next_retry_at = raw.get("next_retry_at")
        attempts = raw.get("attempts")
        if (
            not _valid_fresh_bridge_token(token)
            or token in seen
            or isinstance(created_at, bool)
            or not isinstance(created_at, (int, float))
            or not 0 < created_at < float("inf")
            or isinstance(next_retry_at, bool)
            or not isinstance(next_retry_at, (int, float))
            or not 0 <= next_retry_at < float("inf")
            or isinstance(attempts, bool)
            or not isinstance(attempts, int)
            or not 0 <= attempts <= 10000
        ):
            continue
        seen.add(token)
        entries.append({
            "token": token,
            "created_at": float(created_at),
            "next_retry_at": float(next_retry_at),
            "attempts": attempts,
        })
        if len(entries) >= BAMBU_REVOKE_MAX_PENDING:
            break
    return entries


def _write_pending_bambu_revokes(entries):
    """Persist only exact fresh tokens plus bounded retry metadata.

    This is a narrow lifecycle compensation, so it intentionally uses the
    unchecked atomic writer after validating every field above. It never stores
    a caller-supplied endpoint, printer address, access code or account token.
    """
    payload = {"version": 1, "pending": entries[:BAMBU_REVOKE_MAX_PENDING]}
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    _write_bytes_atomic_unchecked(BAMBU_REVOKE_FILE, encoded, mode=0o600)


def queue_fresh_bambu_revoke(bridge_token, now=None, attempts=None):
    if not _valid_fresh_bridge_token(bridge_token):
        return False
    now = time.time() if now is None else float(now)
    attempt_count = BAMBU_REVOKE_ATTEMPTS if attempts is None else int(attempts)
    attempt_count = min(max(attempt_count, 0), 10000)
    with _BAMBU_REVOKE_LOCK:
        entries = _load_pending_bambu_revokes(now)
        existing = next(
            (item for item in entries if item["token"] == bridge_token), None
        )
        if existing is None:
            if len(entries) >= BAMBU_REVOKE_MAX_PENDING:
                return False
            existing = {
                "token": bridge_token,
                "created_at": now,
                "next_retry_at": now + BAMBU_REVOKE_BACKOFF_INITIAL_SECONDS,
                "attempts": attempt_count,
            }
            entries.append(existing)
        else:
            existing["attempts"] = max(existing["attempts"], attempt_count)
        try:
            _write_pending_bambu_revokes(entries)
        except OSError:
            return False
    wake_pending_bambu_revoke_scheduler()
    return True


def can_queue_fresh_bambu_revoke(now=None):
    now = time.time() if now is None else float(now)
    with _BAMBU_REVOKE_LOCK:
        return len(_load_pending_bambu_revokes(now)) < BAMBU_REVOKE_MAX_PENDING


def discard_pending_bambu_revoke(bridge_token, now=None):
    if not _valid_fresh_bridge_token(bridge_token):
        return False
    now = time.time() if now is None else float(now)
    with _BAMBU_REVOKE_LOCK:
        entries = _load_pending_bambu_revokes(now)
        kept = [item for item in entries if item["token"] != bridge_token]
        if len(kept) == len(entries):
            return False
        try:
            _write_pending_bambu_revokes(kept)
        except OSError:
            return False
    return True


def _try_revoke_fresh_bridge_token(bridge_token, authorize=None):
    status = 0
    for _attempt in range(BAMBU_REVOKE_ATTEMPTS):
        if authorize is not None:
            authorize()
        status = _http_delete_bridge(
            "/printer-bridge/connection",
            bridge_token,
            allow_retired_generation=True,
        )
        if status in {204, 401}:
            break
    return status


def revoke_fresh_bridge_token(bridge_token):
    """Compensate one just-accepted pair even if its worker was unloaded.

    This bypass is deliberately limited to the fixed connection endpoint and a
    newly returned bridge credential. Stored/user-selected connections still
    use ``http_delete_bridge`` and cannot be removed by a retired generation.
    A failed bounded attempt is retained in private state for a later lifecycle.
    """
    if not _valid_fresh_bridge_token(bridge_token):
        return 0
    status = _try_revoke_fresh_bridge_token(bridge_token)
    if status in {204, 401}:
        discard_pending_bambu_revoke(bridge_token)
    else:
        queue_fresh_bambu_revoke(bridge_token)
    return status


def retry_pending_bambu_revokes(now=None, authorize=None):
    """Retry due exact-token compensations and merge concurrent queue writes."""
    now = time.time() if now is None else float(now)
    with _BAMBU_REVOKE_LOCK:
        snapshot = _load_pending_bambu_revokes(now)
    updates = {}
    for entry in snapshot:
        if entry["next_retry_at"] > now:
            continue
        try:
            status = _try_revoke_fresh_bridge_token(
                entry["token"], authorize=authorize
            )
        except PluginLifecycleStopped:
            break
        if status in {204, 401}:
            updates[entry["token"]] = None
            continue
        attempts = min(entry["attempts"] + BAMBU_REVOKE_ATTEMPTS, 10000)
        exponent = min(attempts // BAMBU_REVOKE_ATTEMPTS, 12)
        delay = min(
            BAMBU_REVOKE_BACKOFF_INITIAL_SECONDS * (2 ** exponent),
            BAMBU_REVOKE_BACKOFF_MAX_SECONDS,
        )
        updates[entry["token"]] = {
            **entry,
            "attempts": attempts,
            "next_retry_at": now + delay,
        }
    with _BAMBU_REVOKE_LOCK:
        current = _load_pending_bambu_revokes(now)
        merged = {item["token"]: item for item in current}
        for token, update in updates.items():
            if update is None:
                merged.pop(token, None)
            elif token in merged:
                merged[token] = update
        entries = list(merged.values())
        try:
            _write_pending_bambu_revokes(entries)
        except OSError:
            return {"retried": len(updates), "remaining": len(current)}
    return {"retried": len(updates), "remaining": len(entries)}


def _next_pending_bambu_revoke_at(now=None):
    now = time.time() if now is None else float(now)
    with _BAMBU_REVOKE_LOCK:
        entries = _load_pending_bambu_revokes(now)
    if not entries:
        return None
    return min(item["next_retry_at"] for item in entries)


class BambuRevokeScheduler:
    """Own one cancellable timer for the nearest durable compensation retry."""

    def __init__(self):
        self._lock = threading.RLock()
        self._timer = None
        self._generation = 0
        self._active = False
        self._running = False

    def _schedule_locked(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if not self._active or self._running:
            return
        retry_at = _next_pending_bambu_revoke_at()
        if retry_at is None:
            return
        generation = self._generation
        timer = threading.Timer(
            min(
                max(0.0, retry_at - time.time()),
                BAMBU_REVOKE_BACKOFF_MAX_SECONDS,
            ),
            self._fire,
            args=(generation,),
        )
        timer.name = "filamenthub-bambu-revoke"
        timer.daemon = True
        self._timer = timer
        timer.start()

    def start(self):
        with self._lock:
            if self._active:
                self._schedule_locked()
                return False
            self._active = True
            self._generation += 1
            self._schedule_locked()
            return True

    def stop(self):
        with self._lock:
            self._active = False
            self._generation += 1
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def wake(self):
        with self._lock:
            if not self._active:
                return False
            self._schedule_locked()
            return True

    def _fire(self, generation):
        with self._lock:
            if not self._active or generation != self._generation:
                return
            self._timer = None
            self._running = True
        try:
            retry_pending_bambu_revokes(
                authorize=lambda: self._authorize_retry(generation)
            )
        finally:
            with self._lock:
                self._running = False
                if self._active:
                    self._schedule_locked()

    def _authorize_retry(self, generation):
        """Authorize one DELETE start without holding the lock during I/O."""
        with self._lock:
            if not self._active or generation != self._generation:
                raise PluginLifecycleStopped(
                    "Bambu revoke scheduler generation has stopped"
                )


BAMBU_REVOKE_SCHEDULER = BambuRevokeScheduler()


def wake_pending_bambu_revoke_scheduler():
    """Reschedule only while this plugin lifecycle remains loaded."""
    runtime_lock = globals().get("_PLUGIN_RUNTIME_LOCK")
    if runtime_lock is None:
        return False
    with runtime_lock:
        if not globals().get("_PLUGIN_RUNTIME_ACTIVE", False):
            return False
        return BAMBU_REVOKE_SCHEDULER.wake()


def http_post_file(path, token, file_path, field="file", file_name=""):
    """Send one file to FilamentHub the way a browser upload would.

    The G-code never passes through the page: it goes from this machine straight
    to the server, so a 25 MB slice costs nothing in the WebView.
    """
    ensure_worker_generation_active()
    boundary = "----FilamentHub" + secrets.token_hex(16)
    name = file_name or os.path.basename(file_path)
    crlf = chr(13) + chr(10)
    with open(file_path, "rb") as fh:
        content = fh.read()
    head = (
        "--" + boundary + crlf
        + 'Content-Disposition: form-data; name="' + field + '"; filename="' + name + '"' + crlf
        + "Content-Type: application/octet-stream" + crlf + crlf
    )
    tail = crlf + "--" + boundary + "--" + crlf
    body = head.encode("utf-8") + content + tail.encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "multipart/form-data; boundary=" + boundary,
        "User-Agent": "FilamentHub-OrcaPlugin/" + PLUGIN_VERSION,
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API_BASE + path, data=body, headers=headers, method="POST")
    try:
        with _urlopen_authorized(req, HTTP_TIMEOUT * 4) as resp:
            return resp.getcode(), _read_response_limited(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_RESPONSE_BYTES)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return 0, str(exc).encode("utf-8", errors="replace")


def _preset_scalar(value):
    """Return one stable Orca identity value from scalar/list config options."""
    if isinstance(value, (list, tuple)):
        value = next((item for item in value if item not in (None, "")), "")
    return str(value or "").strip()


def _compatibility_strings(value):
    """Project Orca compatibility options onto the backend list contract."""
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        return None
    normalized = []
    for item in values:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if item and item not in normalized:
            normalized.append(item)
    return normalized or None


def _compatibility_condition(value):
    """Project Orca's scalar/vector host representations onto one condition."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _http_error_shape(body):
    """Return validation locations/types without logging rejected profile data."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return ""
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, dict):
        code = detail.get("code")
        return str(code)[:100] if isinstance(code, str) else ""
    if not isinstance(detail, list):
        return ""
    summaries = []
    for item in detail[:5]:
        if not isinstance(item, dict):
            continue
        location = item.get("loc")
        error_type = item.get("type")
        if not isinstance(location, (list, tuple)) or not isinstance(error_type, str):
            continue
        path = ".".join(str(part) for part in location)
        summaries.append("%s:%s" % (path[:160], error_type[:80]))
    return ", ".join(summaries)


def _preset_config_value(preset, key):
    try:
        return preset.config_value(key)
    except Exception:
        return None


def _profile_settings_fingerprint(settings):
    """Hash a sanitized technical delta for conservative server matching."""
    try:
        reduced = {
            key: value
            for key, value in settings.items()
            if key not in {"bundle_id", "fhub_id", "fhub_source", "updated_at"}
        }
        blob = json.dumps(
            reduced,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
    except Exception:
        return ""


class PrinterObservationSnapshot(list):
    """A partial host read must never retire previously known connections."""

    complete = False


def observe_printer_presets():
    """What OrcaSlicer knows about the machines this person has (UI thread —
    reads preset_bundle). Two kinds of entry, and printhost_apikey is in neither:

    * every saved user preset, including distinct endpoints/names;
    * visible system presets. Orca marks the models enabled by the person in its
      setup separately from the rest of each vendor bundle, so visibility is the
      evidence that a stock machine belongs in the user's workspace.
    """
    observed_connections = PrinterObservationSnapshot()
    identity_items = []
    identity_observations = []
    try:
        bundle = orca.host.preset_bundle()
        # The preset selected right now: the site can then offer the machine the
        # person is actually slicing on instead of asking them to pick again.
        try:
            current_name = bundle.current_printer_preset().name or ""
        except Exception:
            current_name = ""
        printers = bundle.printers
        for i in range(printers.size()):
            preset = printers.preset(i)
            model = _preset_scalar(_preset_config_value(preset, "printer_model"))
            try:
                is_user = bool(preset.is_user())
            except Exception:
                is_user = False
            host = _preset_config_value(preset, "print_host") if is_user else ""
            if not model and not host:
                continue
            is_current = preset.name == current_name
            try:
                is_system = bool(preset.is_system)
            except Exception:
                is_system = not is_user
            try:
                is_visible = bool(preset.is_visible)
            except Exception:
                # Older hosts did not expose visibility. Keep the selected
                # profile working there without treating an entire vendor
                # bundle as the user's printer list.
                is_visible = False
            observation = {
                "preset_name": str(preset.name or "")[:200],
                "printer_settings_id": _preset_scalar(
                    _preset_config_value(preset, "printer_settings_id")
                    or _preset_config_value(preset, "setting_id")
                )[:200],
                "inherits": _preset_scalar(_preset_config_value(preset, "inherits"))[:200],
                "printer_model": model[:200],
                "nozzle_diameter": _preset_scalar(
                    _preset_config_value(preset, "nozzle_diameter")
                    or _preset_config_value(preset, "printer_variant")
                )[:20],
                "vendor_id": str(getattr(preset, "bundle_id", "") or "")[:100],
                "profile_fingerprint": None,
                "print_host": _preset_scalar(host)[:500],
                "host_type": _preset_scalar(_preset_config_value(preset, "host_type"))[:50],
                "is_system": is_system,
                "is_visible": is_visible,
                "is_current": is_current,
            }
            if is_user:
                try:
                    analysis = analyze_user_profile(printers, preset, "machine")
                except Exception:
                    analysis = None
                if analysis is not None:
                    identity_items.append({
                        "name": str(preset.name or ""),
                        "locator": _local_profile_locator(
                            preset, "machine", preset.name
                        ),
                        # Connection keys were already removed by the analysis;
                        # changing an IP therefore preserves this identity.
                        "settings": analysis["settings"],
                    })
                    identity_observations.append(observation)
                    observation["inherits"] = analysis["inherits"][:200]
                    if analysis["parent_vendor_id"]:
                        observation["vendor_id"] = analysis["parent_vendor_id"][:100]
                    observation["has_technical_changes"] = (
                        analysis["has_technical_changes"]
                        if analysis["parent_resolved"]
                        else None
                    )
                    if (
                        analysis["parent_resolved"]
                        and analysis["has_technical_changes"]
                    ):
                        observation["profile_fingerprint"] = (
                            _profile_settings_fingerprint(analysis["settings"]) or None
                        )
            if (
                observation["print_host"]
                or is_user
                or is_current
                or (is_system and is_visible)
            ):
                # A user may have several physical printers of one model. Each
                # endpoint or named user profile is its own observation and must
                # survive the sync. A visible stock profile represents a model
                # explicitly enabled in Orca's setup, not every vendor preset.
                observed_connections.append(observation)
        if identity_items:
            account_id, identity_items, registry_saved = (
                reconcile_local_profile_identities(
                    "machine", identity_items, authoritative=True
                )
            )
            if registry_saved:
                for observation, identity in zip(
                    identity_observations, identity_items
                ):
                    observation["connection_ref"] = local_profile_external_id(
                        account_id, identity["local_profile_id"]
                    )[:120]
        observed_connections.complete = True
    except Exception as exc:
        fh_log("printer observation scan failed: %s" % exc)
    return observed_connections


def _bambu_host_hint(value):
    """Return only a host name/IP from Orca's local print_host setting."""
    raw = _preset_scalar(value).strip()
    if not raw or len(raw) > 500 or any(ch in raw for ch in "\\\r\n?#@"):
        return ""
    try:
        parsed = urllib.parse.urlsplit(
            raw if "://" in raw else "//" + raw,
            allow_fragments=False,
        )
        if parsed.username or parsed.password or parsed.path not in {"", "/"}:
            return ""
        host = parsed.hostname or ""
    except (TypeError, ValueError):
        return ""
    host = host.strip().strip("[]").rstrip(".")
    if not host or len(host) > 253 or any(ch in host for ch in "/\\?#@"):
        return ""
    return host


def bambu_host_candidates(observations, context, physical_printer_id):
    """Select bounded, local-only Bambu address hints for one physical printer.

    A server binding may identify the exact Orca preset. If it cannot, only the
    currently selected printer preset is offered as a convenience. Addresses
    remain inside the host-owned local dialog and are never posted to FilamentHub.
    """
    bindings = context.get("bindings") if isinstance(context, dict) else []
    bound_refs = {
        item.get("connection_ref")
        for item in bindings or []
        if isinstance(item, dict)
        and item.get("status") == "bound"
        and item.get("physical_printer_id") == physical_printer_id
        and isinstance(item.get("connection_ref"), str)
    }
    observations = [item for item in observations or [] if isinstance(item, dict)
                    and (not item.get("host_type") or item.get("host_type") == "bambu")]
    selected = [
        item for item in observations
        if item.get("connection_ref") in bound_refs and _bambu_host_hint(item.get("print_host"))
    ]
    if not selected:
        selected = [
            item for item in observations
            if item.get("is_current") is True and _bambu_host_hint(item.get("print_host"))
        ]
    candidates = []
    seen = set()
    for item in selected:
        host = _bambu_host_hint(item.get("print_host"))
        if not host or host.lower() in seen:
            continue
        seen.add(host.lower())
        candidates.append({
            "host": host,
            "label": str(
                item.get("preset_name") or item.get("printer_model") or host
            )[:200],
        })
        if len(candidates) >= 16:
            break
    return candidates


_DISCOVERY_SERVICES = {"_moonraker._tcp.local": "moonraker", "_octoprint._tcp.local": "octoprint"}
_DISCOVERY_LIMIT = 64


def _discovery_address(value):
    try:
        address = ipaddress.ip_address(value)
        lan = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")
        if address.version == 4 and any(address in ipaddress.ip_network(net) for net in lan) and not (
            address.is_multicast or address.is_unspecified or address.is_loopback
        ):
            return str(address)
    except ValueError:
        pass
    return ""


def _bambu_announcement(packet, sender):
    """Advertisements are local hints, never authenticated device identity."""
    if len(packet) > 8192 or not _discovery_address(sender):
        return None
    text = packet.decode("utf-8", errors="replace")
    if not text.splitlines() or text.splitlines()[0].upper() not in {"NOTIFY * HTTP/1.1", "HTTP/1.1 200 OK"}:
        return None
    headers = {}
    for line in text.splitlines()[1:]:
        key, separator, value = line.partition(":")
        if separator:
            key = key.strip().lower()
            if key in headers:
                return None
            headers[key] = value.strip()
    if not (headers.get("devname.bambu.com") or "bambulab" in headers.get("nt", "").lower()
            or "bambulab" in headers.get("st", "").lower()):
        return None
    marker = headers.get("nt", headers.get("st", "")).lower()
    if marker and not re.fullmatch(
        r"urn:bambulab-com:device:3dprinter:\d+",
        marker,
    ):
        return None
    host = _bambu_host_hint(headers.get("location", sender))
    # Never follow a Location advertised on behalf of another host.
    if host != sender:
        return None
    serial = _normalized_bambu_serial(headers.get("usn", "").removeprefix("uuid:").split("::")[0])
    name = headers.get("devname.bambu.com", "Bambu Lab")
    if any(ord(ch) < 32 for ch in name):
        return None
    return {"provider": "bambu", "host": host, "serial": serial,
            "label": name[:200], "source": "network"}


def _dns_name(packet, offset):
    labels, visited, end = [], set(), None
    for _ in range(128):
        if offset >= len(packet) or offset in visited:
            raise ValueError("invalid DNS name")
        visited.add(offset)
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise ValueError("invalid DNS pointer")
            end = end or offset + 2
            offset = ((length & 63) << 8) | packet[offset + 1]
            continue
        if length > 63 or offset + length + 1 > len(packet):
            raise ValueError("invalid DNS label")
        offset += 1
        if not length:
            name = ".".join(labels)
            if len(name) > 253:
                raise ValueError("DNS name too long")
            return name, end or offset
        label = packet[offset:offset + length].decode("utf-8", errors="strict")
        if any(ord(ch) < 32 for ch in label):
            raise ValueError("invalid DNS text")
        labels.append(label)
        offset += length
    raise ValueError("DNS compression limit")


def _mdns_records(packet):
    if not 12 <= len(packet) <= 9000:
        return []
    try:
        _id, flags, questions, answers, authority, additional = struct.unpack("!6H", packet[:12])
        if not flags & 0x8000 or flags & 0x000F or questions > 64 or answers + authority + additional > 256:
            return []
        offset, records = 12, []
        for _ in range(questions):
            _name, offset = _dns_name(packet, offset)
            offset += 4
        for _ in range(answers + authority + additional):
            name, offset = _dns_name(packet, offset)
            kind, klass, ttl, size = struct.unpack_from("!HHIH", packet, offset)
            offset += 10
            end = offset + size
            if end > len(packet):
                return []
            value = None
            if klass & 0x7FFF == 1 and ttl:
                if kind == 12:
                    value, consumed = _dns_name(packet, offset)
                    if consumed > end:
                        return []
                elif kind == 33 and size >= 7:
                    _priority, _weight, port = struct.unpack_from("!HHH", packet, offset)
                    target, consumed = _dns_name(packet, offset + 6)
                    if consumed > end:
                        return []
                    value = (target.lower(), port)
                elif kind == 1 and size == 4:
                    value = socket.inet_ntoa(packet[offset:end])
                elif kind == 16:
                    value, cursor = {}, offset
                    while cursor < end:
                        length = packet[cursor]
                        cursor += 1
                        if cursor + length > end:
                            return []
                        item = packet[cursor:cursor + length].decode("utf-8", errors="replace")
                        key, separator, val = item.partition("=")
                        if separator:
                            value[key.lower()] = val
                        cursor += length
            if value is not None:
                records.append((name.lower(), kind, value))
            offset = end
        return records
    except (ValueError, UnicodeError, struct.error, OSError):
        return []


def _mdns_query(names):
    questions = []
    for name, kind in names:
        labels = name.rstrip(".").split(".")
        encoded = [label.encode("utf-8") for label in labels]
        if not encoded or any(not label or len(label) > 63 for label in encoded):
            continue
        questions.append(b"".join(bytes([len(label)]) + label for label in encoded)
                         + b"\0" + struct.pack("!HH", kind, 0x8001))
    return struct.pack("!6H", 0, 0, len(questions), 0, 0, 0) + b"".join(questions)


def _mdns_candidates(records):
    services, targets, addresses, texts = {}, {}, {}, {}
    for name, kind, value in records:
        if kind == 12 and name in _DISCOVERY_SERVICES:
            services[value.lower()] = _DISCOVERY_SERVICES[name]
        elif kind == 33:
            targets[name] = value
        elif kind == 1 and _discovery_address(value):
            addresses[name] = value
        elif kind == 16:
            texts[name] = value
    candidates = []
    for name, provider in services.items():
        target, port = targets.get(name, ("", 0))
        host = addresses.get(target)
        if not host or not 0 < port <= 65535:
            continue
        txt = texts.get(name, {})
        path = txt.get("route_prefix" if provider == "moonraker" else "path", "/") or "/"
        if provider == "moonraker" and not path.startswith("/"):
            path = "/" + path
        if not path.startswith("/") or path.startswith("//") or any(ch in path for ch in "\\?#@") or any(ord(ch) < 32 for ch in path):
            path = "/"
        scheme = "http"
        https_port = txt.get("https_port", "")
        if provider == "moonraker" and https_port.isdigit() and 0 < int(https_port) <= 65535:
            scheme, port = "https", int(https_port)
        label = name.split("._", 1)[0][:200]
        candidates.append({"provider": provider, "host": host, "hostname": target,
                           "print_host": "%s://%s:%s%s" % (scheme, host, port, path),
                           "label": label, "source": "network"})
    return candidates[:_DISCOVERY_LIMIT]


def discover_lan_printers(duration=4.0):
    """One bounded local search; no subnet sweep, credentials or device commands."""
    sockets, records, found = [], {}, {}
    record_count = 0
    complete = True
    deadline = time.monotonic() + min(5.0, max(0.1, duration))
    try:
        ensure_worker_generation_active()
        try:
            with external_operation():
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sockets.append((sock, "bambu"))
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("", 2021))
                sock.setblocking(False)
        except OSError:
            complete = False
            if sockets:
                sockets.pop()[0].close()
        try:
            with external_operation():
                interfaces = sorted({item[4][0] for item in socket.getaddrinfo(
                    socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM,
                ) if _discovery_address(item[4][0])})[:8]
        except OSError:
            interfaces = []
        for interface in interfaces or ["0.0.0.0"]:
            sock = None
            try:
                with external_operation():
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.bind((interface, 0))
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface))
                    sock.setblocking(False)
                    sock.sendto(_mdns_query([(name, 12) for name in _DISCOVERY_SERVICES]), ("224.0.0.251", 5353))
                sockets.append((sock, "mdns"))
            except OSError:
                complete = False
                if sock is not None:
                    sock.close()
        asked, packets = set(), 0
        while sockets and time.monotonic() < deadline and packets < 512:
            ensure_worker_generation_active()
            ready, _, _ = select.select([item[0] for item in sockets], [], [], min(0.2, max(0, deadline - time.monotonic())))
            for sock in ready:
                packets += 1
                try:
                    with external_operation():
                        packet, sender = sock.recvfrom(9001)
                except BlockingIOError:
                    continue
                if not _discovery_address(sender[0]):
                    continue
                if next(kind for candidate, kind in sockets if candidate is sock) == "bambu":
                    item = _bambu_announcement(packet, sender[0])
                    if item and len(found) < _DISCOVERY_LIMIT:
                        found[(item["provider"], item["serial"] or item["host"])] = item
                else:
                    if sender[1] != 5353:
                        continue
                    new_records = _mdns_records(packet)
                    accepted = new_records[:max(0, 1024 - record_count)]
                    records.setdefault((sock, sender[0]), []).extend(accepted)
                    record_count += len(accepted)
                    follow = []
                    for name, kind, value in new_records:
                        wanted = []
                        if kind == 12 and name in _DISCOVERY_SERVICES:
                            wanted = [(value, 33), (value, 16)]
                        elif kind == 33 and any(name.endswith("." + service) for service in _DISCOVERY_SERVICES):
                            wanted = [(value[0], 1)]
                        for question in wanted:
                            if (sock, question) not in asked and len(asked) < 64:
                                asked.add((sock, question))
                                follow.append(question)
                    if follow:
                        with external_operation():
                            sock.sendto(_mdns_query(follow), ("224.0.0.251", 5353))
        for batch in records.values():
            for item in _mdns_candidates(batch):
                if len(found) < _DISCOVERY_LIMIT:
                    found[(item["provider"], item["print_host"])] = item
        return list(found.values()), complete and packets < 512 and len(found) < _DISCOVERY_LIMIT and record_count < 1024
    except OSError:
        for batch in records.values():
            for item in _mdns_candidates(batch):
                if len(found) < _DISCOVERY_LIMIT:
                    found[(item["provider"], item["print_host"])] = item
        return list(found.values()), False
    finally:
        for sock, _kind in sockets:
            sock.close()


def observe_local_moonraker_connections(observations):
    """Collect local-only Moonraker access for observed user machine presets.

    The server receives the stable ``connection_ref`` through the normal printer
    observation payload.  The endpoint and API key stay in this in-memory list
    and are never added to that payload or written by FilamentHub.
    """
    by_preset = {}
    for observation in observations or []:
        connection_ref = observation.get("connection_ref")
        host = _preset_scalar(observation.get("print_host"))
        name = str(observation.get("preset_name") or "")
        if connection_ref and host:
            by_preset.setdefault((name, host), []).append(connection_ref)

    candidates = {}
    ambiguous = set()
    try:
        printers = orca.host.preset_bundle().printers
        for index in range(printers.size()):
            preset = printers.preset(index)
            try:
                if not bool(preset.is_user()):
                    continue
            except Exception:
                continue
            host = _preset_scalar(_preset_config_value(preset, "print_host"))
            host_type = _preset_scalar(
                _preset_config_value(preset, "host_type")
            ).lower()
            printer_agent = _preset_scalar(
                _preset_config_value(preset, "printer_agent")
            ).lower()
            if not host or "moonraker" not in {host_type, printer_agent}:
                continue
            refs = by_preset.get((str(preset.name or ""), host)) or []
            if len(refs) != 1:
                continue
            connection_ref = refs[0]
            candidate = {
                "connection_ref": connection_ref,
                "print_host": host,
                "api_key": _preset_scalar(
                    _preset_config_value(preset, "printhost_apikey")
                ),
            }
            if connection_ref in candidates and candidates[connection_ref] != candidate:
                ambiguous.add(connection_ref)
            else:
                candidates[connection_ref] = candidate
    except Exception as exc:
        fh_log("local Moonraker scan failed: %s" % exc)
    return [
        candidate
        for connection_ref, candidate in candidates.items()
        if connection_ref not in ambiguous
    ]


_LOCAL_SETUP_LOCK = threading.RLock()


def _local_setup_config():
    path = os.path.join(os.path.dirname(AUTH_FILE), ".fh_printer_connections.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.loads(handle.read(1024 * 1024))
    except FileNotFoundError:
        value = {"version": 1, "connections": []}
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(
        value.get("connections"), list,
    ) or len(value["connections"]) > 256 or not all(
        isinstance(item, dict) for item in value["connections"]
    ):
        raise ValueError("Invalid local printer connection store")
    for item in value["connections"]:
        identity = item.get("device_identity")
        if (
            not all(isinstance(item.get(key), str) and item[key] for key in (
                "account_scope", "connection_ref", "print_host",
            ))
            or type(item.get("physical_printer_id")) is not int
            or item["physical_printer_id"] < 1
            or not isinstance(item.get("api_key", ""), str)
            or (identity is not None and (
                not isinstance(identity, dict)
                or identity.get("kind") != "moonraker_instance"
                or not isinstance(identity.get("token"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", identity["token"])
            ))
        ):
            raise ValueError("Invalid local printer connection store")
    return path, value


def printer_setup_context(token):
    source = plugin_source_instance_id()
    status, value = _filamenthub_json_get(
        "/orcaslicer/printer-connections/setup-context?source_instance_id="
        + urllib.parse.quote(source, safe=""), token,
    )
    if status != 200 or not isinstance(value, dict) or value.get("source_instance_id") != source:
        raise ValueError("auth" if status in {401, 403} else "setup_context")
    key = value.get("discovery_key")
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key) or not isinstance(
        value.get("bindings"), list,
    ):
        raise ValueError("setup_context")
    value["account_scope"] = hashlib.sha256((account_origin() + "\0" + key).encode()).hexdigest()
    return value


def setup_inventory_linked(context, connection_ref, snapshot):
    if not snapshot or snapshot.get("spoolman_support") != "pull":
        return False
    digest = snapshot.get("inventory_key_digest")
    return bool(digest and any(
        item.get("connection_ref") == connection_ref and item.get("status") == "bound"
        and item.get("inventory_key_digest") == digest for item in context["bindings"]
    ))


def local_setup_connections(context):
    """Only this account's still-bound connections may address the local network."""
    with _LOCAL_SETUP_LOCK:
        _path, config = _local_setup_config()
    owned = {
        item.get("connection_ref"): item.get("physical_printer_id")
        for item in context["bindings"] if isinstance(item, dict) and item.get("status") == "bound"
    }
    return [
        dict(item) for item in config["connections"]
        if isinstance(item, dict) and item.get("account_scope") == context["account_scope"]
        and owned.get(item.get("connection_ref")) == item.get("physical_printer_id")
        and isinstance(item.get("physical_printer_id"), int)
    ]


def verified_local_setup_connections(token):
    # Nothing configured: do not add cloud requests to every existing HH action.
    with _LOCAL_SETUP_LOCK:
        _path, config = _local_setup_config()
    if not config["connections"]:
        return []
    context = printer_setup_context(token)
    verified = []
    for connection in local_setup_connections(context):
        expected = connection.get("device_identity")
        if not expected:
            continue
        identity = _observe_moonraker_identity(connection)
        actual = _printer_evidence_token(
            context["discovery_key"], "device", "moonraker_instance\0" + str(identity),
        ) if identity else None
        if actual != expected.get("token"):
            continue
        verified.append(connection)
    return verified


def save_local_setup_connection(context, connection, physical_printer_id, evidence):
    if not evidence.get("device_identity"):
        raise ValueError("identity_unavailable")
    with _LOCAL_SETUP_LOCK:
        path, config = _local_setup_config()
        items = [item for item in config["connections"] if not (
            item.get("account_scope") == context["account_scope"]
            and item.get("connection_ref") == connection["connection_ref"]
        )]
        if len(items) >= 256:
            raise ValueError("Local printer connection limit reached")
        items.append({
            "account_scope": context["account_scope"],
            "connection_ref": connection["connection_ref"],
            "physical_printer_id": physical_printer_id,
            "print_host": connection["print_host"], "api_key": connection.get("api_key", ""),
            "device_identity": evidence.get("device_identity"),
            "label": connection.get("label", "Moonraker"),
        })
        write_json_atomic(path, {"version": 1, "connections": items}, mode=0o600)


def probe_printer_setup(context, connection, origin):
    """Read capabilities first; absent MMU is not inferred from a failed request."""
    status, body, _error = _moonraker_json(connection, "/printer/objects/list")
    result = body.get("result")
    objects = result.get("objects") if isinstance(result, dict) else None
    if status != 200 or not isinstance(objects, list):
        raise ValueError("printer_auth" if status in {401, 403} else "unreachable")
    snapshot = read_happy_hare_snapshot(connection) if "mmu" in objects else None
    identity = _observe_moonraker_identity(connection)
    if origin == "local_manual" and not identity:
        raise ValueError("identity_unavailable")
    evidence = {
        "source_instance_id": context["source_instance_id"],
        "connection_ref": connection["connection_ref"], "origin": origin,
        "provider": "moonraker",
        "endpoint_token": _connection_endpoint_token(
            context["discovery_key"], connection["print_host"], "moonraker",
        ),
    }
    if identity:
        evidence["device_identity"] = {
            "kind": "moonraker_instance",
            "token": _printer_evidence_token(
                context["discovery_key"], "device", "moonraker_instance\0" + identity,
            ),
        }
    return evidence, snapshot


def _moonraker_base_url(value):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Moonraker address is empty")
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urllib.parse.urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)*/?", parsed.path)
        or any(part in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise ValueError("Moonraker address or route prefix is invalid")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Moonraker port is invalid") from exc
    host = parsed.hostname
    if ":" in host:
        host = "[" + host + "]"
    return "%s://%s%s%s" % (
        parsed.scheme,
        host,
        (":" + str(port)) if port is not None else "",
        parsed.path.rstrip("/"),
    )


def _moonraker_json(connection, path, payload=None, timeout=None):
    """Call only the endpoint read from Orca's local machine preset."""
    base_url = _moonraker_base_url(connection.get("print_host"))
    headers = {
        "Accept": "application/json",
        "User-Agent": "FilamentHub-OrcaPlugin/" + PLUGIN_VERSION,
    }
    api_key = str(connection.get("api_key") or "")
    if api_key:
        headers["X-Api-Key"] = api_key
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        base_url + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with _urlopen_authorized(
            request,
            min(HTTP_TIMEOUT, timeout if timeout is not None else 10),
        ) as response:
            status = response.getcode()
            body = _read_response_limited(response)
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read(MAX_RESPONSE_BYTES)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return 0, {}, str(exc)
    try:
        decoded = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, ValueError):
        return status, {}, "invalid JSON"
    return status, decoded if isinstance(decoded, dict) else {}, ""


_HH_ARRAY_FIELDS = (
    "gate_status",
    "gate_material",
    "gate_color",
    "gate_temperature",
    "gate_spool_id",
    "gate_spool_rfid",
)


def _physical_tag_uid(value):
    """Normalize raw provider evidence without assigning provider ownership."""
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[\s:_.-]+", "", value).strip().upper()
    if normalized.startswith("0X"):
        normalized = normalized[2:]
    if (
        len(normalized) < 2
        or len(normalized) > 64
        or len(normalized) % 2
        or re.fullmatch(r"[0-9A-F]+", normalized) is None
    ):
        return None
    return normalized


def _happy_hare_inventory_digest(connection):
    status, body, _error = _moonraker_json(connection, "/server/config")
    result = body.get("result") if status == 200 and isinstance(body, dict) else None
    config = result.get("config") if isinstance(result, dict) else None
    spoolman = config.get("spoolman") if isinstance(config, dict) else None
    server = spoolman.get("server") if isinstance(spoolman, dict) else None
    if not isinstance(server, str):
        return None
    try:
        parsed = urllib.parse.urlsplit(server)
    except ValueError:
        return None
    own_sites = {SITE_URL}
    if account_origin() == PROD_SITE_URL:
        own_sites.update(PROD_SITE_URLS.values())
    if not any(
        (parsed.scheme, parsed.netloc) == (site.scheme, site.netloc)
        for site in map(urllib.parse.urlsplit, own_sites)
    ):
        return None
    match = re.fullmatch(r"/api/v1/spool_compat/([A-Za-z0-9_-]+)/*", parsed.path)
    if not match or parsed.query or parsed.fragment:
        return None
    return hashlib.sha256(match.group(1).encode()).hexdigest()


def read_happy_hare_snapshot(connection):
    """Read one complete Happy Hare topology through Moonraker, without writes."""
    query_status, query, query_error = _moonraker_json(
        connection,
        "/printer/objects/query",
        {
            "objects": {
                "mmu": [
                    "num_gates",
                    "gate_status",
                    "gate_material",
                    "gate_color",
                    "gate_temperature",
                    "gate_spool_id",
                    "gate_spool_rfid",
                    "spoolman_support",
                    "has_bypass",
                    "tool",
                    "gate",
                    "filament_pos",
                ],
                "print_stats": ["state"],
            }
        },
    )
    if query_status != 200:
        raise RuntimeError(query_error or "Moonraker query HTTP %s" % query_status)
    result = query.get("result")
    status_map = result.get("status") if isinstance(result, dict) else None
    mmu = status_map.get("mmu") if isinstance(status_map, dict) else None
    if not isinstance(mmu, dict):
        raise ValueError("Happy Hare object 'mmu' is unavailable")

    arrays = {}
    lengths = set()
    for key in _HH_ARRAY_FIELDS:
        value = mmu.get(key)
        if value is None:
            arrays[key] = None
            continue
        if not isinstance(value, list):
            raise ValueError("Happy Hare %s is not an array" % key)
        arrays[key] = value
        lengths.add(len(value))

    raw_count = mmu.get("num_gates")
    if isinstance(raw_count, bool):
        raw_count = None
    try:
        gate_count = int(raw_count) if raw_count is not None else None
    except (TypeError, ValueError):
        gate_count = None
    if gate_count is None:
        if len(lengths) != 1:
            raise ValueError("Happy Hare gate count cannot be determined safely")
        gate_count = next(iter(lengths))
    if gate_count < 1 or gate_count > 256:
        raise ValueError("Happy Hare gate count is outside 1..256")
    if any(length != gate_count for length in lengths):
        raise ValueError("Happy Hare gate arrays disagree with num_gates")

    def value_at(key, index, default):
        values = arrays.get(key)
        return values[index] if values is not None else default

    gates = []
    actual_spool_ids = []
    for gate in range(gate_count):
        try:
            hh_status = int(value_at("gate_status", gate, -1))
        except (TypeError, ValueError):
            hh_status = -1
        if hh_status not in {-1, 0, 1, 2}:
            hh_status = -1
        material = str(value_at("gate_material", gate, "") or "")[:50]
        color = str(value_at("gate_color", gate, "") or "").lstrip("#").upper()
        if not re.fullmatch(r"[0-9A-F]{6}", color):
            color = ""
        try:
            temperature = max(0, int(value_at("gate_temperature", gate, 0) or 0))
        except (TypeError, ValueError):
            temperature = 0
        try:
            spool_id = int(value_at("gate_spool_id", gate, -1))
        except (TypeError, ValueError):
            spool_id = -1
        actual_spool_ids.append(spool_id if spool_id > 0 else None)
        rfid_uid = _physical_tag_uid(value_at("gate_spool_rfid", gate, ""))
        gate_item = {
            "gate": gate,
            "status": hh_status,
            "material": material,
            "color_hex": color,
            "temperature": temperature,
        }
        if rfid_uid is not None:
            gate_item["rfid_uid"] = rfid_uid
        gates.append(gate_item)

    info_status, info, _info_error = _moonraker_json(
        connection, "/printer/info"
    )
    info_result = info.get("result") if info_status == 200 else None
    hostname = (
        str(info_result.get("hostname") or "")[:200]
        if isinstance(info_result, dict)
        else ""
    )
    print_stats = (
        status_map.get("print_stats") if isinstance(status_map, dict) else None
    )
    print_state = (
        str(print_stats.get("state") or "").strip().lower()
        if isinstance(print_stats, dict)
        else ""
    )
    raw_has_bypass = mmu.get("has_bypass")
    has_bypass = raw_has_bypass if isinstance(raw_has_bypass, bool) else None
    raw_tool = mmu.get("tool")
    try:
        selected_tool = int(raw_tool) if not isinstance(raw_tool, bool) else None
    except (TypeError, ValueError):
        selected_tool = None
    raw_gate = mmu.get("gate")
    selected_gate = raw_gate if type(raw_gate) is int and -2 <= raw_gate < gate_count else None
    bypass_selected = selected_gate == -2 or selected_tool == -2
    raw_filament_pos = mmu.get("filament_pos")
    try:
        filament_pos = float(raw_filament_pos) if not isinstance(raw_filament_pos, bool) else None
    except (TypeError, ValueError):
        filament_pos = None
    if bypass_selected:
        # A selected bypass is stronger evidence than an omitted capability
        # field from an older Happy Hare build.
        has_bypass = True
    bypass = None
    if has_bypass is True:
        bypass_present = None
        if bypass_selected and filament_pos is not None and filament_pos >= 0:
            bypass_present = filament_pos > 0
        bypass = {
            "selected": bypass_selected,
            "present": bypass_present,
        }
    return {
        "gate_count": gate_count,
        "gates": gates,
        "actual_spool_ids": actual_spool_ids,
        "spool_ids_known": arrays.get("gate_spool_id") is not None,
        "tag_read_capable": arrays.get("gate_spool_rfid") is not None,
        "spoolman_support": str(mmu.get("spoolman_support") or "").strip().lower(),
        "print_state": print_state,
        "printer_hostname": hostname,
        "has_bypass": has_bypass,
        "bypass": bypass,
        "selected_gate": selected_gate,
        "filament_loaded": filament_pos > 0 if filament_pos is not None and filament_pos >= 0 else None,
        "inventory_key_digest": _happy_hare_inventory_digest(connection),
    }


def upload_happy_hare_snapshot(token, physical_printer_id, snapshot):
    payload = {
        "physical_printer_id": physical_printer_id,
        "gate_count": snapshot["gate_count"],
        "snapshot_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gates": snapshot["gates"],
        "spool_ids": snapshot.get("actual_spool_ids") if snapshot.get("spool_ids_known") else None,
        "inventory_key_digest": snapshot.get("inventory_key_digest"),
        "selected_gate": snapshot.get("selected_gate"),
        "filament_loaded": snapshot.get("filament_loaded"),
        "tag_read_capable": bool(snapshot.get("tag_read_capable")),
    }
    if isinstance(snapshot.get("has_bypass"), bool):
        payload["has_bypass"] = snapshot["has_bypass"]
    if isinstance(snapshot.get("bypass"), dict):
        payload["bypass"] = snapshot["bypass"]
    status, body = http_post_json(
        "/orcaslicer/preset-slot-sync/hh/snapshot",
        token,
        payload,
    )
    if status != 200:
        return status, {}
    try:
        result = json.loads(body.decode("utf-8")) or {}
    except (AttributeError, UnicodeDecodeError, ValueError):
        result = {}
    return status, result if isinstance(result, dict) else {}


def _filamenthub_json_get(path, token):
    status, body = http_get(path, token=token)
    if status != 200:
        return status, None
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return status, None
    return status, decoded


def _plugin_material_server_inventory(token, source_instance_id=None):
    if source_instance_id is None:
        source_instance_id = plugin_source_instance_id()
    status, context = _filamenthub_json_get(
        "/orcaslicer/preset-slot-sync/plugin-context?source_instance_id="
        + urllib.parse.quote(source_instance_id, safe=""),
        token,
    )
    if status == 401:
        return None, "auth"
    if status == 403:
        return None, "access"
    if status != 200:
        return None, "server"
    if (
        not isinstance(context, dict)
        or context.get("source_instance_id") != source_instance_id
        or not isinstance(context.get("printers"), list)
    ):
        return None, "server"
    return {
        "source_instance_id": source_instance_id,
        "printers": [
            item for item in context["printers"] if isinstance(item, dict)
        ],
    }, None


def _material_commit_context(
    token,
    source_instance_id,
    provider,
    physical_printer_id,
    material_system_id,
    commit,
):
    """Re-read and match one committed slot before a local device operation."""
    inventory, error = _plugin_material_server_inventory(
        token, source_instance_id=source_instance_id
    )
    if error or inventory is None:
        return None, None, None, error or "server"
    device = next(
        (item for item in inventory["printers"]
         if item.get("id") == physical_printer_id),
        None,
    )
    if device is None:
        return None, None, None, "connection_not_found"
    system = next(
        (
            item for item in device.get("material_systems") or []
            if isinstance(item, dict)
            and item.get("id") == material_system_id
            and item.get("provider") == provider
        ),
        None,
    )
    if system is None:
        return device, None, None, "material_system_not_found"
    slot = next(
        (
            item for item in system.get("slots") or []
            if isinstance(item, dict)
            and item.get("material_slot_id") == commit.get("materialSlotId")
        ),
        None,
    )
    if slot is None:
        return device, system, None, "slot_not_found"
    current_desired = None
    if any(slot.get(key) is not None for key in ("preset_id", "spool_id", "source_ts")):
        current_desired = {
            "presetId": slot.get("preset_id"),
            "spoolId": slot.get("spool_id"),
            "sourceTs": str(slot.get("source_ts") or "") or None,
        }
    if (
        slot.get("provider_index") != commit.get("providerIndex")
        or slot.get("assignment_revision") != commit.get("assignmentRevision")
        or current_desired != commit.get("desired")
    ):
        return device, system, slot, "stale_assignment"
    return device, system, slot, None


def _decode_json_object(body):
    try:
        value = json.loads(body.decode("utf-8")) if body else {}
    except (AttributeError, UnicodeDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _valid_immediate_material_commit(value):
    if not isinstance(value, dict) or set(value) != {
        "materialSlotId", "providerIndex", "assignmentRevision", "desired"
    }:
        return False
    if (
        type(value.get("materialSlotId")) is not int
        or value["materialSlotId"] <= 0
        or type(value.get("providerIndex")) is not int
        or not 0 <= value["providerIndex"] <= 1023
        or type(value.get("assignmentRevision")) is not int
        or value["assignmentRevision"] < 0
    ):
        return False
    desired = value.get("desired")
    if desired is None:
        return True
    if not isinstance(desired, dict) or set(desired) != {
        "presetId", "spoolId", "sourceTs"
    }:
        return False
    return (
        (desired["presetId"] is None
         or type(desired["presetId"]) is int and desired["presetId"] > 0)
        and (desired["spoolId"] is None
             or type(desired["spoolId"]) is int and desired["spoolId"] > 0)
        and (desired["sourceTs"] is None
             or isinstance(desired["sourceTs"], str)
             and 0 < len(desired["sourceTs"]) <= 64)
    )


# Compatibility name for the existing Happy Hare reconciliation path.
_happy_hare_server_inventory = _plugin_material_server_inventory


def resolve_happy_hare_connection(
    token,
    local_connections,
    physical_printer_id,
    inventory=None,
):
    """Resolve one server-owned printer to one local Orca connection.

    Stable ``connection_ref`` wins.  The only fallback is an exact hostname
    reported by Moonraker itself; display names, model names and endpoints from
    the web page are never used to guess a LAN target.
    """
    if inventory is None:
        inventory, inventory_error = _happy_hare_server_inventory(token)
        if inventory_error or inventory is None:
            return None, None, None, inventory_error or "server"
    device = next(
        (
            item
            for item in inventory["printers"]
            if item.get("id") == physical_printer_id
        ),
        None,
    )
    if device is None:
        return None, None, None, "not_found"

    local_by_ref = {}
    duplicate_refs = set()
    for connection in local_connections or []:
        connection_ref = connection.get("connection_ref")
        if not connection_ref:
            continue
        if connection_ref in local_by_ref:
            duplicate_refs.add(connection_ref)
        else:
            local_by_ref[connection_ref] = connection
    exact = []
    connection_refs = device.get("connection_refs")
    if not isinstance(connection_refs, list):
        return None, None, device, "server"
    for connection_ref in connection_refs:
        if not isinstance(connection_ref, str):
            continue
        if connection_ref in duplicate_refs:
            continue
        connection = local_by_ref.get(connection_ref)
        if connection is not None:
            exact.append(connection)
    # Different configuration refs can explicitly bind to the same endpoint.
    # They are aliases of one local connection, not competing physical devices.
    unique_exact = {}
    for item in exact:
        try:
            endpoint = _moonraker_base_url(item.get("print_host"))
        except ValueError:
            continue
        unique_exact[(endpoint, item.get("api_key") or "")] = item
    if len(unique_exact) == 1:
        connection = next(iter(unique_exact.values()))
        try:
            snapshot = read_happy_hare_snapshot(connection)
        except (RuntimeError, ValueError) as exc:
            fh_log("Happy Hare read failed for bound connection: %s" % exc)
            return None, None, device, "unreachable"
        return connection, snapshot, device, None
    if len(unique_exact) > 1:
        return None, None, device, "ambiguous_connection"
    return None, None, device, "connection_not_found"


def _desired_happy_hare_spools(physical_printer, material_system_id):
    systems = physical_printer.get("material_systems")
    if not isinstance(systems, list):
        return None
    system = next(
        (
            item
            for item in systems
            if isinstance(item, dict) and item.get("id") == material_system_id
        ),
        None,
    )
    if system is None or system.get("provider") != "happy_hare":
        return None
    desired = {}
    for slot in system.get("slots") or []:
        if not isinstance(slot, dict) or not slot.get("active", True):
            continue
        index = slot.get("provider_index")
        if not isinstance(index, int) or index < 0:
            continue
        spool_id = slot.get("spool_id")
        desired[index] = spool_id if isinstance(spool_id, int) and spool_id > 0 else None
    return desired


def _happy_hare_assignment_changes(actual_spool_ids, desired_spool_ids):
    changes = []
    for gate, actual in enumerate(actual_spool_ids):
        desired = desired_spool_ids.get(gate)
        if actual != desired:
            changes.append({
                "gate": gate,
                "actualSpoolId": actual,
                "desiredSpoolId": desired,
            })
    return changes


def _happy_hare_reconciliation_payload(
    physical_printer_id,
    material_system_id,
    connection,
    snapshot,
    expected_desired=None,
):
    connection_ref = connection.get("connection_ref")
    if not isinstance(connection_ref, str) or not connection_ref:
        return None
    actual_spool_ids = snapshot.get("actual_spool_ids") or []
    gates = []
    for gate_item in snapshot.get("gates") or []:
        gate = gate_item.get("gate") if isinstance(gate_item, dict) else None
        if not isinstance(gate, int) or gate < 0 or gate >= len(actual_spool_ids):
            return None
        gates.append({
            "gate": gate,
            "status": gate_item.get("status", -1),
            "spool_id": actual_spool_ids[gate],
        })
    if {item["gate"] for item in gates} != set(range(snapshot["gate_count"])):
        return None
    payload = {
        "source_instance_id": plugin_source_instance_id(),
        "connection_ref": connection_ref,
        "physical_printer_id": physical_printer_id,
        "material_system_id": material_system_id,
        "gate_count": snapshot["gate_count"],
        "spool_ids_known": bool(snapshot.get("spool_ids_known")),
        "gates": gates,
    }
    if expected_desired is not None:
        payload["expected_desired"] = expected_desired
    return payload


def _decode_happy_hare_reconciliation(result):
    def differences(key):
        decoded = []
        for item in result.get(key) or []:
            if not isinstance(item, dict) or not isinstance(item.get("gate"), int):
                continue
            decoded.append({
                "gate": item["gate"],
                "actualSpoolId": item.get("actual_spool_id"),
                "desiredSpoolId": item.get("desired_spool_id"),
            })
        return decoded

    import_changes = []
    for item in result.get("import_changes") or []:
        if not isinstance(item, dict) or not isinstance(item.get("gate"), int):
            continue
        import_changes.append({
            "gate": item["gate"],
            "proposedSpoolId": item.get("proposed_spool_id"),
            "desiredSpoolId": item.get("desired_spool_id"),
            "source": item.get("source"),
        })
    unresolved = []
    for item in result.get("unresolved") or []:
        if not isinstance(item, dict) or not isinstance(item.get("gate"), int):
            continue
        unresolved.append({"gate": item["gate"], "reason": item.get("reason")})
    desired_assignments = []
    for item in result.get("desired_assignments") or []:
        if not isinstance(item, dict) or not isinstance(item.get("gate"), int):
            continue
        desired_assignments.append({
            "gate": item["gate"],
            "spool_id": item.get("spool_id"),
        })
    return {
        "changes": differences("printer_changes"),
        "importChanges": import_changes,
        "unresolved": unresolved,
        "desiredAssignments": desired_assignments,
        "adoptedGates": int(result.get("adopted_gates") or 0),
    }


def request_happy_hare_reconciliation(
    token,
    operation,
    physical_printer_id,
    material_system_id,
    connection,
    snapshot,
    expected_desired=None,
):
    payload = _happy_hare_reconciliation_payload(
        physical_printer_id,
        material_system_id,
        connection,
        snapshot,
        expected_desired,
    )
    if payload is None:
        return 400, {}
    status, body = http_post_json(
        "/orcaslicer/preset-slot-sync/hh/reconciliation/" + operation,
        token,
        payload,
    )
    if status != 200:
        return status, {}
    try:
        result = json.loads(body.decode("utf-8")) or {}
    except (AttributeError, UnicodeDecodeError, ValueError):
        return status, {}
    if not isinstance(result, dict):
        return status, {}
    return status, _decode_happy_hare_reconciliation(result)


def sync_happy_hare_topologies(token, local_connections):
    """Quietly upload complete read-only HH snapshots during normal sync."""
    if not token or not local_connections:
        return 0, 0
    inventory, inventory_error = _happy_hare_server_inventory(token)
    if inventory_error or inventory is None:
        return 0, len(local_connections)
    synced = failed = 0
    for device in inventory["printers"]:
        physical_printer_id = device.get("id")
        if not isinstance(physical_printer_id, int):
            continue
        _connection, snapshot, _device, error = resolve_happy_hare_connection(
            token,
            local_connections,
            physical_printer_id,
            inventory=inventory,
        )
        if error or snapshot is None:
            if error not in {"connection_not_found"}:
                failed += 1
            continue
        status, _result = upload_happy_hare_snapshot(
            token, physical_printer_id, snapshot
        )
        if status == 200:
            synced += 1
        else:
            failed += 1
    if synced or failed:
        fh_log("Happy Hare topology sync: synced=%d failed=%d" % (synced, failed))
    return synced, failed


def send_printer_observations(token, observations, source_instance_id="", *, snapshot_complete=None):
    """POST observed printer connection data. The backend records it raw; the
    plugin makes no physical-printer identity decisions."""
    if not token:
        return None, {}
    status, body = http_post_json(
        "/orcaslicer/printer-connections/observe",
        token,
        {
            "observations": observations,
            "source_instance_id": source_instance_id or None,
            "snapshot_complete": (getattr(observations, "complete", True)
                                  if snapshot_complete is None else snapshot_complete),
        },
    )
    if status != 200:
        fh_log("printer observations HTTP %s for %d profile(s)" % (status, len(observations)))
        return status, {}
    try:
        result = json.loads(body.decode("utf-8")) or {}
    except (AttributeError, UnicodeDecodeError, ValueError):
        result = {}
    fh_log(
        "printer observations: sent=%d accepted=%d matched=%d unmatched=%d created=%d"
        % (
            len(observations),
            int(result.get("accepted") or 0),
            int(result.get("matched") or 0),
            int(result.get("unmatched") or 0),
            int(result.get("created") or 0),
        )
    )
    return status, result


RECOVERY_PROFILE_FOLDERS = {
    "filament": "filament",
    "machine": "machine",
    "process": "process",
}


def _is_managed_recovery_profile(kind, path, profile):
    if "[fh]" in str(profile.get("name") or "") or "@fh" in str(
        profile.get("name") or ""
    ):
        return True
    if kind == "filament":
        return managed_preset_id(path, profile) is not None
    return managed_profile_id(path, profile, kind) is not None


def _collect_recovery_presets(root, into, only_new, source):
    """Collect recoverable user presets from one live/backup Orca user tree."""
    try:
        accounts = os.listdir(root)
    except OSError:
        return
    for account in accounts:
        for kind, folder in RECOVERY_PROFILE_FOLDERS.items():
            base = os.path.join(root, account, folder)
            if not os.path.isdir(base):
                continue
            for dirpath, _dirs, files in os.walk(base):
                for fn in files:
                    if not fn.endswith(".json"):
                        continue
                    path = os.path.join(dirpath, fn)
                    try:
                        with open(path, "r", encoding="utf-8") as fh:
                            profile = json.load(fh)
                    except (OSError, ValueError):
                        continue
                    if not isinstance(profile, dict) or not profile:
                        continue
                    name = str(profile.get("name") or fn[:-len(".json")]).strip()
                    if not name or _is_managed_recovery_profile(kind, path, profile):
                        continue
                    # Two Orca accounts can legitimately contain differently
                    # edited presets with the same display name. Account is
                    # part of recovery identity; a live file still shadows an
                    # older backup of that same account/kind/name.
                    identity = "%s:%s:%s" % (kind, account, name)
                    if only_new and identity in into:
                        continue
                    into.setdefault(identity, {
                        "key": identity,
                        "kind": kind,
                        "name": name,
                        "account": account,
                        "profile": profile,
                        "source": source,
                    })


def scan_recovery_presets():
    """Find unmanaged filament, machine and process presets in live/backups.

    Live files win over version snapshots with the same kind/name. Managed
    FilamentHub files are repairable from the server and are deliberately kept
    out of this import list.
    """
    by_identity = {}
    _collect_recovery_presets(
        os.path.join(DATA_DIR, "user"),
        by_identity,
        only_new=False,
        source="live",
    )
    try:
        backups = [
            d for d in os.listdir(DATA_DIR) if d.startswith("user_backup")
        ]
        backups.sort(
            key=lambda name: os.path.getmtime(os.path.join(DATA_DIR, name)),
            reverse=True,
        )
    except OSError:
        backups = []
    for backup in backups:
        _collect_recovery_presets(
            os.path.join(DATA_DIR, backup),
            by_identity,
            only_new=True,
            source="backup",
        )
    return list(by_identity.values())


def scan_recovery_filaments():
    """Backward-compatible filament-only view used by older callers/tests."""
    return [item for item in scan_recovery_presets() if item["kind"] == "filament"]


def disambiguate_recovery_candidates(candidates):
    """Preserve same-named profiles when several Orca accounts are selected.

    FilamentHub profile identity cannot safely distinguish two recovered rows
    that have the same kind and display name. Keep the familiar name when only
    one is selected; when both are selected, append the source account to each
    recovered copy instead of silently letting the second overwrite the first.
    """
    counts = {}
    for candidate in candidates:
        identity = (candidate["kind"], candidate["name"])
        counts[identity] = counts.get(identity, 0) + 1

    result = []
    for candidate in candidates:
        identity = (candidate["kind"], candidate["name"])
        if counts[identity] < 2:
            result.append(candidate)
            continue
        account = str(candidate.get("account") or "Orca")
        suffix = " [%s]" % account
        recovered_name = candidate["name"][: max(1, 200 - len(suffix))] + suffix
        recovered = dict(candidate)
        recovered["name"] = recovered_name
        recovered["profile"] = {
            **candidate["profile"],
            "name": recovered_name,
        }
        result.append(recovered)
    return result


def preset_config_dict(preset, include_metadata=False):
    """Return the host-resolved, JSON-safe configuration for one preset.

    This is the normal integration path: Orca owns preset loading and
    inheritance, while the plugin consumes the public Preset API. Metadata that
    is not a config option is copied only when the host exposes it directly.
    """
    settings = {}
    for key in preset.config_keys():
        try:
            value = preset.config_value(key)
        except Exception:
            continue
        if value is None or isinstance(value, (str, int, float, bool, list, dict)):
            settings[key] = value
    if include_metadata:
        name = str(getattr(preset, "name", "") or "")
        if name:
            settings["name"] = name
        bundle_id = str(getattr(preset, "bundle_id", "") or "")
        if bundle_id:
            settings["bundle_id"] = bundle_id
    return settings


def _loaded_preset_metadata(collection, preset, local_profile):
    """Read identity metadata along the inheritance chain Orca actually loaded.

    ``Preset.filament_id`` and ``Preset.setting_id`` exist in Orca's C++ model,
    but the current Python host binding exposes neither property.  The host does
    expose the loaded preset's backing file and ``find_preset``; use only those
    host-selected files for metadata while keeping all resolved print settings
    on the public ``config_value`` API.
    """
    metadata = {}
    current = preset
    first_profile = local_profile if isinstance(local_profile, dict) else None
    visited = set()
    for _depth in range(16):
        name = str(getattr(current, "name", "") or "").strip()
        if not name or name in visited:
            break
        visited.add(name)
        raw = first_profile
        first_profile = None
        if raw is None:
            path = str(getattr(current, "file", "") or "").strip()
            if not path or not path.lower().endswith(".json"):
                break
            try:
                if os.path.getsize(path) > 2 * 1024 * 1024:
                    break
                with open(path, "r", encoding="utf-8") as fh:
                    candidate = json.load(fh)
                raw = candidate if isinstance(candidate, dict) else None
            except (OSError, ValueError):
                break
        if not isinstance(raw, dict):
            break
        for key in ("setting_id", "filament_id"):
            value = raw.get(key)
            if key not in metadata and isinstance(value, str) and value.strip():
                metadata[key] = value.strip()
        if "filament_id" in metadata:
            break
        parent_name = _parent_name(raw)
        if not parent_name:
            break
        try:
            current = collection.find_preset(parent_name)
        except Exception:
            break
        if current is None:
            break
    return metadata


def scan_managed_host_filaments():
    """Resolved managed material presets currently loaded by Orca.

    Bambu needs the provider family ``filament_id`` as well as the exact
    ``setting_id``. Those values are inheritance results owned by Orca, so a
    server export or a raw JSON file is not an honest substitute for the host's
    loaded Preset object.
    """
    local_entries = scan_local_fh_presets(user_filament_dir())
    local_names = {}
    for preset_id, entry in local_entries.items():
        path = entry.get("path") or ""
        if path:
            local_names[os.path.basename(path)[:-len(".json")]] = preset_id
        profile_name = str((entry.get("profile") or {}).get("name") or "").strip()
        if profile_name:
            local_names[profile_name] = preset_id

    resolved = {}
    try:
        filaments = orca.host.preset_bundle().filaments
        for index in range(filaments.size()):
            preset = filaments.preset(index)
            name = str(getattr(preset, "name", "") or "").strip()
            preset_id = preset_id_from_bundle(
                str(getattr(preset, "bundle_id", "") or "")
            )
            if preset_id is None:
                preset_id = local_names.get(name)
            if preset_id is None:
                continue
            profile = preset_config_dict(preset, include_metadata=True)
            local_profile = (local_entries.get(preset_id) or {}).get("profile") or {}
            for key in (
                "filament_type",
                "filament_colour",
                "default_filament_colour",
                "nozzle_temperature_range_low",
                "nozzle_temperature_range_high",
            ):
                if key in profile:
                    continue
                try:
                    value = preset.config_value(key)
                except Exception:
                    continue
                if value is None or isinstance(value, (str, int, float, bool, list, dict)):
                    profile[key] = value
            metadata = _loaded_preset_metadata(filaments, preset, local_profile)
            profile.update(metadata)
            profile["name"] = name or str(profile.get("name") or "")
            resolved[preset_id] = profile
    except Exception as exc:
        fh_log("managed material host scan failed: %s" % type(exc).__name__)
    return resolved


def loaded_managed_preset_ids():
    """Managed preset ids OrcaSlicer has actually loaded into its collection.

    A written JSON file is desired state, not evidence. Orca reads user presets
    at startup and silently discards any file its config loader rejects, so file
    count and loaded count are different facts. Returns None when the host
    collection cannot be read, which is "unknown" rather than "none loaded".
    Host reads must happen on the UI thread.
    """
    loaded = set()
    try:
        filaments = orca.host.preset_bundle().filaments
        for index in range(filaments.size()):
            preset_id = preset_id_from_bundle(
                str(getattr(filaments.preset(index), "bundle_id", "") or "")
            )
            if preset_id is not None:
                loaded.add(preset_id)
    except Exception as exc:
        fh_log("loaded managed preset scan unavailable: %s" % type(exc).__name__)
        return None
    return loaded


def scan_active_user_filaments():
    """Return only saved, unmanaged user filament presets from the active account.

    Orca's live Preset object can include editor changes that have not been
    written to disk yet. Importing that state would make a private draft appear
    in FilamentHub before the user saved it, so the persisted file is the source
    for this particular outbound path.
    """
    candidates = []
    try:
        filaments = orca.host.preset_bundle().filaments
        for i in range(filaments.size()):
            preset = filaments.preset(i)
            if not preset.is_user():
                continue
            name = str(getattr(preset, "name", "") or "").strip()
            if not name or "[fh]" in name or "@fh" in name:
                continue
            profile = saved_user_filament_profile(preset, name)
            if profile is None:
                continue
            candidates.append({
                "name": name,
                "profile": profile,
                "locator": _local_profile_locator(preset, "filament", name),
            })
    except Exception:
        pass
    return candidates


def saved_user_filament_profile(preset, expected_name):
    """Read one saved unmanaged filament profile without trusting live edits."""
    path = str(getattr(preset, "file", "") or "").strip()
    if not path or not path.lower().endswith(".json"):
        return None
    account_root = os.path.abspath(
        os.path.join(DATA_DIR, "user", resolve_user_preset_folder())
    )
    candidate = os.path.abspath(path)
    managed_root = os.path.abspath(user_filament_dir())
    try:
        if os.path.normcase(os.path.commonpath((account_root, candidate))) != os.path.normcase(
            account_root
        ):
            return None
        if os.path.normcase(os.path.commonpath((managed_root, candidate))) == os.path.normcase(
            managed_root
        ):
            return None
        if os.path.getsize(candidate) > 2 * 1024 * 1024:
            return None
        with open(candidate, "r", encoding="utf-8") as fh:
            profile = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(profile, dict):
        return None
    saved_name = str(profile.get("name") or "").strip()
    if not saved_name or saved_name != expected_name:
        return None
    # A bundle preset saved through Orca's Save As can retain its old metadata,
    # but its new path makes it a user profile.  Directory ownership is the
    # authority here; never let copied FilamentHub markers turn it back into an
    # update of the managed source.
    if preset_id_from_bundle(profile.get("bundle_id")) is not None:
        profile = dict(profile)
        profile.pop("bundle_id", None)
        profile.pop("fhub_id", None)
        profile.pop("fhub_source", None)
    return profile


def _sync_preferences(token):
    """Read account sync preferences through the plugin-scoped endpoint."""
    defaults = {
        "available": False,
        "auto_import_local_presets": False,
        "sync_printer_endpoints": False,
        "printer_discovery_key": "",
        "allow_filament_presets_import": False,
        "allow_filament_presets_export": False,
        "allow_printer_profiles_import": False,
        "allow_printer_profiles_export": False,
        "allow_print_profiles_import": False,
        "allow_print_profiles_export": False,
    }
    status, body = http_get("/orcaslicer/sync-prefs", token=token)
    defaults["status"] = status
    if status != 200:
        fh_log("sync-prefs HTTP %s -> privacy-safe defaults" % status)
        return defaults
    try:
        raw = json.loads(body.decode("utf-8")) or {}
        return dict(defaults, **{
            "available": True,
            "auto_import_local_presets": bool(raw.get("auto_import_local_presets")),
            "sync_printer_endpoints": bool(raw.get("sync_printer_endpoints")),
            "printer_discovery_key": str(raw.get("printer_discovery_key") or ""),
            "allow_filament_presets_import": bool(
                raw.get("allow_filament_presets_import")
            ),
            "allow_filament_presets_export": bool(
                raw.get("allow_filament_presets_export")
            ),
            "allow_printer_profiles_import": bool(
                raw.get("allow_printer_profiles_import")
            ),
            "allow_printer_profiles_export": bool(
                raw.get("allow_printer_profiles_export")
            ),
            "allow_print_profiles_import": bool(
                raw.get("allow_print_profiles_import")
            ),
            "allow_print_profiles_export": bool(
                raw.get("allow_print_profiles_export")
            ),
        })
    except ValueError:
        return defaults


def _printer_evidence_token(key, kind, value):
    if not re.fullmatch(r"[0-9a-f]{64}", str(key or "")) or not value:
        return None
    return hmac.new(bytes.fromhex(key), (kind + "\0" + value).encode("utf-8"), hashlib.sha256).hexdigest()


def _connection_endpoint_token(key, host, provider):
    raw = str(host or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parts = urllib.parse.urlsplit(raw)
        provider = str(provider or "generic").strip().lower()
        scheme = (parts.scheme or "http").lower()
        hostname = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError:
        return None
    if not hostname:
        return None
    if port is None:
        port = {"http": 80, "https": 443, "mqtt": 1883, "mqtts": 8883}.get(scheme)
    canonical = "|".join([provider, scheme, hostname, str(port or ""), (parts.path or "").rstrip("/")])
    return _printer_evidence_token(key, "endpoint", canonical)


def _observe_moonraker_identity(connection):
    status, body, _ = _moonraker_json(
        connection, "/server/database/item?namespace=moonraker&key=instance_id", timeout=3,
    )
    result = body.get("result") if status == 200 else None
    value = result.get("value") if isinstance(result, dict) else None
    try:
        return uuid.UUID(str(value)).hex
    except (ValueError, AttributeError):
        return None


def _observations_for_sync(observations, share_endpoints=False, discovery_key="", local_connections=None):
    """Keep LAN addresses local unless the account explicitly opted in."""
    prepared = PrinterObservationSnapshot()
    prepared.complete = getattr(observations, "complete", True)
    identities = {}
    connections = {str(c.get("print_host")): c for c in local_connections or []}
    if discovery_key and connections:
        # No LAN I/O on Orca's UI thread; one bounded read per configured host.
        worker = globals().get("BACKGROUND_WORKER")
        current_generation = getattr(worker, "current_job_generation", None)
        run_in_generation = getattr(worker, "run_in_generation", None)
        generation = current_generation() if callable(current_generation) else None

        def observe_identity(connection):
            if callable(run_in_generation):
                return run_in_generation(
                    generation, _observe_moonraker_identity, connection
                )
            return _observe_moonraker_identity(connection)

        with ThreadPoolExecutor(max_workers=4) as pool:
            values = pool.map(observe_identity, connections.values())
            identities = dict(zip(connections, values))
    for observation in observations or []:
        item = dict(observation)
        host = str(item.get("print_host") or "")
        item["has_connection"] = bool(host)
        item["endpoint_token"] = _connection_endpoint_token(discovery_key, host, item.get("host_type"))
        identity = identities.get(host)
        if identity:
            item["device_identity"] = {
                "kind": "moonraker_instance",
                "token": _printer_evidence_token(discovery_key, "device", "moonraker_instance\0" + identity),
            }
        if not share_endpoints:
            item["print_host"] = ""
        prepared.append(item)
    return prepared


def _draft_id(name):
    return "orca_local_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:12]


IMPORTED_DRAFTS_FILE = os.path.join(PLUGIN_DIR, ".fh_imported.json")


def load_imported_draft_ids():
    """Draft-ids already pushed by auto-import, kept in plugin storage so each
    local preset is imported once: a draft the user later deletes on the site is
    not resurrected on the next sync."""
    try:
        with open(IMPORTED_DRAFTS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_imported_draft_ids(ids):
    try:
        write_json_atomic(IMPORTED_DRAFTS_FILE, ids)
    except OSError:
        pass


def push_filament_drafts(token, candidates, authoritative=True):
    """Push private drafts with durable per-profile identity.

    The display name is editable in Orca and therefore cannot be identity.  The
    same private registry used by machine/process profiles distinguishes a rename
    from Save As.  Only per-item acknowledgements count as success: an HTTP 200
    may still contain rejected rows.
    """
    imported = load_imported_draft_ids()
    identity_items = []
    for candidate in candidates:
        profile = candidate.get("profile") or {}
        identity_items.append({
            "name": candidate.get("name") or "",
            "locator": candidate.get("locator") or (
                "recovery:filament:%s" % (candidate.get("key") or candidate.get("name") or "")
            ),
            "settings": profile,
            "candidate": candidate,
        })
    account_id, identity_items, registry_saved = reconcile_local_profile_identities(
        "filament", identity_items, authoritative=authoritative
    )
    if not registry_saved:
        return []

    sent_ids = []
    batch = []
    batch_ids = []
    batch_candidates = []
    imported_changed = False

    def flush_batch():
        accepted = []
        if not batch:
            return accepted
        status, body = http_post_json(
            "/orcaslicer/filaments/import", token, {"profiles": list(batch)}
        )
        if status != 200:
            fh_log("filament draft push HTTP %s for %d profile(s)" % (status, len(batch)))
            return accepted
        try:
            response = json.loads(body.decode("utf-8")) or {}
        except (AttributeError, UnicodeDecodeError, ValueError):
            response = {}
        results = response.get("results")
        if not isinstance(results, list):
            fh_log("filament draft push returned no per-item results")
            return accepted
        for index, did in enumerate(batch_ids):
            item_result = results[index] if index < len(results) else None
            if (
                isinstance(item_result, dict)
                and item_result.get("status") in {"created", "updated", "skipped"}
            ):
                accepted.append(did)
                candidate = batch_candidates[index]
                review_state = item_result.get("review_state")
                decisions = item_result.get("important_decisions")
                if isinstance(review_state, str):
                    candidate["_draft_review_state"] = review_state
                if isinstance(decisions, int) and decisions >= 0:
                    candidate["_draft_decisions"] = decisions
            else:
                fh_log("filament draft %s was not accepted" % did)
        return accepted

    for item in identity_items:
        candidate = item["candidate"]
        did = local_profile_external_id(account_id, item["local_profile_id"])
        legacy_did = _draft_id(candidate["name"])
        candidate["_draft_sync_id"] = did
        if did in imported or legacy_did in imported:
            if did not in imported:
                imported[did] = imported[legacy_did]
                imported_changed = True
            continue
        settings = dict(candidate["profile"])
        if authoritative:
            capture_mode = "resolved_runtime"
        else:
            recovered_source = candidate.get("source")
            capture_mode = (
                "recovered_backup_json"
                if recovered_source == "backup"
                else "recovered_live_json"
            )
        batch.append({
            "name": candidate["name"][:200],
            "external_id": did,
            "orcaslicer_settings": settings,
            "source": "orcaslicer",
            "source_version": PLUGIN_VERSION,
            "capture_mode": capture_mode,
        })
        batch_ids.append(did)
        batch_candidates.append(candidate)
        if len(batch) >= 50:
            sent_ids.extend(flush_batch())
            batch, batch_ids, batch_candidates = [], [], []
    if batch:
        sent_ids.extend(flush_batch())
    if imported_changed:
        save_imported_draft_ids(imported)
    return sent_ids


# --------------------------------------------------------------------------- #
# Two-way sync (all plugin-side; the host is never touched). Mirrors the fork's
# model: identity is the "filamenthub:<id>" bundle_id while present, with the
# persistent .info sync_info as fallback after Orca saves the preset. The
# FilamentHub version is preset.updated_at; a local edit is detected by a content hash. A small state
# private state file records, per preset, the (updated_at, hash) at the last
# sync so we can tell "remote changed" from "edited in OrcaSlicer".
#   * remote newer than last sync  -> pull (download + overwrite local)
#   * local hash changed           -> push (POST to the import endpoint; the
#                                     backend updates the owned preset or forks a
#                                     non-owned one into a new user preset)
#   * neither                      -> skip (never re-apply an unchanged preset)
#   * both changed                 -> keep both copies and report a conflict;
#                                     neither side wins silently.
# --------------------------------------------------------------------------- #
BUNDLE_PREFIX = "filamenthub:"
SYNC_STATE_FILE = os.path.join(PLUGIN_DIR, ".fh_sync.json")
# Fields that don't represent user intent (identity/bookkeeping) are excluded
# from the content hash so re-tagging or a metadata bump doesn't read as an edit.
_HASH_IGNORE = {"bundle_id", "updated_at", "setting_id", "filament_settings_id", "user_id", "from"}


def preset_id_from_bundle(bundle_id):
    if isinstance(bundle_id, str) and bundle_id.startswith(BUNDLE_PREFIX):
        tail = bundle_id[len(BUNDLE_PREFIX):]
        return int(tail) if tail.isdigit() else None
    return None


def preset_content_hash(profile):
    reduced = {k: v for k, v in profile.items() if k not in _HASH_IGNORE}
    blob = json.dumps(reduced, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


ANNOUNCED_WARNINGS_KEY = "_announced_warnings"


def load_sync_state():
    try:
        with open(SYNC_STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_sync_state(state):
    try:
        write_json_atomic(SYNC_STATE_FILE, state)
    except OSError:
        pass


def _valid_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def load_profile_identity_registry():
    path = profile_identity_registry_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            registry = json.load(fh)
    except (OSError, ValueError):
        registry = {}
    if not isinstance(registry, dict):
        registry = {}
    account_id = _valid_uuid(registry.get("account_id")) or str(uuid.uuid4())
    profiles = registry.get("profiles")
    if not isinstance(profiles, dict):
        profiles = {}
    for kind in (*PROFILE_KINDS, "filament"):
        if not isinstance(profiles.get(kind), dict):
            profiles[kind] = {}
    return {
        "version": 1,
        "account_id": account_id,
        "profiles": profiles,
    }


def save_profile_identity_registry(registry):
    try:
        write_json_atomic(profile_identity_registry_path(), registry, mode=0o600)
        return True
    except OSError as exc:
        fh_log("profile identity registry write failed: %s" % exc)
        return False


def plugin_source_instance_id():
    """Persistent identity of this Orca data directory, not a printer identity."""
    path = os.path.join(DATA_DIR, ".filamenthub", "source_identity.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
        value = stored.get("source_instance_id") if isinstance(stored, dict) else None
    except (OSError, ValueError):
        value = None
    if isinstance(value, str) and 16 <= len(value) <= 100:
        return value

    # Preserve the identity generated by earlier plugin builds when upgrading.
    state = load_sync_state()
    value = state.get("_source_instance_id")
    if not isinstance(value, str) or not 16 <= len(value) <= 100:
        value = secrets.token_urlsafe(24)
    try:
        write_json_atomic(path, {"source_instance_id": value}, mode=0o600)
    except OSError:
        # The old state remains a safe compatibility fallback if a filesystem
        # policy temporarily prevents creating the durable data-dir record.
        state["_source_instance_id"] = value
        save_sync_state(state)
    return value


def recover_sync_record(pid, token, known_presets, local_entry, remote_updated):
    """The sync state file is a cache next to the plugin and dies with it (a
    dialog-driven plugin update recreates the whole directory). A local preset
    with no state record must NOT be treated as outdated — re-pulling would
    silently overwrite the user's local edits. Rebuild the record by content:
    download the remote export, normalize it exactly like a pull would, and
    compare hashes. Returns the record to adopt when contents match, False when
    the local copy differs (a real local edit — caller pushes it), or None when
    the remote couldn't be fetched (caller skips this round)."""
    version_id = (remote_updated or {}).get("selected_version_id") if isinstance(remote_updated, dict) else None
    remote_timestamp = (remote_updated or {}).get("updated_at") if isinstance(remote_updated, dict) else remote_updated
    export_path = "/presets/%d/export/orcaslicer.json" % pid
    if isinstance(version_id, int):
        export_path += "?version_id=%d" % version_id
    status, body = http_get(export_path, token=token)
    if status != 200:
        return None
    try:
        remote = validate_filament_profile(json.loads(body.decode("utf-8")))
    except (TypeError, ValueError):
        return None
    ensure_parent_exists(remote, known_presets)
    ensure_filament_colour(remote)
    remote["bundle_id"] = "%s%d" % (BUNDLE_PREFIX, pid)
    local_path = local_entry.get("path")
    if local_path:
        apply_managed_filename_identity(remote, local_path)
    if preset_content_hash(remote) != local_entry["hash"]:
        return False
    if isinstance(version_id, int) and local_path:
        try:
            write_managed_info(
                local_path[:-len(".json")],
                pid,
                token,
                version_id,
            )
        except OSError as exc:
            fh_log("sync state recovery %d FAILED to persist version: %r" % (pid, exc))
            return None
    record = {"updated_at": remote_timestamp or "",
              "hash": local_entry["hash"],
              "name": local_entry["profile"].get("name") or ""}
    if isinstance(version_id, int):
        record["version_id"] = version_id
    return record


def scan_local_fh_presets(folder):
    # Map preset_id -> {path, profile, hash} for every managed local file. Orca
    # drops unknown JSON headers when the user saves a preset, so the persistent
    # .info sync_info marker is the fallback identity after bundle_id disappears.
    out = {}
    for artifact in scan_managed_preset_artifacts(folder):
        if not artifact.get("healthy"):
            continue
        pid = artifact["preset_id"]
        path = artifact["json_path"]
        profile = artifact["profile"]
        if pid not in out:
            out[pid] = {
                "path": path,
                "profile": profile,
                "hash": preset_content_hash(profile),
                "version_id": preset_version_id_from_info_file(
                    artifact.get("info_path") or ""
                ),
            }
    return out


# --------------------------------------------------------------------------- #
# Automatic printer (machine) and print (process) profile sync remains one-way:
# profiles are read from OrcaSlicer and handed to FilamentHub, so the site knows
# which machine a spool, a gate or a recommendation belongs to. A user may also
# explicitly restore selected profiles from the Recovery Center. That
# separate action creates only FilamentHub-managed copies and never overwrites an
# unmanaged Orca profile. Automatic sync does not pull machine/process profiles.
# Outbound profiles are sent once and again only after they change; the content
# hash lives in the shared sync state.
# --------------------------------------------------------------------------- #
PROFILE_KINDS = {
    "machine": {
        "label": "printer",
        "collection": "printers",
        "state_prefix": "machine",
        "import_path": "/orcaslicer/printer-profiles/import",
        "id_key": "printer_settings_id",
    },
    "process": {
        "label": "print",
        "collection": "prints",
        "state_prefix": "process",
        "import_path": "/orcaslicer/print-profiles/import",
        "id_key": "print_settings_id",
    },
}

SYNC_SCOPES = frozenset({"all", "filament", "machine", "process"})


def sync_scope_includes(scope, kind):
    return scope == "all" or scope == kind

# Connection fields describe one mutable physical-printer binding, not slicing
# behaviour.  Keep all of them out of PrinterProfile payloads.  Credentials and
# local certificate paths never leave the machine; safe endpoint facts travel
# only through the dedicated observation endpoint.
PRINTHOST_CONNECTION_KEYS = frozenset({
    "preset_name",
    "preset_names",
    "host_type",
    "printer_agent",
    "print_host",
    "print_host_webui",
    "printhost_port",
    "printhost_apikey",
    "printhost_user",
    "printhost_password",
    "printhost_cafile",
    "printhost_ssl_ignore_revoke",
    "printhost_authorization_type",
    "flashforge_serial_number",
    "bbl_use_printhost",
    "bbl_use_print_host_webui",
})

PROFILE_BOOKKEEPING_KEYS = frozenset({
    "type",
    "name",
    "from",
    "setting_id",
    "printer_settings_id",
    "print_settings_id",
    "filament_settings_id",
    "instantiation",
    "bundle_id",
    "fhub_id",
    "fhub_source",
    "updated_at",
    "user_id",
    "base_id",
    "version",
})


def strip_printhost_secrets(settings):
    return {k: v for k, v in settings.items() if k not in PRINTHOST_CONNECTION_KEYS}


def _profile_parent(collection, preset):
    parent_name = _preset_scalar(_preset_config_value(preset, "inherits"))
    if not parent_name:
        return "", None
    try:
        parent = collection.find_preset(parent_name)
        if parent is not None:
            return parent_name, parent
    except Exception:
        pass
    # Defensive fallback for compatible host builds/mocks that expose indexed
    # collections but not find_preset yet. Names are unique inside one Orca
    # collection, and using the exact parent is safer than flattening the child.
    try:
        for index in range(collection.size()):
            candidate = collection.preset(index)
            if str(getattr(candidate, "name", "") or "") == parent_name:
                return parent_name, candidate
    except Exception:
        pass
    return parent_name, None


def analyze_user_profile(collection, preset, kind):
    """Split a saved Orca preset into lineage, technical delta and connection.

    The host exposes resolved configs. Comparing the child with its exact loaded
    parent recreates Orca's semantic intent without reading OrcaSlicer.conf or
    freezing every current factory default into FilamentHub.
    """
    resolved = preset_config_dict(preset)
    parent_name, parent = _profile_parent(collection, preset)
    parent_resolved = not parent_name or parent is not None
    parent_settings = preset_config_dict(parent) if parent is not None else {}
    technical = {}
    if parent_resolved:
        for key, value in resolved.items():
            if key in PRINTHOST_CONNECTION_KEYS or key in PROFILE_BOOKKEEPING_KEYS:
                continue
            if parent is not None and key in parent_settings and parent_settings[key] == value:
                continue
            technical[key] = value
    if parent_name:
        technical["inherits"] = parent_name

    meaningful_keys = set(technical) - {"inherits"}
    id_key = PROFILE_KINDS[kind]["id_key"]
    setting_id = _preset_scalar(resolved.get(id_key) or getattr(preset, "name", ""))
    analysis = {
        "settings": technical,
        "inherits": parent_name,
        "parent_vendor_id": (
            str(getattr(parent, "bundle_id", "") or "") if parent is not None else ""
        ),
        "parent_resolved": parent_resolved,
        "setting_id": setting_id,
        "has_technical_changes": bool(meaningful_keys),
    }
    if kind == "process":
        analysis.update({
            "compatible_printers": _compatibility_strings(
                resolved.get("compatible_printers")
            ),
            "compatible_filaments": _compatibility_strings(
                resolved.get("compatible_filaments")
            ),
            "compatible_printers_condition": _compatibility_condition(
                resolved.get("compatible_printers_condition")
            ),
        })
    return analysis


def _local_profile_locator_from_path(preset_file, kind, name):
    preset_file = str(preset_file or "").strip()
    if preset_file:
        account_root = os.path.abspath(
            os.path.join(DATA_DIR, "user", resolve_user_preset_folder())
        )
        candidate = os.path.abspath(preset_file)
        try:
            if os.path.normcase(os.path.commonpath((account_root, candidate))) == os.path.normcase(
                account_root
            ):
                relative = os.path.relpath(candidate, account_root)
                normalized = relative.replace("\\", "/").lower()
                return "file:" + normalized
        except (OSError, ValueError):
            pass
    return "host:%s:%s" % (kind, str(name or "").strip())


def _local_profile_locator(preset, kind, name):
    """A private disk locator used only to reconcile rename versus Save As."""
    return _local_profile_locator_from_path(
        getattr(preset, "file", ""), kind, name
    )


def _local_profile_signature(kind, item):
    settings = item.get("settings") or item.get("profile") or {}
    if kind == "filament":
        settings = {
            key: value
            for key, value in settings.items()
            if key not in PROFILE_BOOKKEEPING_KEYS
        }
    payload = {"settings": settings}
    if kind == "process":
        for key in (
            "compatible_printers",
            "compatible_filaments",
            "compatible_printers_condition",
        ):
            value = item.get(key)
            if value not in (None, "", []):
                payload[key] = value
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def reconcile_local_profile_identities(kind, items, authoritative=True):
    """Assign durable UUIDs and conservatively recognize a one-to-one rename."""
    registry = load_profile_identity_registry()
    entries = registry["profiles"][kind]
    current_locators = {item.get("locator") for item in items}
    if authoritative:
        for entry in entries.values():
            if isinstance(entry, dict):
                entry["present"] = False

    used_ids = set()
    unresolved = []
    for item in items:
        locator = str(item.get("locator") or "host:%s:%s" % (kind, item.get("name", "")))
        signature = _local_profile_signature(kind, item)
        previous = entries.get(locator)
        local_id = _valid_uuid(previous.get("local_id")) if isinstance(previous, dict) else None
        if local_id and local_id not in used_ids:
            item["local_profile_id"] = local_id
            used_ids.add(local_id)
        else:
            unresolved.append((item, locator, signature))
        item["locator"] = locator
        item["identity_signature"] = signature

    if authoritative:
        missing_by_signature = {}
        for locator, entry in entries.items():
            if locator in current_locators or not isinstance(entry, dict):
                continue
            local_id = _valid_uuid(entry.get("local_id"))
            signature = entry.get("signature")
            if local_id and local_id not in used_ids and isinstance(signature, str):
                missing_by_signature.setdefault(signature, []).append((locator, local_id))

        new_by_signature = {}
        for unresolved_item in unresolved:
            new_by_signature.setdefault(unresolved_item[2], []).append(unresolved_item)
        for signature, new_items in new_by_signature.items():
            missing = missing_by_signature.get(signature) or []
            if len(new_items) == 1 and len(missing) == 1:
                item, _locator, _signature = new_items[0]
                item["local_profile_id"] = missing[0][1]
                used_ids.add(missing[0][1])

    for item, _locator, _signature in unresolved:
        if not item.get("local_profile_id"):
            item["local_profile_id"] = str(uuid.uuid4())

    for item in items:
        entries[item["locator"]] = {
            "local_id": item["local_profile_id"],
            "signature": item["identity_signature"],
            "name": item.get("name") or "",
            "present": True,
        }
    saved = save_profile_identity_registry(registry)
    return registry["account_id"], items, saved


def local_profile_external_id(account_id, local_profile_id):
    return "orca-local-v1:%s:%s" % (account_id, local_profile_id)


def scan_user_profiles_checked(kind):
    """Saved user profiles only; system presets travel as observations.

    Importing a selected stock profile would turn the global read-only
    definition into a user-owned FilamentHub copy and later export it back.
    Selection is evidence/reference, not ownership.
    """
    out = []
    complete = True
    try:
        spec = PROFILE_KINDS[kind]
        bundle = orca.host.preset_bundle()
        collection = getattr(bundle, spec["collection"])
        seen_names = set()
        for i in range(collection.size()):
            preset = collection.preset(i)
            name = str(getattr(preset, "name", "") or "")
            if name in seen_names:
                complete = False
                continue
            try:
                is_user = bool(preset.is_user())
            except Exception:
                is_user = False
            if not is_user:
                continue
            if "[fh]" in name or "@fh" in name:
                continue
            if str(getattr(preset, "bundle_id", "") or "").startswith(BUNDLE_ID):
                continue
            analysis = analyze_user_profile(collection, preset, kind)
            if not analysis["parent_resolved"]:
                # The host gives us a flattened child config. Without its exact
                # declared parent there is no honest way to recover the user's
                # delta, so keep it as observation evidence and retry after the
                # parent bundle becomes available instead of uploading a clone.
                seen_names.add(name)
                complete = False
                continue
            # A child created only to hold an IP/credentials is not a new
            # technical configuration. It is still sent as an observation by
            # observe_printer_presets(), where it can bind a physical printer to
            # the canonical parent without polluting the profile list.
            if not analysis["has_technical_changes"]:
                seen_names.add(name)
                continue
            out.append({
                "name": name,
                "locator": _local_profile_locator(preset, kind, name),
                "settings": analysis["settings"],
                "setting_id": analysis["setting_id"],
                "inherits": analysis["inherits"],
                "compatible_printers": analysis.get("compatible_printers"),
                "compatible_filaments": analysis.get("compatible_filaments"),
                "compatible_printers_condition": analysis.get(
                    "compatible_printers_condition"
                ),
            })
            seen_names.add(name)
    except Exception as exc:
        fh_log("%s profile scan failed: %s" % (kind, exc))
        return out, False
    return out, complete


def scan_user_profiles(kind):
    """Compatibility wrapper for callers that do not need completeness."""
    return scan_user_profiles_checked(kind)[0]


def push_user_profiles(kind, token, items, state, authoritative=True):
    """Send the profiles whose content changed since the last sync. Returns
    (sent, failed); unchanged profiles are silently left alone."""
    spec = PROFILE_KINDS[kind]
    account_id, items, registry_saved = reconcile_local_profile_identities(
        kind, items, authoritative=authoritative
    )
    if not registry_saved:
        return 0, max(1, len(items))

    source_instance_id = plugin_source_instance_id()
    snapshot_id = None
    server_bound_ids = None
    protocol_key = "_profile_snapshot_v1:%s:%s" % (account_id, kind)
    if authoritative:
        start_status, start_body = http_post_json(
            "/orcaslicer/profile-snapshots/start",
            token,
            {
                "kind": kind,
                "source_instance_id": source_instance_id,
                "account_id": account_id,
            },
        )
        if start_status == 200:
            try:
                start_result = json.loads(start_body.decode("utf-8")) or {}
                snapshot_id = _valid_uuid(start_result.get("snapshot_id"))
                raw_bound_ids = start_result.get("bound_local_profile_ids")
                if raw_bound_ids is not None:
                    if not isinstance(raw_bound_ids, list):
                        raise ValueError("bound_local_profile_ids must be a list")
                    server_bound_ids = {
                        _valid_uuid(value) for value in raw_bound_ids
                    }
                    if None in server_bound_ids:
                        raise ValueError("bound_local_profile_ids contains an invalid id")
            except (AttributeError, UnicodeDecodeError, ValueError):
                snapshot_id = None
                server_bound_ids = None
            if snapshot_id is None:
                fh_log("%s snapshot start returned an invalid id" % kind)
                return 0, max(1, len(items))
        elif start_status not in (404, 405):
            fh_log("%s snapshot start HTTP %s" % (kind, start_status))
            return 0, max(1, len(items))

    force_full_snapshot = snapshot_id is not None and not state.get(protocol_key)
    changed = []
    for item in items:
        settings = item["settings"]
        if kind == "machine":
            settings = strip_printhost_secrets(settings)
        local_profile_id = item["local_profile_id"]
        key = "%s:%s" % (spec["state_prefix"], local_profile_id)
        digest_payload = dict(settings)
        digest_payload["__name"] = item["name"]
        if kind == "process":
            for compatibility_key in (
                "compatible_printers",
                "compatible_filaments",
                "compatible_printers_condition",
            ):
                if item.get(compatibility_key) not in (None, "", []):
                    digest_payload["__effective_%s" % compatibility_key] = item[
                        compatibility_key
                    ]
        digest = preset_content_hash(digest_payload)
        binding_missing = (
            server_bound_ids is not None
            and local_profile_id not in server_bound_ids
        )
        if not force_full_snapshot and not binding_missing and state.get(key) == digest:
            continue
        # setting_id is how FilamentHub ties a network observation of this printer
        # back to its profile, so it must travel with the profile, not only as the
        # external id.
        setting_id = _preset_scalar(
            item.get("setting_id") or settings.get(spec["id_key"]) or item["name"]
        )[:100]
        payload = {
            "name": item["name"][:200],
            "external_id": local_profile_external_id(account_id, local_profile_id),
            "local_profile_id": local_profile_id,
            "setting_id": setting_id,
            "orcaslicer_settings": settings,
            "source": "orcaslicer",
        }
        if kind == "process":
            for compatibility_key in (
                "compatible_printers",
                "compatible_filaments",
                "compatible_printers_condition",
            ):
                value = item.get(compatibility_key)
                if compatibility_key == "compatible_printers_condition":
                    value = _compatibility_condition(value)
                else:
                    value = _compatibility_strings(value)
                if value not in (None, "", []):
                    payload[compatibility_key] = value
        changed.append((key, digest, payload))
    sent = failed = 0

    def send_batch(batch):
        nonlocal sent, failed
        request_payload = {"profiles": [entry[2] for entry in batch]}
        if snapshot_id is not None:
            request_payload.update({
                "source_instance_id": source_instance_id,
                "account_id": account_id,
                "snapshot_id": snapshot_id,
            })
        status, body = http_post_json(spec["import_path"], token, request_payload)
        if status == 200:
            try:
                response = json.loads(body.decode("utf-8")) or {}
            except (AttributeError, UnicodeDecodeError, ValueError):
                response = {}
            results = response.get("results")
            if isinstance(results, list):
                for index, (key, digest, _payload) in enumerate(batch):
                    item_result = results[index] if index < len(results) else None
                    if (
                        isinstance(item_result, dict)
                        and item_result.get("status") in {"created", "updated", "skipped"}
                    ):
                        state[key] = digest
                        sent += 1
                    else:
                        failed += 1
            else:
                if snapshot_id is not None:
                    # The snapshot API and per-item results ship together. An
                    # incomplete 200 must not finalize absence based on a batch
                    # whose individual writes were never acknowledged.
                    failed += len(batch)
                else:
                    # Compatibility with older API builds that acknowledged a
                    # whole successful batch without returning item results.
                    for key, digest, _payload in batch:
                        state[key] = digest
                    sent += len(batch)
            return
        if status == 422 and len(batch) > 1:
            midpoint = len(batch) // 2
            send_batch(batch[:midpoint])
            send_batch(batch[midpoint:])
            return
        error_shape = _http_error_shape(body)
        suffix = " (%s)" % error_shape if error_shape else ""
        fh_log(
            "%s push HTTP %s for %d profile(s)%s"
            % (kind, status, len(batch), suffix)
        )
        failed += len(batch)

    for batch_start in range(0, len(changed), 25):
        send_batch(changed[batch_start:batch_start + 25])

    if snapshot_id is not None and failed == 0:
        finalize_status, finalize_body = http_post_json(
            "/orcaslicer/profile-snapshots/finalize",
            token,
            {
                "kind": kind,
                "source_instance_id": source_instance_id,
                "account_id": account_id,
                "snapshot_id": snapshot_id,
                "present_local_profile_ids": [
                    item["local_profile_id"] for item in items
                ],
            },
        )
        finalize_result = {}
        if finalize_status == 200:
            try:
                finalize_result = json.loads(finalize_body.decode("utf-8")) or {}
            except (AttributeError, UnicodeDecodeError, ValueError):
                finalize_result = {}
        if finalize_result.get("status") in {"finalized", "already_finalized"}:
            state[protocol_key] = 1
        else:
            fh_log("%s snapshot finalize failed: HTTP %s" % (kind, finalize_status))
            failed += 1
    return sent, failed


RECOVERY_MACHINE_STRUCTURAL_KEYS = frozenset({
    # Orca writes these to a user machine file to keep the file structurally
    # valid even when they equal the system parent. They are not evidence of a
    # customized slicing configuration on their own.
    "printer_extruder_id",
    "printer_extruder_variant",
})


def recovery_profile_sync_item(candidate):
    """Convert one raw recovery file into the normal delta import contract."""
    kind = candidate["kind"]
    profile = dict(candidate["profile"])
    settings = {}
    for key, value in profile.items():
        if key in PRINTHOST_CONNECTION_KEYS or key in PROFILE_BOOKKEEPING_KEYS:
            continue
        settings[key] = value
    inherits = _parent_name(profile)
    if inherits:
        settings["inherits"] = inherits

    meaningful = set(settings) - {"inherits"}
    if kind == "machine":
        meaningful -= RECOVERY_MACHINE_STRUCTURAL_KEYS
        if not meaningful:
            return None

    item = {
        "name": candidate["name"],
        "locator": _local_profile_locator_from_path(
            candidate.get("path"), kind, candidate["name"]
        ),
        "settings": settings,
        "setting_id": _preset_scalar(
            profile.get(PROFILE_KINDS[kind]["id_key"]) or candidate["name"]
        ),
        "inherits": inherits,
    }
    if kind == "process":
        for key in (
            "compatible_printers",
            "compatible_filaments",
            "compatible_printers_condition",
        ):
            if profile.get(key) not in (None, "", []):
                item[key] = profile[key]
    return item


def recovery_connection_observation(candidate):
    """Return safe physical-printer evidence from a connection-only backup."""
    profile = candidate["profile"]
    host = _preset_scalar(profile.get("print_host"))
    if not host:
        return None
    return {
        "preset_name": candidate["name"][:200],
        "printer_settings_id": _preset_scalar(
            profile.get("printer_settings_id") or candidate["name"]
        )[:200],
        "inherits": _parent_name(profile)[:200],
        "printer_model": _preset_scalar(profile.get("printer_model"))[:200],
        "nozzle_diameter": _preset_scalar(
            profile.get("nozzle_diameter") or profile.get("printer_variant")
        )[:20],
        "vendor_id": "",
        "profile_fingerprint": None,
        "print_host": host[:500],
        "host_type": _preset_scalar(profile.get("host_type"))[:50],
        "is_system": False,
        "has_technical_changes": False,
        "is_current": False,
    }


# --------------------------------------------------------------------------- #
# Direct plugin page bootstrap
# --------------------------------------------------------------------------- #
DIRECT_PAGE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
html,body{height:100%;margin:0}body{display:grid;place-items:center;background:#171724;
color:#e8e8ef;font:14px system-ui,-apple-system,"Segoe UI",sans-serif}
.card{width:min(520px,calc(100% - 32px));box-sizing:border-box;padding:24px;
border:1px solid #3c3c4c;border-radius:16px;background:#20202e;text-align:center}
.spinner{width:28px;height:28px;margin:0 auto 16px;border:3px solid #3c3c4c;
border-top-color:#8b7cf8;border-radius:50%;animation:spin .9s linear infinite}
h1{margin:0 0 10px;font-size:19px}p{margin:0;color:#b8b8c5;line-height:1.5}
button{display:none;margin:18px auto 0;padding:8px 15px;border:1px solid #8b7cf8;
border-radius:8px;background:#8b7cf8;color:white;font:inherit;cursor:pointer}
button:disabled{opacity:.6;cursor:default}@keyframes spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.spinner{animation:none}}
</style></head><body><main class="card" role="status" aria-live="polite">
<div class="spinner" id="spinner"></div><h1 id="title"></h1><p id="message"></p>
<button id="retry" type="button"></button></main><script>
'use strict';
var target=__TARGET__,copy=__COPY__,title=document.getElementById('title'),
message=document.getElementById('message'),spinner=document.getElementById('spinner'),
retry=document.getElementById('retry'),attempt=0;
function showConnecting(){title.textContent=copy.connectTitle;message.textContent=copy.connectMessage;
spinner.style.display='block';retry.style.display='none';retry.disabled=true}
function showUnavailable(){title.textContent=copy.unavailableTitle;message.textContent=copy.unavailableMessage;
spinner.style.display='none';retry.style.display='block';retry.disabled=false}
function connect(){var current=++attempt,controller=new AbortController();showConnecting();
var timeout=setTimeout(function(){controller.abort()},10000);
fetch(target,{method:'GET',mode:'no-cors',cache:'no-store',credentials:'omit',signal:controller.signal})
.then(function(){if(current===attempt)location.replace(target)})
.catch(function(){if(current===attempt)showUnavailable()})
.finally(function(){clearTimeout(timeout)})}
retry.textContent=copy.retry;retry.addEventListener('click',connect);connect();
</script></body></html>"""


def direct_embed_url(bridge_session, language=None):
    """Bind the official injected bridge to this one plugin-page navigation."""
    url = localized_embed_url(language)
    fragment = urllib.parse.urlencode({"fh_bridge": bridge_session})
    return urllib.parse.urlunsplit((*urllib.parse.urlsplit(url)[:4], fragment))


def render_direct_page(bridge_session):
    """Probe the service before navigating the host page to the HTTPS embed UI."""
    language = refresh_ui_language()
    copy = {
        key: resolved_ui_catalog(language).get(key, key)
        for key in (
            "connectTitle",
            "connectMessage",
            "unavailableTitle",
            "unavailableMessage",
            "retry",
        )
    }
    return DIRECT_PAGE.replace(
        "__TARGET__",
        json.dumps(direct_embed_url(bridge_session, language)).replace("</", "<\\/"),
    ).replace(
        "__COPY__", json.dumps(copy, ensure_ascii=False).replace("</", "<\\/")
    )


SETTINGS_PAGE = r"""<style>
*{box-sizing:border-box}
body{margin:0;padding:14px 16px;background:var(--orca-bg);color:var(--orca-fg);font:13px var(--orca-font,system-ui,sans-serif)}
fieldset{margin:0 0 14px;padding:0;border:0}
legend{margin-bottom:6px;font-weight:600}
.row{display:flex;gap:8px;align-items:flex-start;margin:0 0 12px;cursor:pointer}
.row input{margin:2px 0 0;accent-color:var(--orca-accent)}
.servers{display:flex;gap:16px}
.servers .row{margin:0}
.hint{display:block;margin-top:2px;color:var(--orca-muted);font-size:12px;line-height:1.4}
.note{margin:6px 0 0;color:var(--orca-muted);font-size:12px;line-height:1.4}
.restart{color:var(--orca-accent)}
</style>
<fieldset><legend id="server-label"></legend>
<div class="servers">
<label class="row"><input type="radio" name="server" value="ru"><span>filamenthub.ru</span></label>
<label class="row"><input type="radio" name="server" value="club"><span>filamenthub.club</span></label>
</div>
<p class="note" id="server-note"></p>
<p class="note restart" id="server-restart" hidden></p>
</fieldset>
<label class="row"><input type="checkbox" data-key="auto_sync"><span><span data-copy="settingsAutoSync"></span><span class="hint" data-copy="settingsAutoSyncHint"></span></span></label>
<label class="row"><input type="checkbox" data-key="sync_success_notice"><span><span data-copy="settingsSuccessNotice"></span><span class="hint" data-copy="settingsSuccessNoticeHint"></span></span></label>
<label class="row"><input type="checkbox" data-key="developer_mode"><span><span data-copy="settingsDeveloperMode"></span><span class="hint" data-copy="settingsDeveloperModeHint"></span></span></label>
<p class="note" data-copy="settingsAccountHint"></p>
<script>
(function () {
  var copy = __COPY__;
  var defaults = __DEFAULTS__;
  var activeServer = __ACTIVE_SERVER__;
  var settings = Object.assign({}, defaults);
  document.getElementById("server-label").textContent = copy.settingsServer;
  document.getElementById("server-note").textContent = copy.settingsServerNote;
  document.getElementById("server-restart").textContent = copy.settingsServerRestart;
  document.querySelectorAll("[data-copy]").forEach(function (node) {
    node.textContent = copy[node.getAttribute("data-copy")];
  });
  function render(config) {
    settings = Object.assign({}, defaults);
    Object.keys(defaults).forEach(function (key) {
      if (config && typeof config[key] === typeof defaults[key]) settings[key] = config[key];
    });
    if (settings.server !== "ru" && settings.server !== "club") settings.server = defaults.server;
    var readOnly = !!(window.orca.getContext() || {}).readOnly;
    document.querySelectorAll("input[name=server]").forEach(function (input) {
      input.checked = input.value === settings.server;
      input.disabled = readOnly;
    });
    document.querySelectorAll("input[data-key]").forEach(function (input) {
      input.checked = settings[input.getAttribute("data-key")] === true;
      input.disabled = readOnly;
    });
    document.getElementById("server-restart").hidden = !activeServer || settings.server === activeServer;
  }
  function save() {
    window.orca.saveConfig(settings);
    render(settings);
  }
  document.querySelectorAll("input[name=server]").forEach(function (input) {
    input.addEventListener("change", function () { settings.server = input.value; save(); });
  });
  document.querySelectorAll("input[data-key]").forEach(function (input) {
    input.addEventListener("change", function () { settings[input.getAttribute("data-key")] = input.checked; save(); });
  });
  window.orca.onConfig(render);
})();
</script>"""

SETTINGS_COPY_KEYS = (
    "settingsServer",
    "settingsServerNote",
    "settingsServerRestart",
    "settingsAutoSync",
    "settingsAutoSyncHint",
    "settingsSuccessNotice",
    "settingsSuccessNoticeHint",
    "settingsDeveloperMode",
    "settingsDeveloperModeHint",
    "settingsAccountHint",
)


def render_settings_page():
    language = refresh_ui_language()
    catalog = resolved_ui_catalog(language)
    active_server = next(
        (key for key, url in PROD_SITE_URLS.items() if url == SITE_URL), None
    )

    def inline(value):
        return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")

    return (
        SETTINGS_PAGE.replace("__COPY__", inline({key: catalog.get(key, key) for key in SETTINGS_COPY_KEYS}))
        .replace("__DEFAULTS__", inline(PLUGIN_SETTINGS_DEFAULTS))
        .replace("__ACTIVE_SERVER__", inline(active_server))
    )


LOCAL_DIALOG_PAGE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
:root{color-scheme:dark}*{box-sizing:border-box}html,body{margin:0;min-height:100%}
body{background:#171724;color:#e8e8ef;font:14px system-ui,-apple-system,"Segoe UI",sans-serif;padding:22px}
main{max-width:620px;margin:0 auto}h1{font-size:19px;margin:0 0 8px}p{color:#b8b8c5;line-height:1.5;margin:0 0 16px}
label{display:block;margin-top:13px;color:#c9c9d4}input,select{display:block;width:100%;margin-top:6px;padding:9px 10px;
border:1px solid #49495c;border-radius:7px;background:#232334;color:#f5f5f8;font:inherit}
details{margin-top:13px}summary{cursor:pointer;color:#c9c9d4}.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px;justify-content:flex-end}
button{padding:8px 14px;border:1px solid #55556a;border-radius:7px;background:transparent;color:#ededf4;font:inherit;cursor:pointer}
button.primary{border-color:#8b5cf6;background:#7c3aed;color:#fff}button.danger{margin-right:auto;color:#fca5a5}
button:disabled{opacity:.5;cursor:wait}#status{min-height:21px;margin-top:14px;color:#c4b5fd}#candidate-wrap{display:none}
:focus-visible{outline:2px solid #c084fc;outline-offset:2px}
</style></head><body><main><h1 id="title"></h1><p id="hint"></p>
<form id="form"><div id="candidate-wrap"><label id="candidate-label"><span id="candidate-title"></span><select id="candidate"></select></label></div>
<label id="host-label"><input id="host" required autocomplete="off" maxlength="500"></label>
<label id="secret-label"><input id="secret" type="password" autocomplete="off" maxlength="1024"></label>
<details id="serial-wrap"><summary id="serial-summary"></summary><label><input id="serial" autocomplete="off" maxlength="200"></label></details>
<div id="status" role="status" aria-live="polite"></div><div class="actions">
<button id="remove" class="danger" type="button"></button><button id="search" type="button"></button>
<button id="cancel" type="button"></button><button id="save" class="primary" type="submit"></button>
</div></form></main><script>
'use strict';
var action=__ACTION__,copy=__COPY__,session=__SESSION__,kind=action.type==='configure-bambu'?'bambu':'moonraker',
activeSearchRequest='',ignoredSearchRequest='',searchTimer=0,activeConnectRequest='',ignoredConnectRequest='',connectTimer=0;
var form=document.getElementById('form'),host=document.getElementById('host'),secret=document.getElementById('secret'),
serial=document.getElementById('serial'),candidate=document.getElementById('candidate'),statusLine=document.getElementById('status'),
save=document.getElementById('save'),search=document.getElementById('search'),remove=document.getElementById('remove');
function send(message){try{orca.postMessage(Object.assign({source:'filamenthub-plugin',localDialogSession:session},message))}catch(error){}}
function finish(outcome){send({type:'local-dialog-close',outcome:outcome,provider:kind});}
function setBusy(value){save.disabled=value;search.disabled=value;remove.disabled=value;}
document.getElementById('cancel').textContent=copy.cancel||'Cancel';
document.getElementById('cancel').onclick=function(){finish('cancelled')};
if(kind==='bambu'){
 document.getElementById('title').textContent=(copy.bambuTitle||'Bambu LAN')+(action.printerName?' · '+action.printerName:'');
 document.getElementById('hint').textContent=copy.bambuHint||'';
 document.getElementById('host-label').prepend(document.createTextNode(copy.bambuAddress||'Printer address'));
 document.getElementById('secret-label').prepend(document.createTextNode(copy.bambuCode||'LAN access code'));
 document.getElementById('serial-summary').textContent=copy.bambuSerial||'Serial number';
 host.placeholder=copy.bambuAddressPlaceholder||'';serial.placeholder=copy.bambuSerialHint||'';secret.required=true;
 save.textContent=copy.bambuSave||'Connect';search.textContent=copy.bambuSearch||'Search local network';
 remove.textContent=copy.bambuRemove||'Remove local connection';remove.style.display='none';
 function prepare(refresh){var requestId='bambu-search-'+Date.now();
  if(refresh){activeSearchRequest=requestId;ignoredSearchRequest='';clearTimeout(searchTimer);setBusy(true);
   statusLine.textContent=copy.bambuSearching||'Searching…';
   searchTimer=setTimeout(function(){ignoredSearchRequest=activeSearchRequest;activeSearchRequest='';setBusy(false);
    statusLine.textContent=copy.bambuSearchIncomplete||'The network search could not finish.'},30000)}else{statusLine.textContent=''}
  send({type:'prepare-bambu-local',requestId:requestId,refresh:refresh===true,
   physicalPrinterId:action.physicalPrinterId,materialSystemId:action.materialSystemId,
   connectionRef:action.connectionRef||'',pairingCode:action.pairingCode||''});}
 search.onclick=function(){prepare(true)};
 remove.onclick=function(){send({type:'remove-bambu-local',physicalPrinterId:action.physicalPrinterId});finish('removed')};
 form.onsubmit=function(event){event.preventDefault();if(!host.value.trim()||!secret.value.trim())return;
  var requestId='bambu-setup-'+Date.now();activeConnectRequest=requestId;ignoredConnectRequest='';
  clearTimeout(connectTimer);setBusy(true);statusLine.textContent=copy.bambuConnecting||'Connecting…';
  connectTimer=setTimeout(function(){ignoredConnectRequest=activeConnectRequest;activeConnectRequest='';setBusy(false);
   statusLine.textContent=copy.bambuSetupTimeout||'No response was received. Your settings were not changed.';secret.focus()},120000);
  send({type:'configure-bambu-local',requestId:requestId,physicalPrinterId:action.physicalPrinterId,
   materialSystemId:action.materialSystemId,host:host.value.trim(),accessCode:secret.value.trim(),
   serial:serial.value.trim(),pairingCode:action.pairingCode||''});secret.value=''};
 function candidates(data){if((activeSearchRequest&&data.requestId!==activeSearchRequest)||data.requestId===ignoredSearchRequest)return;
  if(activeSearchRequest){clearTimeout(searchTimer);activeSearchRequest='';setBusy(false)}
  var items=Array.isArray(data.candidates)?data.candidates:[];candidate.textContent='';
  if(items.length){document.getElementById('candidate-wrap').style.display='block';
   document.getElementById('candidate-title').textContent=copy.bambuChoosePrinter||'Printer';
   items.forEach(function(item,index){var option=document.createElement('option');option.value=String(index);
    option.textContent=String(item.label||item.host||'')+' · '+String(item.host||'');candidate.appendChild(option)});
   function choose(){var item=items[Number(candidate.value)]||{};host.value=item.host||'';serial.value=item.serial||'';secret.value=''}
   candidate.onchange=choose;choose();statusLine.textContent=copy.bambuFound||'';
  }else{statusLine.textContent=data.discoveryAttempted?(data.discoveryComplete===false?(copy.bambuSearchIncomplete||''):(copy.bambuNotFound||'')):''}
  remove.style.display=data.hasSavedConnection?'':'none';search.textContent=data.discoveryAttempted?(copy.bambuSearchAgain||copy.bambuSearch):copy.bambuSearch;}
 orca.onMessage(function(data){if(!data||data.source!=='filamenthub-host')return;
  if(data.type==='bambu-setup-candidates')candidates(data);
  if(data.type==='bambu-setup-result'){
   if((activeConnectRequest&&data.requestId!==activeConnectRequest)||data.requestId===ignoredConnectRequest)return;
   clearTimeout(connectTimer);activeConnectRequest='';
   if(data.ok){finish('saved')}else{setBusy(false);statusLine.textContent=copy[data.code]||copy.bambuInvalid||'Connection failed';secret.focus()}}});
 prepare(false);host.focus();
}else{
 var labels=action.copy||{};document.getElementById('title').textContent=labels.title||'Moonraker';
 document.getElementById('hint').textContent=labels.hint||'';
 document.getElementById('host-label').prepend(document.createTextNode(labels.address||'Moonraker address'));
 document.getElementById('secret-label').prepend(document.createTextNode(labels.apiKey||'API key'));
 host.value=action.host||'';host.readOnly=!!action.connectionRef;secret.required=false;
 document.getElementById('serial-wrap').style.display='none';search.style.display='none';remove.style.display='none';
 save.textContent=labels.submit||copy.save||'Connect';
 form.onsubmit=function(event){event.preventDefault();if(!host.value.trim())return;setBusy(true);
  send({type:'printer-setup-local',operation:'probe',requestId:action.requestId,host:host.value.trim(),
   apiKey:secret.value,connectionRef:action.connectionRef||'',copy:labels});secret.value='';finish('saved')};
 (action.connectionRef?secret:host).focus();
}
</script></body></html>"""


def render_local_dialog(action, local_dialog_session):
    """Render a credential form owned by the plugin process, never by the site."""
    language = refresh_ui_language()
    copy = resolved_ui_catalog(language)
    return (
        LOCAL_DIALOG_PAGE.replace(
            "__ACTION__", json.dumps(action, ensure_ascii=False).replace("</", "<\\/")
        )
        .replace(
            "__COPY__", json.dumps(copy, ensure_ascii=False).replace("</", "<\\/")
        )
        .replace(
            "__SESSION__", json.dumps(local_dialog_session).replace("</", "<\\/")
        )
    )


# --------------------------------------------------------------------------- #
# Bambu Lab in LAN mode: reading the material feed
# --------------------------------------------------------------------------- #
# A Bambu printer answers a "pushall" with its whole state; the feed sits in
# print.ams. Field names and the flat tray numbering below are what BambuStudio's
# own parser reads, so whatever firmware feeds Bambu Studio feeds us too.
#
# Slot numbers stay the printer's own, never renumbered: 0..15 for AMS trays,
# 255 and 254 for the external spool holders of the main and deputy extruder.
# Only what the printer actually stated is reported — an unmeasurable spool
# yields None, never a zero that would read as "empty".

BAMBU_EXTERNAL_TRAY_MAIN = 255
BAMBU_EXTERNAL_TRAY_DEPUTY = 254
# Single-slot units (AMS HT) carry their own flat number from 0x80 up instead of
# being addressed as unit*4 + slot, and tray_now reports them that way as well.
BAMBU_WIDE_UNIT_BASE = 128
BAMBU_AMS_TYPE_N3S = 4
BAMBU_AMS_TYPE_MIXED = 5


def _bambu_ams_type(unit_info):
    bits = _bambu_bits(unit_info)
    return None if bits is None else bits & 0xF


def bambu_slot_index(unit_id, slot_id, unit_info=None):
    if unit_id in (BAMBU_EXTERNAL_TRAY_MAIN, BAMBU_EXTERNAL_TRAY_DEPUTY):
        return unit_id
    ams_type = _bambu_ams_type(unit_info)
    if unit_id >= BAMBU_WIDE_UNIT_BASE or ams_type == BAMBU_AMS_TYPE_N3S:
        return unit_id
    if ams_type == BAMBU_AMS_TYPE_MIXED:
        return 24 + slot_id
    return unit_id * 4 + slot_id


def _bambu_presence_bit_index(unit_id, slot_id, unit_info=None):
    ams_type = _bambu_ams_type(unit_info)
    if unit_id >= BAMBU_WIDE_UNIT_BASE or ams_type == BAMBU_AMS_TYPE_N3S:
        return 16 + max(unit_id - BAMBU_WIDE_UNIT_BASE, 0) + slot_id
    if ams_type == BAMBU_AMS_TYPE_MIXED:
        return 24 + slot_id
    return unit_id * 4 + slot_id


def _bambu_int(value, default=None):
    """Bambu sends numbers as strings about as often as it sends them as numbers."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value) if math.isfinite(value) else default
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except (ValueError, OverflowError):
            return default
    return default


def _bambu_bits(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return int(value.strip(), 16)
    except ValueError:
        return None


def _bambu_color(value):
    """tray_color is RRGGBBAA; an unset slot reports it fully transparent."""
    text = (value or "").strip().lstrip("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}([0-9A-F]{2})?", text):
        return None
    if len(text) == 8 and text[6:] == "00":
        return None
    return text[:6]


def _bambu_amount(value):
    """-1 means the printer cannot measure this spool, which is not the same as 0."""
    amount = _bambu_int(value)
    return None if amount is None or amount < 0 else amount


def _bambu_slot(tray, index, present):
    uid = (tray.get("tray_uuid") or tray.get("tag_uid") or "").strip()
    return {
        "index": index,
        "present": present,
        "material": (tray.get("tray_type") or "").strip() or None,
        "color_hex": _bambu_color(tray.get("tray_color")),
        "remaining_pct": _bambu_amount(tray.get("remain")),
        "remaining_g": _bambu_amount(tray.get("remain_g")),
        "reported_capacity_g": _bambu_amount(tray.get("tray_weight")),
        "filament_id": str(tray.get("tray_info_idx") or "").strip() or None,
        "setting_id": str(tray.get("setting_id") or "").strip() or None,
        "nozzle_temp_min": _bambu_int(tray.get("nozzle_temp_min")),
        "nozzle_temp_max": _bambu_int(tray.get("nozzle_temp_max")),
        # A zeroed uuid is how an empty or non-Bambu tray reports "no tag".
        "provider_uid": uid if uid.strip("0") else None,
    }


def _bambu_tag_read_capable(report):
    if not isinstance(report, dict):
        return False
    feed = report.get("ams")
    units = feed.get("ams") if isinstance(feed, dict) else None
    trays = []
    for unit in units or []:
        if isinstance(unit, dict):
            trays.extend(item for item in (unit.get("tray") or []) if isinstance(item, dict))
    holders = report.get("vir_slot")
    if isinstance(holders, list):
        trays.extend(item for item in holders if isinstance(item, dict))
    else:
        holder = report.get("vt_tray")
        if isinstance(holder, dict):
            trays.append(holder)
    return any("tray_uuid" in tray or "tag_uid" in tray for tray in trays)


def _bambu_capabilities(report):
    capabilities = ["read", "write", "presence", "consumption"]
    if _bambu_tag_read_capable(report):
        capabilities.append("tag_read")
    return capabilities


def _bambu_slot_locator(report, provider_index):
    feed = report.get("ams") if isinstance(report, dict) else None
    units = feed.get("ams") if isinstance(feed, dict) else None
    for unit in units or []:
        if not isinstance(unit, dict):
            continue
        unit_id = _bambu_int(unit.get("id"))
        if unit_id is None:
            continue
        for tray in unit.get("tray") or []:
            if not isinstance(tray, dict):
                continue
            slot_id = _bambu_int(tray.get("id"))
            if slot_id is None:
                continue
            if bambu_slot_index(unit_id, slot_id, unit.get("info")) == provider_index:
                return {"ams_id": unit_id, "slot_id": slot_id, "tray": tray}

    holders = report.get("vir_slot") if isinstance(report, dict) else None
    if not isinstance(holders, list):
        holder = report.get("vt_tray") if isinstance(report, dict) else None
        holders = [holder] if isinstance(holder, dict) else []
    for holder in holders:
        if not isinstance(holder, dict):
            continue
        ams_id = _bambu_int(holder.get("id"), BAMBU_EXTERNAL_TRAY_MAIN)
        if ams_id == provider_index:
            return {"ams_id": ams_id, "slot_id": 0, "tray": holder}
    return None


def _bambu_external_slots(report):
    slots = []
    holders = report.get("vir_slot")
    if not isinstance(holders, list):
        holder = report.get("vt_tray")
        holders = [holder] if isinstance(holder, dict) else []
    for holder in holders:
        if not isinstance(holder, dict):
            continue
        index = _bambu_int(holder.get("id"), BAMBU_EXTERNAL_TRAY_MAIN)
        slot = _bambu_slot(holder, index, bool((holder.get("tray_type") or "").strip()))
        slots.append(slot)
    return slots


def parse_bambu_feed(report):
    """Flatten one Bambu status report into the slots FilamentHub talks about.

    Returns None when the report says nothing about the feed: Bambu also pushes
    partial updates, and a partial one must not erase a full one.
    """
    if not isinstance(report, dict):
        return None
    feed = report.get("ams")
    units = feed.get("ams") if isinstance(feed, dict) else None
    external = _bambu_external_slots(report)
    if not isinstance(units, list) and not external:
        return None

    exist_bits = _bambu_bits(feed.get("tray_exist_bits")) if isinstance(feed, dict) else None
    slots = []
    for unit in units or []:
        if not isinstance(unit, dict):
            continue
        unit_id = _bambu_int(unit.get("id"))
        if unit_id is None:
            continue
        for tray in unit.get("tray") or []:
            if not isinstance(tray, dict):
                continue
            slot_id = _bambu_int(tray.get("id"))
            if slot_id is None:
                continue
            unit_info = unit.get("info")
            index = bambu_slot_index(unit_id, slot_id, unit_info)
            if exist_bits is None:
                present = bool((tray.get("tray_type") or "").strip())
            else:
                presence_index = _bambu_presence_bit_index(unit_id, slot_id, unit_info)
                present = bool(exist_bits & (1 << presence_index))
            slots.append(_bambu_slot(tray, index, present))

    slots.extend(external)
    slots.sort(key=lambda slot: slot["index"])
    active = _bambu_int(feed.get("tray_now")) if isinstance(feed, dict) else None
    return {"slots": slots, "active_index": active}


_BAMBU_STATES = {
    "RUNNING": "printing",
    "PAUSE": "paused",
    "PAUSED": "paused",
    "IDLE": "idle",
    "FINISH": "finished",
    "FAILED": "failed",
    "PREPARE": "preparing",
    "SLICING": "preparing",
}
BAMBU_MQTT_PORT = 8883
BAMBU_POLL_SECONDS = 30.0
BAMBU_MQTT_TIMEOUT = 12.0
BAMBU_SNAPSHOT_MIN_SECONDS = 60.0
BAMBU_HEARTBEAT_SECONDS = 120.0
BAMBU_STARTUP_JITTER_SECONDS = 120.0
BAMBU_RETRY_INITIAL_SECONDS = 5.0
BAMBU_RETRY_MAX_SECONDS = 300.0
BAMBU_INTERVAL_JITTER_RATIO = 0.2


def _mqtt_len(length):
    encoded = bytearray()
    while True:
        digit = length & 0x7F
        length >>= 7
        if length:
            digit |= 0x80
        encoded.append(digit)
        if not length:
            return bytes(encoded)


def _mqtt_field(payload):
    return struct.pack("!H", len(payload)) + payload


def _recv_exact(sock, length, deadline):
    chunks = bytearray()
    while len(chunks) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Bambu MQTT timed out")
        sock.settimeout(max(0.1, remaining))
        with external_operation():
            chunk = sock.recv(length - len(chunks))
        if not chunk:
            raise ConnectionError("Bambu MQTT connection closed")
        chunks.extend(chunk)
    return bytes(chunks)


def _mqtt_read_packet(sock, deadline):
    header = _recv_exact(sock, 1, deadline)[0]
    length = 0
    multiplier = 1
    for _ in range(4):
        digit = _recv_exact(sock, 1, deadline)[0]
        length += (digit & 0x7F) * multiplier
        if length > 2 * 1024 * 1024:
            raise ValueError("Bambu MQTT packet exceeds limit")
        if not digit & 0x80:
            body = _recv_exact(sock, length, deadline) if length else b""
            return header, body
        multiplier *= 128
    raise ValueError("invalid MQTT remaining length")


def _resolved_bambu_address(host):
    """Resolve once and return only a private/link-local LAN destination."""
    if not isinstance(host, str):
        raise ValueError("invalid LAN address")
    host = host.strip().strip("[]")
    if not host or len(host) > 253 or any(ch in host for ch in "/\\?#@"):
        raise ValueError("invalid LAN address")
    with external_operation():
        addresses = socket.getaddrinfo(
            host,
            BAMBU_MQTT_PORT,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    for family, socktype, proto, _, sockaddr in addresses:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        allowed = (
            DEV_CONTOUR if address.is_loopback else address.is_private or address.is_link_local
        )
        if allowed and not (address.is_multicast or address.is_unspecified):
            return family, socktype, proto, sockaddr
    raise ValueError("Bambu address must resolve inside the local network")


def _open_bambu_mqtt(host, access_code, timeout):
    family, socktype, proto, sockaddr = _resolved_bambu_address(host)
    ensure_worker_generation_active()
    raw = socket.socket(family, socktype, proto)
    raw.settimeout(timeout)
    try:
        with external_operation():
            raw.connect(sockaddr)
        with external_operation():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context.wrap_socket(raw, server_hostname=None)
    except Exception:
        raw.close()
        raise


def read_bambu_lan_snapshot(config, timeout=BAMBU_MQTT_TIMEOUT, on_report=None):
    """Read a Bambu snapshot, or keep receiving reports for a lifecycle-bound callback.

    The access code is used only for this local TLS connection. The returned
    payload deliberately contains no address or credential.
    """
    ensure_worker_generation_active()
    host = config.get("host") or ""
    access_code = config.get("access_code") or ""
    serial = (config.get("serial") or "").strip()
    if not access_code:
        raise ValueError("missing Bambu access code")
    deadline = time.monotonic() + timeout
    sock = _open_bambu_mqtt(host, access_code, min(timeout, BAMBU_MQTT_TIMEOUT))
    try:
        variable = _mqtt_field(b"MQTT") + bytes([4, 0xC2]) + struct.pack("!H", 30)
        client_id = ("fhub-" + secrets.token_hex(6)).encode("ascii")
        connection = (
            variable
            + _mqtt_field(client_id)
            + _mqtt_field(b"bblp")
            + _mqtt_field(access_code.encode("utf-8"))
        )
        with external_operation():
            sock.sendall(b"\x10" + _mqtt_len(len(connection)) + connection)
        header, connack = _mqtt_read_packet(sock, deadline)
        if (header & 0xF0) != 0x20 or len(connack) < 2 or connack[1] != 0:
            raise PermissionError("Bambu MQTT authentication rejected")

        report_topic = (
            "device/%s/report" % serial if serial else "device/+/report"
        ).encode("utf-8")
        subscribe = struct.pack("!H", 1) + _mqtt_field(report_topic) + b"\x00"
        with external_operation():
            sock.sendall(b"\x82" + _mqtt_len(len(subscribe)) + subscribe)
        sub_header, suback = _mqtt_read_packet(sock, deadline)
        if (
            (sub_header & 0xF0) != 0x90
            or len(suback) < 3
            or suback[2] == 0x80
        ):
            raise ConnectionError("Bambu MQTT subscription rejected")

        def request_full_snapshot(target_serial):
            topic = ("device/%s/request" % target_serial).encode("utf-8")
            body = json.dumps(
                {"pushing": {"sequence_id": "0", "command": "pushall"}},
                separators=(",", ":"),
            ).encode("utf-8")
            publish = _mqtt_field(topic) + body
            with external_operation():
                sock.sendall(b"\x30" + _mqtt_len(len(publish)) + publish)

        if serial:
            request_full_snapshot(serial)

        fallback = None
        last_ping = time.monotonic()
        while on_report is not None or time.monotonic() < deadline:
            if on_report is not None:
                ensure_worker_generation_active()
                if time.monotonic() - last_ping >= 15:
                    with external_operation():
                        sock.sendall(b"\xC0\x00")
                    last_ping = time.monotonic()
                with external_operation():
                    ready = sock.pending() or select.select([sock], [], [], 2)[0]
                if not ready:
                    continue
            try:
                header, packet = _mqtt_read_packet(
                    sock, time.monotonic() + BAMBU_MQTT_TIMEOUT
                    if on_report is not None else deadline
                )
            except TimeoutError:
                if fallback is not None:
                    return serial, fallback
                raise
            packet_type = header & 0xF0
            if packet_type == 0xC0:
                with external_operation():
                    sock.sendall(b"\xD0\x00")
                continue
            if packet_type != 0x30 or len(packet) < 2:
                continue
            topic_length = struct.unpack("!H", packet[:2])[0]
            if len(packet) < 2 + topic_length:
                continue
            topic = packet[2 : 2 + topic_length].decode("utf-8", "replace")
            parts = topic.split("/")
            if len(parts) != 3 or parts[0] != "device" or parts[2] != "report":
                continue
            topic_serial = parts[1]
            if not re.fullmatch(r"[A-Za-z0-9._-]{4,80}", topic_serial):
                continue
            if serial and topic_serial != serial:
                continue
            if not serial:
                serial = topic_serial
                request_full_snapshot(serial)
            payload_offset = 2 + topic_length
            qos = (header >> 1) & 0x03
            if qos == 0x03:
                continue
            if qos:
                if len(packet) < payload_offset + 2:
                    continue
                payload_offset += 2
            try:
                message = json.loads(packet[payload_offset:].decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            report = message.get("print") if isinstance(message, dict) else None
            if not isinstance(report, dict):
                continue
            if on_report is not None:
                on_report(serial, report)
                continue
            if "gcode_state" in report or "nozzle_temper" in report:
                fallback = report
            if "gcode_state" in report and (
                "ams" in report or "vt_tray" in report or "vir_slot" in report
            ):
                return serial, report
        if fallback is not None:
            return serial, fallback
        raise TimeoutError("Bambu MQTT report timed out")
    finally:
        try:
            sock.sendall(b"\xE0\x00")
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


class _BambuCommandDeadlineExpired(TimeoutError):
    """The host deadline elapsed before the device command was sent."""


def _publish_bambu_json(
    config,
    serial,
    payload,
    timeout=BAMBU_MQTT_TIMEOUT,
    absolute_deadline=None,
):
    """Publish one allowlisted local Bambu command over a short TLS session."""
    ensure_worker_generation_active()
    access_code = config.get("access_code") or ""
    if not access_code or not re.fullmatch(r"[A-Za-z0-9._-]{4,80}", serial or ""):
        raise ValueError("invalid Bambu command context")
    started_at = time.monotonic()
    deadline = started_at + timeout
    if absolute_deadline is not None:
        deadline = min(deadline, absolute_deadline)

    def ensure_before_command_deadline():
        if time.monotonic() < deadline:
            return
        if absolute_deadline is not None and deadline == absolute_deadline:
            raise _BambuCommandDeadlineExpired("Bambu command deadline expired")
        raise TimeoutError("Bambu MQTT timed out")

    ensure_before_command_deadline()
    connection_timeout = deadline - started_at
    try:
        sock = _open_bambu_mqtt(
            config.get("host") or "", access_code, connection_timeout
        )
    except TimeoutError as exc:
        if absolute_deadline is not None and time.monotonic() >= absolute_deadline:
            raise _BambuCommandDeadlineExpired(
                "Bambu command deadline expired"
            ) from exc
        raise
    try:
        ensure_before_command_deadline()
        variable = _mqtt_field(b"MQTT") + bytes([4, 0xC2]) + struct.pack("!H", 30)
        client_id = ("fhub-" + secrets.token_hex(6)).encode("ascii")
        connection = (
            variable
            + _mqtt_field(client_id)
            + _mqtt_field(b"bblp")
            + _mqtt_field(access_code.encode("utf-8"))
        )
        with external_operation():
            sock.sendall(b"\x10" + _mqtt_len(len(connection)) + connection)
        try:
            header, connack = _mqtt_read_packet(sock, deadline)
        except TimeoutError as exc:
            if absolute_deadline is not None and time.monotonic() >= absolute_deadline:
                raise _BambuCommandDeadlineExpired(
                    "Bambu command deadline expired"
                ) from exc
            raise
        if (header & 0xF0) != 0x20 or len(connack) < 2 or connack[1] != 0:
            raise PermissionError("Bambu MQTT authentication rejected")
        topic = ("device/%s/request" % serial).encode("utf-8")
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        publish = _mqtt_field(topic) + body
        # TCP/TLS and MQTT authentication consume the same host-side budget.
        # A slow CONNACK must not let an expired assignment reach the printer.
        ensure_before_command_deadline()
        with external_operation():
            sock.sendall(b"\x30" + _mqtt_len(len(publish)) + publish)
    finally:
        try:
            sock.sendall(b"\xE0\x00")
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


def _bambu_scalar(value):
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    return text or None


def _bambu_material_target(preset_id, profile):
    if not isinstance(profile, dict):
        return None
    filament_id = _bambu_scalar(profile.get("filament_id"))
    setting_id = _bambu_scalar(profile.get("setting_id"))
    material = _bambu_scalar(profile.get("filament_type"))
    color = _bambu_color(
        _bambu_scalar(profile.get("filament_colour"))
        or _bambu_scalar(profile.get("default_filament_colour"))
    )
    nozzle_min = _bambu_int(_bambu_scalar(profile.get("nozzle_temperature_range_low")))
    nozzle_max = _bambu_int(_bambu_scalar(profile.get("nozzle_temperature_range_high")))
    if not all((filament_id, setting_id, material, color)):
        return None
    if nozzle_min is None or nozzle_max is None or nozzle_min > nozzle_max:
        return None
    return {
        "preset_id": preset_id,
        "name": str(profile.get("name") or "")[:200] or "#%d" % preset_id,
        "filament_id": filament_id[:100],
        "setting_id": setting_id[:100],
        "material": material[:100],
        "color_hex": color,
        "nozzle_temp_min": nozzle_min,
        "nozzle_temp_max": nozzle_max,
    }


def _bambu_committed_spool_target(binding, commit, host_profiles):
    """Build a target from canonical spool facts and one loaded host preset."""
    status, body = http_get_bridge_json("/printer-bridge/snapshot", binding["bridge_token"])
    if status == 401:
        return None, "auth"
    if status == 403:
        return None, "access"
    if status != 200:
        return None, "server"
    snapshot = _decode_json_object(body)
    if (
        snapshot is None
        or snapshot.get("physical_printer_id") != binding.get("physical_printer_id")
        or snapshot.get("material_system_id") != binding.get("material_system_id")
    ):
        return None, "material_system_not_found"
    slot = next(
        (
            item for item in snapshot.get("slots") or []
            if isinstance(item, dict)
            and item.get("material_slot_id") == commit.get("materialSlotId")
        ),
        None,
    )
    desired = commit.get("desired")
    if slot is None:
        return None, "slot_not_found"
    if (
        slot.get("index") != commit.get("providerIndex")
        or slot.get("assignment_revision") != commit.get("assignmentRevision")
        or not isinstance(desired, dict)
    ):
        return None, "stale_assignment"
    preset = slot.get("preset")
    spool = slot.get("spool")
    if (
        not isinstance(preset, dict)
        or preset.get("id") != desired.get("presetId")
        or not isinstance(spool, dict)
        or spool.get("id") != desired.get("spoolId")
    ):
        return None, "stale_assignment"
    preset_id = desired.get("presetId")
    profile = host_profiles.get(preset_id) if isinstance(host_profiles, dict) else None
    target = _bambu_material_target(preset_id, profile)
    if target is None:
        return None, "preset_not_loaded"
    material = _bambu_scalar(spool.get("material_type"))
    color = _bambu_color(spool.get("color_hex"))
    if material is None or color is None:
        return None, "spool_facts_unavailable"
    if material.upper() != str(target["material"]).upper():
        return None, "material_mismatch"
    target = dict(target)
    target["material"] = material[:100]
    target["color_hex"] = color
    return target, None


def _bambu_material_matches(slot, target):
    if not isinstance(slot, dict) or not isinstance(target, dict):
        return False
    return (
        slot.get("filament_id") == target.get("filament_id")
        and (
            not slot.get("setting_id")
            or slot.get("setting_id") == target.get("setting_id")
        )
        and str(slot.get("material") or "").upper()
        == str(target.get("material") or "").upper()
        and str(slot.get("color_hex") or "").upper()
        == str(target.get("color_hex") or "").upper()
        and slot.get("nozzle_temp_min") == target.get("nozzle_temp_min")
        and slot.get("nozzle_temp_max") == target.get("nozzle_temp_max")
    )


def _bambu_material_command(locator, target):
    ams_id = locator["ams_id"]
    slot_id = locator["slot_id"]
    tray_id = (
        BAMBU_EXTERNAL_TRAY_DEPUTY
        if ams_id in {BAMBU_EXTERNAL_TRAY_MAIN, BAMBU_EXTERNAL_TRAY_DEPUTY}
        else slot_id
    )
    return {
        "print": {
            "command": "ams_filament_setting",
            "sequence_id": str(secrets.randbelow(900000000) + 100000000),
            "ams_id": ams_id,
            "slot_id": slot_id,
            "tray_id": tray_id,
            "tray_info_idx": target["filament_id"],
            "setting_id": target["setting_id"],
            "tray_color": target["color_hex"] + "FF",
            "nozzle_temp_min": target["nozzle_temp_min"],
            "nozzle_temp_max": target["nozzle_temp_max"],
            "tray_type": target["material"],
        }
    }


def apply_bambu_material_targets(
    config,
    targets,
    timeout=BAMBU_MQTT_TIMEOUT,
    settle_delay=0.75,
    absolute_deadline=None,
):
    """Apply non-RFID material metadata and prove the resulting printer state."""
    serial, report = read_bambu_lan_snapshot(config, timeout=timeout)
    expected_serial = str(config.get("serial") or "").strip()
    if expected_serial and serial != expected_serial:
        return {"ok": False, "code": "printer_changed", "report": report}
    state = str(report.get("gcode_state") or "").strip().upper()
    if state not in {"IDLE", "FINISH", "FAILED"}:
        return {"ok": False, "code": "printer_busy", "report": report}
    if absolute_deadline is not None and time.monotonic() >= absolute_deadline:
        return {"ok": False, "code": "expired", "report": report}

    prepared = []
    feed = parse_bambu_feed(report) or {"slots": []}
    slots = {item["index"]: item for item in feed.get("slots") or []}
    for provider_index, target in targets.items():
        slot = slots.get(provider_index)
        locator = _bambu_slot_locator(report, provider_index)
        if slot is None or locator is None:
            return {"ok": False, "code": "slot_not_found", "report": report}
        if (
            not slot.get("present")
            and provider_index
            not in {BAMBU_EXTERNAL_TRAY_MAIN, BAMBU_EXTERNAL_TRAY_DEPUTY}
        ):
            return {"ok": False, "code": "slot_empty", "report": report}
        if slot.get("provider_uid"):
            return {"ok": False, "code": "rfid_managed", "report": report}
        if not _bambu_material_matches(slot, target):
            prepared.append((provider_index, locator, target))

    try:
        for _provider_index, locator, target in prepared:
            if absolute_deadline is not None and time.monotonic() >= absolute_deadline:
                return {"ok": False, "code": "expired", "report": report}
            _publish_bambu_json(
                config,
                serial,
                _bambu_material_command(locator, target),
                timeout=timeout,
                absolute_deadline=absolute_deadline,
            )
    except _BambuCommandDeadlineExpired:
        return {"ok": False, "code": "expired", "report": report}
    except (OSError, PermissionError, TimeoutError, ValueError):
        # MQTT has no multi-slot transaction. If the connection breaks after a
        # preceding slot was accepted, preserve a fresh observation so the UI
        # can ask for another check instead of pretending nothing happened.
        try:
            final_serial, final_report = read_bambu_lan_snapshot(
                config, timeout=timeout
            )
            if final_serial != serial:
                return {
                    "ok": False,
                    "code": "printer_changed",
                    "report": final_report,
                }
        except (OSError, PermissionError, TimeoutError, ValueError):
            final_report = report
        return {"ok": False, "code": "write_failed", "report": final_report}

    final_report = report
    remaining = [item[0] for item in prepared]
    for _attempt in range(3):
        if not remaining:
            break
        if settle_delay > 0:
            time.sleep(settle_delay)
        final_serial, final_report = read_bambu_lan_snapshot(config, timeout=timeout)
        if final_serial != serial:
            return {"ok": False, "code": "printer_changed", "report": final_report}
        final_feed = parse_bambu_feed(final_report) or {"slots": []}
        final_slots = {item["index"]: item for item in final_feed.get("slots") or []}
        remaining = [
            provider_index
            for provider_index in remaining
            if not _bambu_material_matches(
                final_slots.get(provider_index), targets[provider_index]
            )
        ]
    return {
        "ok": not remaining,
        "code": None if not remaining else "verification_failed",
        "report": final_report,
        "remaining": remaining,
    }


def _bambu_number(report, name):
    value = report.get(name)
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _bambu_slot_label(index):
    if index == BAMBU_EXTERNAL_TRAY_MAIN:
        return "External spool"
    if index == BAMBU_EXTERNAL_TRAY_DEPUTY:
        return "External spool 2"
    if index >= BAMBU_WIDE_UNIT_BASE:
        return "AMS HT %d" % (index - BAMBU_WIDE_UNIT_BASE + 1)
    return "AMS %d · %d" % (index // 4 + 1, index % 4 + 1)


def build_bambu_bridge_snapshot(config, source_instance_id, report):
    """Normalize a Bambu report into the server's provider-neutral contract."""
    state = str(report.get("gcode_state") or "").strip().upper()
    progress = _bambu_int(report.get("mc_percent"))
    remaining_minutes = _bambu_int(report.get("mc_remaining_time"))
    print_error = report.get("print_error")
    printer = {
        "state": _BAMBU_STATES.get(state, "unknown"),
        "progress_percent": progress if progress is None else max(0, min(progress, 100)),
        "remaining_seconds": (
            max(0, remaining_minutes * 60) if remaining_minutes is not None else None
        ),
        "current_layer": _bambu_int(report.get("layer_num")),
        "total_layers": _bambu_int(report.get("total_layer_num")),
        "job_name": (report.get("subtask_name") or report.get("gcode_file") or "")[:300]
        or None,
        "nozzle_temperature": _bambu_number(report, "nozzle_temper"),
        "nozzle_target_temperature": _bambu_number(report, "nozzle_target_temper"),
        "bed_temperature": _bambu_number(report, "bed_temper"),
        "bed_target_temperature": _bambu_number(report, "bed_target_temper"),
        "chamber_temperature": _bambu_number(report, "chamber_temper"),
        "wifi_signal": str(report.get("wifi_signal") or "")[:32] or None,
        "error_code": str(print_error)[:80] if print_error not in (None, 0, "0", "") else None,
    }
    feed = parse_bambu_feed(report)
    active_index = feed.get("active_index") if feed else None
    slots = []
    for slot in (feed or {}).get("slots") or []:
        index = slot["index"]
        item = {
            "provider_index": index,
            "label": _bambu_slot_label(index),
            "kind": "external" if index in {254, 255} else "slot",
            "present": slot.get("present"),
            "active_feed": index == active_index if active_index is not None else None,
            "material": slot.get("material"),
            "color_hex": slot.get("color_hex"),
            "remaining_percent": slot.get("remaining_pct"),
            "remaining_grams": slot.get("remaining_g"),
        }
        tag_uid = _physical_tag_uid(slot.get("provider_uid"))
        if tag_uid is not None:
            item["tag_uid"] = tag_uid
            # The LAN report proves an identifier, not the RF technology.
            item["tag_technology"] = "unknown"
        slots.append(item)
    snapshot = {
        "material_system_id": config["material_system_id"],
        "provider": "bambu",
        "transport": "orca_plugin_lan",
        "source_instance_id": source_instance_id,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "capabilities": _bambu_capabilities(report),
        "printer": printer,
        "slots": slots,
        "slot_topology_complete": feed is not None,
    }
    device_identity = _valid_bambu_device_identity(config.get("device_identity"))
    if device_identity is not None:
        snapshot["device_identity"] = device_identity
    return snapshot


def _fetch_bambu_device_identity(bridge_token, serial):
    status, body = http_get_bridge_json("/printer-bridge/identity-context", bridge_token)
    if status != 200:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return _bambu_device_identity(payload.get("printer_discovery_key"), serial)


def _prepare_bambu_observation(config, observed_serial):
    """Pin an observation to its local printer before any cloud request."""
    canonical_observed = _normalized_bambu_serial(observed_serial)
    if not canonical_observed:
        raise ValueError("invalid observed Bambu serial")
    canonical_expected = _normalized_bambu_serial(config.get("serial"))
    if canonical_expected and canonical_expected != canonical_observed:
        raise ValueError("Bambu serial mismatch")

    identity = _valid_bambu_device_identity(config.get("device_identity"))
    if identity is None:
        identity = _fetch_bambu_device_identity(
            config.get("bridge_token") or "",
            observed_serial,
        )

    with _BAMBU_CONFIG_LOCK:
        payload = load_bambu_config()
        current = next(
            (
                item
                for item in payload["printers"]
                if item.get("physical_printer_id") == config.get("physical_printer_id")
                and item.get("material_system_id") == config.get("material_system_id")
                and item.get("bridge_token") == config.get("bridge_token")
            ),
            None,
        )
        if current is None:
            raise ValueError("Bambu binding changed during observation")
        current_expected = _normalized_bambu_serial(current.get("serial"))
        if current_expected and current_expected != canonical_observed:
            raise ValueError("Bambu serial mismatch")
        current_identity = _valid_bambu_device_identity(current.get("device_identity"))
        if current_identity is not None:
            identity = current_identity
        _assert_bambu_binding_available(
            payload,
            current["physical_printer_id"],
            observed_serial,
            identity,
        )

        changed = False
        if not current_expected:
            current["serial"] = str(observed_serial).strip()[:80]
            changed = True
        if identity is not None and current_identity is None:
            current["device_identity"] = identity
            changed = True
        if changed:
            save_bambu_config(payload)
        return dict(current), payload["source_instance_id"]


def _bambu_local_binding(physical_printer_id, material_system_id):
    local = load_bambu_config()
    binding = next(
        (
            item
            for item in local["printers"]
            if item.get("physical_printer_id") == physical_printer_id
            and item.get("material_system_id") == material_system_id
            and item.get("bridge_token")
        ),
        None,
    )
    return local, binding


def _bambu_server_assignments(device, material_system_id):
    systems = device.get("material_systems") if isinstance(device, dict) else None
    system = next(
        (
            item
            for item in systems or []
            if isinstance(item, dict)
            and item.get("id") == material_system_id
            and item.get("provider") == "bambu"
        ),
        None,
    )
    if system is None:
        return None
    assignments = []
    for slot in system.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        provider_index = slot.get("provider_index")
        if type(provider_index) is not int or provider_index < 0:
            continue
        preset_id = slot.get("preset_id")
        spool_id = slot.get("spool_id")
        assignments.append({
            "slot": provider_index,
            "preset_id": preset_id if type(preset_id) is int and preset_id > 0 else None,
            "spool_id": spool_id if type(spool_id) is int and spool_id > 0 else None,
            "source_ts": str(slot.get("source_ts") or "") or None,
        })
    assignments.sort(key=lambda item: item["slot"])
    return assignments


def _bambu_assignment_snapshot(assignments):
    return [
        {
            "slot": item["slot"],
            "preset_id": item.get("preset_id"),
            "spool_id": item.get("spool_id"),
            "source_ts": item.get("source_ts"),
        }
        for item in assignments
    ]


def _bambu_material_preview(report, assignments, host_profiles):
    feed = parse_bambu_feed(report) or {"slots": []}
    slots = {item["index"]: item for item in feed.get("slots") or []}
    changes = []
    unresolved = []
    targets = {}
    for assignment in assignments:
        provider_index = assignment["slot"]
        preset_id = assignment.get("preset_id")
        spool_id = assignment.get("spool_id")
        slot = slots.get(provider_index)
        if preset_id is None:
            if spool_id is not None:
                unresolved.append({"slot": provider_index, "reason": "preset_required"})
            continue
        if slot is None:
            unresolved.append({"slot": provider_index, "reason": "slot_not_found"})
            continue
        if (
            not slot.get("present")
            and provider_index
            not in {BAMBU_EXTERNAL_TRAY_MAIN, BAMBU_EXTERNAL_TRAY_DEPUTY}
        ):
            unresolved.append({"slot": provider_index, "reason": "slot_empty"})
            continue
        if slot.get("provider_uid"):
            unresolved.append({"slot": provider_index, "reason": "rfid_managed"})
            continue
        target = _bambu_material_target(preset_id, host_profiles.get(preset_id))
        if target is None:
            unresolved.append({"slot": provider_index, "reason": "preset_not_loaded"})
            continue
        targets[provider_index] = target
        if _bambu_material_matches(slot, target):
            continue
        changes.append({
            "slot": provider_index,
            "presetId": preset_id,
            "presetName": target["name"],
            "currentMaterial": slot.get("material"),
            "currentColor": slot.get("color_hex"),
            "targetMaterial": target["material"],
            "targetColor": target["color_hex"],
        })
    return changes, unresolved, targets


_MAX_INPUT = 64 * 1024 * 1024
_MAX_METADATA = 1024 * 1024
_MAX_GCODE = 64 * 1024 * 1024
_MAX_RATIO = 1_000
_WEIGHT_VECTOR_RE = re.compile(
    rb"^\s*;\s*filament\s+(?:used|weight)\s*\[g\]\s*[:=]\s*([^\r\n;]+)",
    re.IGNORECASE | re.MULTILINE,
)


def _finite_positive(value: str) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _weights_from_gcode(data: bytes) -> dict[int, float] | None:
    match = _WEIGHT_VECTOR_RE.search(data)
    if match is None:
        return None
    values: dict[int, float] = {}
    for index, raw in enumerate(re.split(rb"[,\s]+", match.group(1).strip())):
        value = _finite_positive(raw.decode("ascii", "ignore"))
        if value is not None:
            values[index] = value
    return values or None


def _safe_zip_info(info: zipfile.ZipInfo, limit: int) -> bool:
    uncompressed = int(info.file_size)
    compressed = int(info.compress_size)
    if uncompressed < 0 or uncompressed > limit:
        return False
    if uncompressed and (compressed <= 0 or uncompressed > compressed * _MAX_RATIO):
        return False
    return True


def _normal_name(name: str) -> str:
    candidate = name.replace("\\", "/")
    if candidate.startswith("/") or any(part == ".." for part in candidate.split("/")):
        return ""
    normalized = posixpath.normpath(candidate)
    return "" if normalized in {"", "."} or normalized.startswith("../") else normalized


def _plate_number(path: str) -> int | None:
    match = re.fullmatch(r"metadata/plate_(\d+)\.gcode", _normal_name(path), re.IGNORECASE)
    return int(match.group(1)) if match else None


def _weights_from_slice_info(payload: bytes, plate_index: int) -> dict[int, float] | None:
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        return None
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return None
    for plate in root.findall(".//plate"):
        metadata = {
            item.get("key"): item.get("value")
            for item in plate.findall("metadata")
            if item.get("key")
        }
        try:
            current = int(metadata.get("index", ""))
        except (TypeError, ValueError):
            continue
        if current != plate_index:
            continue
        weights: dict[int, float] = {}
        for item in plate.findall("filament"):
            try:
                logical = int(item.get("id", "")) - 1
            except (TypeError, ValueError):
                continue
            if logical < 0:
                continue
            value = _finite_positive(item.get("used_g", ""))
            if value is not None:
                weights[logical] = value
        return weights or None
    return None


def parse_bambu_consumption_file(data: bytes, plate_path: str | None = None) -> dict | None:
    """Extract positive per-logical-filament slicer weights from G-code/3MF.

    A multi-plate 3MF requires ``plate_path``; no implicit plate 1 selection is
    made.  The function never treats printer telemetry as consumption evidence.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)) or len(data) > _MAX_INPUT:
        return None
    payload = bytes(data)
    if not payload.startswith(b"PK\x03\x04"):
        weights = _weights_from_gcode(payload)
        return {"source": "slicer_gcode", "weights": weights} if weights else None

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > 4096:
                return None
            names = [_normal_name(item.filename) for item in infos]
            if len(names) != len(set(names)) or "" in names:
                return None
            plates = [item for item in infos if _plate_number(item.filename) is not None]
            if not plates:
                return None
            requested = _normal_name(plate_path) if plate_path else None
            if requested is None and len(plates) != 1:
                return None
            selected = next(
                (item for item in plates if _normal_name(item.filename) == requested),
                plates[0] if requested is None else None,
            )
            if selected is None or not _safe_zip_info(selected, _MAX_GCODE):
                return None
            metadata = next(
                (item for item in infos if _normal_name(item.filename).lower() == "metadata/slice_info.config"),
                None,
            )
            if metadata is not None and not _safe_zip_info(metadata, _MAX_METADATA):
                return None
            plate_index = _plate_number(selected.filename)
            if plate_index is None:
                return None
            metadata_bytes = archive.read(metadata) if metadata is not None else b""
            if b"<!DOCTYPE" in metadata_bytes.upper() or b"<!ENTITY" in metadata_bytes.upper():
                return None
            weights = _weights_from_slice_info(metadata_bytes, plate_index)
            if weights is None:
                weights = _weights_from_gcode(archive.read(selected))
            if not weights:
                return None
            return {
                "source": "slicer_3mf",
                "weights": weights,
                "plate_index": plate_index,
                "plate_path": _normal_name(selected.filename),
            }
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return None


def _merge_bambu_report(previous, update):
    result = dict(previous)
    for key, value in update.items():
        old = result.get(key)
        if isinstance(old, dict) and isinstance(value, dict):
            result[key] = _merge_bambu_report(old, value)
        elif (isinstance(old, list) and isinstance(value, list) and value
              and all(isinstance(item, dict) and "id" in item for item in old + value)):
            indexed = {str(item["id"]): item for item in old}
            for item in value:
                item_key = str(item["id"])
                indexed[item_key] = _merge_bambu_report(indexed.get(item_key, {}), item)
            result[key] = list(indexed.values())
        else:
            result[key] = value
    return result


class _BambuStreamLifecycle:
    def __init__(self, runtime, stop):
        self.runtime = runtime
        self.stop = stop

    def authorize_external_operation(self, generation):
        self.runtime.authorize_external_operation(generation)
        if self.stop.is_set():
            raise PluginLifecycleStopped("Bambu stream binding has stopped")


def _bambu_job_key(report):
    identifiers = [str(report.get(key) or "") for key in ("task_id", "subtask_id", "project_id")]
    keys = ("gcode_file",) if any(value not in {"", "0"} for value in identifiers) else (
        "gcode_file", "subtask_name"
    )
    fields = identifiers + [str(report.get(key) or "") for key in keys]
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def _bambu_file_candidates(report):
    candidates = set()
    for field in ("gcode_file", "subtask_name"):
        value = report.get(field)
        if not isinstance(value, str) or len(value) > 500:
            continue
        value = value.replace("\\", "/")
        if any(ord(char) < 32 for char in value) or ":" in value:
            continue
        if any(part == ".." for part in value.split("/")):
            continue
        if value.lower().startswith("metadata/"):
            continue
        name = posixpath.basename(value)
        if not name:
            continue
        if name.lower().endswith((".3mf", ".gcode")):
            candidates.add(name)
        else:
            candidates.update((name + ".3mf", name + ".gcode.3mf", name + ".gcode"))
    return candidates


class _BambuReadOnlyFTP(ftplib.FTP_TLS):
    """Implicit LAN TLS; data connections remain pinned to the control peer."""

    def putcmd(self, line):
        ensure_worker_generation_active()
        return super().putcmd(line)

    def ntransfercmd(self, cmd, rest=None):
        ensure_worker_generation_active()
        connection, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        try:
            if self._prot_p:
                ensure_worker_generation_active()
                connection = self.context.wrap_socket(
                    connection, server_hostname=self.host, session=self.sock.session
                )
            return connection, size
        except Exception:
            connection.close()
            raise


def read_bambu_consumption_file(config, report):
    """Read a uniquely named current artifact, never the newest file on storage."""
    candidates = _bambu_file_candidates(report)
    if not candidates:
        return None
    _, _, _, address = _resolved_bambu_address(config.get("host") or "")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    ftp = _BambuReadOnlyFTP(context=context, timeout=5)
    ftp.host = address[0]
    deadline = time.monotonic() + 30
    try:
        with external_operation():
            raw = socket.create_connection((ftp.host, 990), timeout=5)
            try:
                ensure_worker_generation_active()
                ftp.sock = context.wrap_socket(raw, server_hostname=ftp.host)
            except Exception:
                raw.close()
                raise
            ftp.af = ftp.sock.family
            ftp.file = ftp.sock.makefile("r", encoding=ftp.encoding)
            ftp.welcome = ftp.getresp()
            ftp.login("bblp", config.get("access_code") or "")
            ftp.prot_p()
            matches = set()
            for directory in ("/", "/cache", "/model"):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Bambu file lookup timed out")
                lines = []

                def append_name(line):
                    if len(lines) >= 4096 or time.monotonic() >= deadline:
                        raise ValueError("Bambu file listing exceeds limit")
                    lines.append(line)

                try:
                    ftp.retrlines("NLST " + directory, append_name)
                except ftplib.error_perm:
                    continue
                for name in lines:
                    basename = posixpath.basename(name)
                    if basename in candidates and not any(ord(c) < 32 for c in name):
                        matches.add(posixpath.join(directory, basename))
            if len(matches) != 1:
                return None
            path = next(iter(matches))
            ftp.voidcmd("TYPE I")
            size = ftp.size(path)
            if size is None or size <= 0 or size > _MAX_INPUT:
                return None
            data = bytearray()

            def receive(chunk):
                ensure_worker_generation_active()
                if len(data) + len(chunk) > _MAX_INPUT or time.monotonic() >= deadline:
                    raise ValueError("Bambu artifact exceeds transfer limit")
                data.extend(chunk)

            ftp.retrbinary("RETR " + path, receive, blocksize=65536)
            if len(data) != size or ftp.size(path) != size:
                return None
        plate_path = str(report.get("gcode_file") or "")
        if _plate_number(plate_path) is None:
            index = _bambu_int(report.get("plate_idx"))
            plate_path = "Metadata/plate_%d.gcode" % index if index and index > 0 else None
        result = parse_bambu_consumption_file(data, plate_path)
        if result is not None:
            result["sha256"] = hashlib.sha256(data).hexdigest()
        return result
    finally:
        ftp.close()


def _bambu_usage_routes(desired):
    result = {}
    for slot in desired.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        spool = slot.get("spool")
        proof = slot.get("usage_route_proof")
        index = slot.get("index")
        if (isinstance(spool, dict) and isinstance(spool.get("id"), int)
                and isinstance(index, int) and isinstance(proof, str) and proof):
            result[index] = {
                "slot_index": index, "spool_id": spool["id"],
                "usage_route_proof": proof, "evidence": "route_proof",
                "initial_weight_g": spool.get("initial_weight_g"),
            }
    return result


def _bambu_progress(report):
    if report.get("gcode_state") == "FINISH":
        return 1.0
    percent = _bambu_number(report, "mc_percent")
    return min(max(percent / 100, 0), 1) if percent is not None else None


def _bambu_usage_counters(report, routes, estimate):
    """Return comparable per-slot estimates with a source and physical identity."""
    feed = parse_bambu_feed(report) or {}
    slots = {item["index"]: item for item in feed.get("slots") or []}
    progress = _bambu_progress(report)
    weights = (estimate or {}).get("weights") or {}
    mapping = report.get("ams_mapping")
    totals = {}
    if weights and progress is not None:
        for logical, weight in weights.items():
            logical = int(logical)
            index = None
            if isinstance(mapping, list) and logical < len(mapping):
                flat = _bambu_int(mapping[logical])
                # Bambu's task mapping uses flat 16..23 for HT units 128..135.
                if flat is not None:
                    index = BAMBU_WIDE_UNIT_BASE + flat - 16 if 16 <= flat < 24 else flat
                    if flat == -1 and len(weights) == 1 and feed.get("active_index") in {254, 255}:
                        index = feed["active_index"]
            elif len(weights) == 1:
                index = feed.get("active_index")
            if index in routes:
                totals[index] = totals.get(index, 0.0) + float(weight)
    result = {}
    for index, route in routes.items():
        slot = slots.get(index) or {}
        if slot.get("present") is False:
            continue
        identity = slot.get("provider_uid")
        if index in totals:
            result[index] = {
                "counter": totals[index] * progress,
                "source": "slicer_progress",
                "identity": identity,
                "scale": [estimate.get("sha256"), totals[index]],
            }
        else:
            remaining = slot.get("remaining_g")
            if remaining is None:
                percent = slot.get("remaining_pct")
                capacity = _finite_positive(slot.get("reported_capacity_g"))
                if percent is not None and 0 <= percent <= 100 and capacity is not None:
                    remaining = capacity * percent / 100
            reading = _bambu_bits((report.get("ams") or {}).get("tray_reading_bits"))
            if (not reading and identity and remaining is not None
                    and math.isfinite(remaining) and remaining >= 0):
                result[index] = {
                    "counter": -remaining, "source": "ams_remaining",
                    "identity": identity, "scale": slot.get("reported_capacity_g"),
                }
    return result


def capture_bambu_usage(state, report, desired, estimate, observed_at):
    """Persistable deltas start at the observed spool binding, including late binds."""
    status = str(report.get("gcode_state") or "").upper()
    active = status in {"RUNNING", "PAUSE", "PREPARE"}
    terminal = status in {"FINISH", "FAILED"}
    key = _bambu_job_key(report)
    progress = _bambu_progress(report)
    tracker = state.get("tracker")
    new_run = (tracker is None or tracker.get("key") != key
               or (active and (tracker.get("terminal") or tracker.get("inactive")))
               or (active and progress is not None and tracker.get("progress") is not None
                   and progress + 0.02 < tracker["progress"]))
    events = []

    def emit(current, *, outcome=None, reason="periodic"):
        pending = current.get("pending") or {}
        if not pending and outcome is None:
            return
        sequence = current["segment_sequence"]
        events.append({
            "contract_version": 2,
            "event_id": current["job_id"] + ":%d" % sequence,
            "job_id": current["job_id"], "segment_sequence": sequence,
            "event_type": "terminal" if outcome is not None else "checkpoint",
            "reasons": ["terminal" if outcome is not None else reason],
            "started_at": current["started_at"], "observed_at": observed_at,
            "file_name": current.get("file_name"),
            "items": list(pending.values()),
            **({"outcome": outcome} if outcome is not None else {}),
        })
        current["pending"] = {}
        current["segment_sequence"] += 1
        current["last_emit"] = observed_at

    if not active and not terminal:
        if tracker is not None:
            emit(tracker, reason="disconnect")
            tracker["previous"] = {}
            tracker["inactive"] = True
        return events
    if new_run:
        if tracker is not None and not tracker.get("terminal"):
            emit(tracker, reason="disconnect")
        tracker = {
            "key": key, "job_id": "bambu:" + uuid.uuid4().hex,
            "file_name": str(report.get("subtask_name") or report.get("gcode_file") or "")[:500],
            "started_at": observed_at, "last_emit": observed_at,
            "segment_sequence": 1, "previous": {}, "pending": {},
            "terminal": terminal,
        }
        state["tracker"] = tracker
    if tracker.get("terminal"):
        return events
    if isinstance(report.get("ams_mapping"), list):
        tracker["ams_mapping"] = report["ams_mapping"]
    elif tracker.get("ams_mapping") is not None:
        report = {**report, "ams_mapping": tracker["ams_mapping"]}
    routes = _bambu_usage_routes(desired)
    counters = _bambu_usage_counters(report, routes, estimate)
    previous = tracker["previous"]
    proofs = {route["usage_route_proof"] for route in routes.values()}
    tag_bindings = {
        proof: identity for proof, identity in state.get("tag_bindings", {}).items()
        if proof in proofs
    }
    state["tag_bindings"] = tag_bindings
    current = {}
    for index, counter in counters.items():
        route = dict(routes[index])
        route.pop("initial_weight_g", None)
        proof = route["usage_route_proof"]
        identity = counter.get("identity")
        if identity is not None:
            bound = tag_bindings.setdefault(proof, identity)
            if bound != identity:
                # A replacement physical tag cannot inherit the old desired
                # spool merely because it occupies the same printer slot.
                continue
        point = {**counter, "route": route, "observed_at": observed_at}
        before = previous.get(str(index))
        current[str(index)] = point
        if (before is None or before["route"] != route
                or before["source"] != point["source"]
                or before.get("identity") != point.get("identity")
                or before.get("scale") != point.get("scale")):
            continue
        delta = point["counter"] - before["counter"]
        if delta <= 0 or not math.isfinite(delta):
            if point["source"] == "ams_remaining" and delta < 0:
                # A sensor rebound must not charge the same decrease again.
                # A new tag, route or calibrated capacity has its own baseline.
                point["counter"] = before["counter"]
            continue
        pending_key = str(route["spool_id"])
        pending = tracker["pending"].get(pending_key)
        if pending is not None and (
            pending["estimate_source"] != point["source"] or pending["slot_index"] != index
            or pending["usage_route_proof"] != proof
        ):
            emit(tracker, reason="slot_change")
            pending = None
        if pending is None:
            pending = {
                **route, "used_weight_g": 0.0, "consumption_kind": "estimated",
                "estimate_source": point["source"],
                "usage_started_at": before["observed_at"],
            }
            tracker["pending"][pending_key] = pending
        pending["used_weight_g"] += delta
    tracker["previous"] = current
    tracker["progress"] = progress
    elapsed = (datetime.datetime.fromisoformat(observed_at)
               - datetime.datetime.fromisoformat(tracker["last_emit"])).total_seconds()
    if terminal:
        emit(tracker, outcome="completed" if status == "FINISH" else "failed")
        tracker["terminal"] = True
    elif elapsed >= 300 or status == "PAUSE":
        emit(tracker, reason="paused" if status == "PAUSE" else "periodic")
    return events


def _bambu_stream_key(config):
    return hashlib.sha256(json.dumps([
        config.get("host"), config.get("serial"), config.get("access_code"),
        config.get("bridge_token"), config.get("physical_printer_id"),
        config.get("material_system_id"),
    ]).encode()).hexdigest()


def _buffer_bambu_usage_report(stream, report, observed_at):
    """Keep accounting transitions until the journal has accepted them."""
    feed = parse_bambu_feed(report) or {}
    signature = json.dumps([
        _bambu_job_key(report), report.get("gcode_state"), _bambu_progress(report),
        report.get("ams_mapping"),
        [{name: slot.get(name) for name in (
            "index", "present", "provider_uid", "remaining_g", "remaining_pct",
            "reported_capacity_g",
        )} for slot in feed.get("slots", [])],
    ], sort_keys=True)
    if signature == stream.get("usage_signature"):
        return
    stream["usage_signature"] = signature
    pending = stream.setdefault("usage_reports", [])
    observation = {"report": json.loads(json.dumps(report)), "observed_at": observed_at}
    if len(pending) >= 256:
        # Do not infer consumption across a lost observation interval. Already
        # journaled deltas remain intact, and the newest point starts a baseline.
        pending.clear()
        observation["report"]["_fh_observation_gap"] = True
    pending.append(observation)


class BambuBridgeRuntime:
    """One bounded daemon serializes all configured local Bambu observations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._restart_requested = False
        self._generation = 0
        self._last_snapshot_digest = {}
        self._last_snapshot_at = {}
        self._last_heartbeat_at = {}
        self._failure_count = {}
        self._retry_at = {}
        self._usage_states = {}
        self._usage_retry_at = {}
        self._streams = {}

    def _stream_observation(self, config):
        key = _bambu_stream_key(config)
        stream = self._streams.get(key)
        if stream is None or not stream["thread"].is_alive():
            generation = self._generation
            stream = {
                "ready": threading.Event(), "lock": threading.Lock(),
                "stop": threading.Event(),
                "binding": (config.get("physical_printer_id"), config.get("material_system_id")),
            }

            def receive(serial, report):
                with stream["lock"]:
                    merged = stream.get("report") or {}
                    if (report.get("gcode_state") in {"PREPARE", "RUNNING"}
                            and merged.get("gcode_state") in {"FINISH", "FAILED", "IDLE"}):
                        merged = {}
                    if any(report.get(field) and merged.get(field)
                           and report[field] != merged[field]
                           for field in ("task_id", "subtask_id", "gcode_file", "subtask_name")):
                        merged = {key: value for key, value in merged.items() if key != "ams_mapping"}
                    # Snapshot packets replace nested feed state; partial MQTT
                    # updates merge fields and slots by their provider IDs.
                    stream["report"] = _merge_bambu_report(merged, report)
                    _buffer_bambu_usage_report(
                        stream, stream["report"],
                        datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    stream["serial"] = serial
                    stream["at"] = time.monotonic()
                    stream["ready"].set()

            def run():
                with bind_lifecycle_generation(_BambuStreamLifecycle(self, stream["stop"]), generation):
                    while not self._stop.is_set() and not stream["stop"].is_set():
                        try:
                            read_bambu_lan_snapshot(config, timeout=3600, on_report=receive)
                        except Exception as exc:
                            if self._stop.is_set() or stream["stop"].is_set():
                                break
                            fh_log("Bambu LAN stream reconnecting: %s" % type(exc).__name__)
                            self._stop.wait(5)

            stream["thread"] = threading.Thread(target=run, name="filamenthub-bambu-lan", daemon=True)
            self._streams[key] = stream
            stream["thread"].start()
        deadline = time.monotonic() + BAMBU_MQTT_TIMEOUT
        while not stream["ready"].wait(0.1):
            if self._stop.is_set() or stream["stop"].is_set():
                raise PluginLifecycleStopped("Bambu stream observation stopped")
            if time.monotonic() >= deadline:
                break
        with stream["lock"]:
            if "report" not in stream or time.monotonic() - stream.get("at", 0) > 60:
                raise TimeoutError("Bambu LAN stream is unavailable")
            return stream["serial"], json.loads(json.dumps(stream["report"]))

    def _record_stream_usage(self, config, source_instance_id, report, observed_at,
                             stream_config=None):
        key = _bambu_stream_key(stream_config if stream_config is not None else config)
        stream = self._streams.get(key)
        if stream is None:
            return self._record_usage(config, source_instance_id, report, observed_at)
        with stream["lock"]:
            pending = list(stream.get("usage_reports", []))
        if not pending:
            return self._record_usage(config, source_instance_id, report, observed_at)
        for observation in pending:
            if self._stop.is_set():
                return
            if self._record_usage(config, source_instance_id, **observation) is False:
                return
            with stream["lock"]:
                queue = stream["usage_reports"]
                if queue and queue[0] is observation:
                    queue.pop(0)

    def _record_usage(self, config, source_instance_id, report, observed_at):
        binding = hashlib.sha256(json.dumps([
            config["physical_printer_id"], config["material_system_id"],
            source_instance_id, config["bridge_token"],
        ]).encode()).hexdigest()
        path = os.path.join(os.path.dirname(BAMBU_CONFIG_FILE), "bambu_usage", binding + ".json")
        state = self._usage_states.get(binding)
        if state is None:
            try:
                if os.path.getsize(path) > 8 * 1024 * 1024:
                    raise ValueError("Bambu usage journal exceeds limit")
                with open(path, encoding="utf-8") as handle:
                    state = json.load(handle)
                if not isinstance(state, dict) or state.get("version") != 1:
                    raise ValueError("Invalid Bambu usage journal")
            except FileNotFoundError:
                state = {"version": 1, "next_sequence": 1, "events": []}
        # A failed disk write must not advance the in-memory accounting baseline.
        state = json.loads(json.dumps(state))
        if report.get("_fh_observation_gap") and state.get("tracker") is not None:
            state["tracker"]["previous"] = {}
        key = _bambu_job_key(report)
        tracker = state.get("tracker")
        if not state.get("outbox") and not state["events"]:
            idle = report.get("gcode_state") not in {"PREPARE", "RUNNING", "PAUSE"}
            if idle and (tracker is None or (tracker.get("terminal") and tracker.get("key") == key)):
                self._usage_states[binding] = state
                return True
        if state.get("estimate_key") != key:
            state["estimate"] = None
            state["estimate_key"] = key
            state["file_retry_at"] = 0
        if (report.get("gcode_state") in {"RUNNING", "PAUSE", "FINISH", "FAILED"}
                and state.get("estimate") is None
                and not state.get("file_permission_denied")
                and time.time() >= state.get("file_retry_at", 0)):
            state["file_retry_at"] = time.time() + 600
            try:
                state["estimate"] = read_bambu_consumption_file(config, report)
            except PermissionError:
                state["file_permission_denied"] = True
                fh_log("Bambu artifact permission denied; file reads are disabled for this binding")
            except (OSError, ValueError, EOFError, ftplib.Error) as exc:
                fh_log("Bambu usage artifact unavailable: %s" % type(exc).__name__)
        status, body = http_get_bridge_json("/printer-bridge/snapshot", config["bridge_token"])
        observation_accepted = False
        if status == 200:
            desired = json.loads(body.decode("utf-8"))
            if not isinstance(desired, dict):
                raise ValueError("Invalid Bambu desired snapshot")
            if len(state["events"]) < 512:
                state["events"].extend(capture_bambu_usage(
                    state, report, desired, state.get("estimate"), observed_at
                ))
                observation_accepted = True
            else:
                fh_log("Bambu usage queue is full; draining before resuming observations")
        # An unavailable desired snapshot defers this observation. Keep the
        # last durable baseline; a changed route proof after reconnection starts
        # its own interval, while an unchanged assignment can resume accounting.
        if state.get("outbox") is None and state["events"]:
            events = state["events"][:32]
            state["events"] = state["events"][32:]
            state["outbox"] = {
                "material_system_id": config["material_system_id"],
                "provider": "bambu", "transport": "orca_plugin_lan",
                "source_instance_id": source_instance_id,
                "sequence": state["next_sequence"], "events": events,
            }
        write_json_atomic(path, state, mode=0o600)
        self._usage_states[binding] = state
        pending = state.get("outbox")
        if pending is None or time.monotonic() < self._usage_retry_at.get(binding, 0):
            return observation_accepted
        status, body, retry_after = http_post_bridge_json(
            "/printer-bridge/usage-batches", config["bridge_token"], pending
        )
        if status == 200:
            ack = json.loads(body.decode("utf-8"))
            if ack.get("accepted") is True and ack.get("ack_sequence") == pending["sequence"]:
                committed = dict(state)
                committed["outbox"] = None
                committed["next_sequence"] = pending["sequence"] + 1
                write_json_atomic(path, committed, mode=0o600)
                self._usage_states[binding] = committed
                self._usage_retry_at.pop(binding, None)
                return observation_accepted
        self._usage_retry_at[binding] = time.monotonic() + max(60, retry_after or 0)
        fh_log("Bambu usage upload pending: HTTP %s" % status)
        return observation_accepted

    def _start_locked(self):
        for stream in self._streams.values():
            stream["stop"].set()
        self._streams = {}
        self._stop.clear()
        self._generation += 1
        generation = self._generation
        self._thread = threading.Thread(
            target=self._run,
            args=(generation,),
            name="filamenthub-bambu-bridge",
            daemon=True,
        )
        self._thread.start()

    def authorize_external_operation(self, generation):
        """Linearize one observer I/O start against stop()."""
        with self._lock:
            if self._stop.is_set() or generation != self._generation:
                raise PluginLifecycleStopped(
                    "Bambu observer lifecycle generation has stopped"
                )

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self._stop.is_set():
                    # A blocking LAN request can outlive Orca's short unload
                    # wait. Restart only after that generation retires; clearing
                    # its shared stop flag here would revive the old observer.
                    self._restart_requested = True
                return
            self._restart_requested = False
            self._start_locked()

    def stop(self, wait_timeout=0.25):
        """Stop observations promptly when Orca unloads the plugin."""
        with self._lock:
            thread = self._thread
            self._restart_requested = False
            self._stop.set()
            for stream in self._streams.values():
                stream["stop"].set()
            self._wake.set()
        if (
            thread is not None
            and thread is not threading.current_thread()
            and wait_timeout > 0
        ):
            thread.join(wait_timeout)

    def wake(self):
        self.start()
        self._wake.set()

    def _retire_current_thread(self):
        current = threading.current_thread()
        with self._lock:
            if self._thread is current:
                self._thread = None
                if self._restart_requested:
                    self._restart_requested = False
                    self._start_locked()

    def _run(self, generation=None):
        if generation is not None:
            with bind_lifecycle_generation(self, generation):
                return self._run_loop()
        return self._run_loop()

    def _run_loop(self):
        # A slicer update or workstation power recovery can start many plugin
        # instances at once. Spread their first automatic LAN read/upload over
        # two minutes so a fleet restart cannot become an origin request wave.
        # An explicit user action calls wake() and interrupts this delay.
        self._wake.wait(random.uniform(0.0, BAMBU_STARTUP_JITTER_SECONDS))
        self._wake.clear()
        if self._stop.is_set():
            self._retire_current_thread()
            return
        while not self._stop.is_set():
            local = load_bambu_config()
            active = [item for item in local["printers"] if item.get("bridge_token")]
            active_keys = {_bambu_stream_key(item) for item in active}
            for key in list(self._streams):
                if key not in active_keys:
                    self._streams.pop(key)["stop"].set()
            if not active:
                self._retire_current_thread()
                return
            for config in active:
                if self._stop.is_set():
                    break
                binding_key = (
                    config.get("physical_printer_id"),
                    config.get("material_system_id"),
                )
                now_monotonic = time.monotonic()
                if now_monotonic < self._retry_at.get(binding_key, 0.0):
                    continue
                try:
                    serial, report = self._stream_observation(config)
                    if self._stop.is_set():
                        break
                    stream_config = config
                    config, source_instance_id = _prepare_bambu_observation(
                        config,
                        serial,
                    )
                    snapshot = build_bambu_bridge_snapshot(
                        config, source_instance_id, report
                    )
                    digest_payload = dict(snapshot)
                    digest_payload.pop("observed_at", None)
                    snapshot_digest = hashlib.sha256(
                        json.dumps(
                            digest_payload,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()
                    snapshot_changed = (
                        self._last_snapshot_digest.get(binding_key) != snapshot_digest
                    )
                    last_snapshot_at = self._last_snapshot_at.get(binding_key)
                    last_heartbeat_at = self._last_heartbeat_at.get(binding_key)
                    snapshot_due = (
                        last_snapshot_at is None
                        or now_monotonic - last_snapshot_at >= BAMBU_SNAPSHOT_MIN_SECONDS
                    )
                    heartbeat_due = (
                        last_heartbeat_at is None
                        or now_monotonic - last_heartbeat_at >= BAMBU_HEARTBEAT_SECONDS
                    )
                    if snapshot_changed and snapshot_due:
                        if self._stop.is_set():
                            break
                        status, _, retry_after = http_post_bridge_json(
                            "/printer-bridge/snapshot",
                            config["bridge_token"],
                            snapshot,
                        )
                        if self._stop.is_set():
                            break
                        if status == 200:
                            self._last_snapshot_digest[binding_key] = snapshot_digest
                            self._last_snapshot_at[binding_key] = now_monotonic
                            self._last_heartbeat_at[binding_key] = now_monotonic
                    elif heartbeat_due:
                        if self._stop.is_set():
                            break
                        status, _, retry_after = http_post_bridge_json(
                            "/printer-bridge/heartbeat",
                            config["bridge_token"],
                            {
                                "material_system_id": config["material_system_id"],
                                "provider": "bambu",
                                "transport": "orca_plugin_lan",
                                "source_instance_id": source_instance_id,
                                "observed_at": datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat(),
                                "capabilities": snapshot["capabilities"],
                            },
                        )
                        if self._stop.is_set():
                            break
                        if status == 200:
                            self._last_heartbeat_at[binding_key] = now_monotonic
                    else:
                        status = 200
                        retry_after = None
                    if status == 200 and not self._stop.is_set():
                        try:
                            self._record_stream_usage(
                                config, source_instance_id, report, snapshot["observed_at"],
                                stream_config=stream_config,
                            )
                        except Exception as exc:
                            fh_log("Bambu usage remains pending: %s" % type(exc).__name__)
                    if self._stop.is_set():
                        break
                    if status == 401:
                        # The owner may have removed the system from the site or
                        # replaced this binding elsewhere. The rejected token is
                        # authoritative: drop the LAN credentials too instead of
                        # leaving an unreachable secret behind forever.
                        remove_bambu_bridge(config["physical_printer_id"])
                        continue
                    if status == 200:
                        self._failure_count.pop(binding_key, None)
                        self._retry_at.pop(binding_key, None)
                    else:
                        failures = self._failure_count.get(binding_key, 0) + 1
                        self._failure_count[binding_key] = failures
                        base_delay = min(
                            BAMBU_RETRY_INITIAL_SECONDS * (2 ** (failures - 1)),
                            BAMBU_RETRY_MAX_SECONDS,
                        )
                        spread = base_delay * BAMBU_INTERVAL_JITTER_RATIO
                        delay = random.uniform(
                            max(0.0, base_delay - spread),
                            min(BAMBU_RETRY_MAX_SECONDS, base_delay + spread),
                        )
                        # A throttled server knows better than this backoff how
                        # long the credential has to stay quiet.
                        self._retry_at[binding_key] = now_monotonic + min(
                            max(delay, retry_after or 0.0),
                            BAMBU_RETRY_MAX_SECONDS,
                        )
                        fh_log("Bambu bridge upload failed: HTTP %s" % status)
                except Exception as exc:
                    if self._stop.is_set():
                        break
                    # Never stringify network exceptions: addresses are local
                    # configuration and do not belong in a support log.
                    failures = self._failure_count.get(binding_key, 0) + 1
                    self._failure_count[binding_key] = failures
                    base_delay = min(
                        BAMBU_RETRY_INITIAL_SECONDS * (2 ** (failures - 1)),
                        BAMBU_RETRY_MAX_SECONDS,
                    )
                    spread = base_delay * BAMBU_INTERVAL_JITTER_RATIO
                    self._retry_at[binding_key] = now_monotonic + random.uniform(
                        max(0.0, base_delay - spread),
                        min(BAMBU_RETRY_MAX_SECONDS, base_delay + spread),
                    )
                    fh_log("Bambu bridge poll failed: %s" % type(exc).__name__)
            if self._stop.is_set():
                break
            spread = BAMBU_POLL_SECONDS * BAMBU_INTERVAL_JITTER_RATIO
            self._wake.wait(random.uniform(
                BAMBU_POLL_SECONDS - spread,
                BAMBU_POLL_SECONDS + spread,
            ))
            self._wake.clear()
        self._retire_current_thread()


BAMBU_BRIDGE_RUNTIME = BambuBridgeRuntime()


def wake_bambu_bridge_runtime():
    """Wake the observer only from the currently loaded worker generation."""
    with _PLUGIN_RUNTIME_LOCK:
        expected_epoch = _PLUGIN_RUNTIME_EPOCH
    worker = globals().get("BACKGROUND_WORKER")
    authorize = getattr(worker, "authorize_external_operation", None)
    if callable(authorize):
        authorize()
    else:
        ensure_worker_generation_active()
    # Do not hold the worker lock across thread creation. The runtime epoch is
    # the second half of the hand-off: unload either follows this short wake and
    # stops it, or wins first and makes this callback a no-op. A later reload has
    # a different epoch and cannot be revived by the old callback.
    with _PLUGIN_RUNTIME_LOCK:
        if (
            not _PLUGIN_RUNTIME_ACTIVE
            or _PLUGIN_RUNTIME_EPOCH != expected_epoch
        ):
            return False
        BAMBU_BRIDGE_RUNTIME.wake()
        return True


_PLUGIN_RUNTIME_LOCK = threading.Lock()
_PLUGIN_RUNTIME_ACTIVE = False
_PLUGIN_RUNTIME_EPOCH = 0


def start_plugin_runtime(storage_initialized=False):
    """Start process-wide resources once after a host lifecycle load."""
    global _PLUGIN_RUNTIME_ACTIVE, _PLUGIN_RUNTIME_EPOCH
    with _PLUGIN_RUNTIME_LOCK:
        if _PLUGIN_RUNTIME_ACTIVE:
            return False
        _PLUGIN_RUNTIME_ACTIVE = True
        _PLUGIN_RUNTIME_EPOCH += 1
    try:
        if not storage_initialized:
            configure_plugin_storage()
        BACKGROUND_WORKER.activate()
        BAMBU_REVOKE_SCHEDULER.start()
        refresh_ui_language()
        if any(item.get("bridge_token") for item in load_bambu_config()["printers"]):
            BAMBU_BRIDGE_RUNTIME.start()
        repaired = repair_local_bundle_parents()
        if repaired:
            fh_log("repaired %d local bundle parent reference(s)" % repaired)
        return True
    except Exception:
        stop_plugin_runtime()
        raise


def stop_plugin_runtime():
    """Cooperatively stop plugin-owned work before the host releases Python."""
    global _PLUGIN_RUNTIME_ACTIVE, _PLUGIN_RUNTIME_EPOCH
    with _PLUGIN_RUNTIME_LOCK:
        if not _PLUGIN_RUNTIME_ACTIVE:
            return False
        _PLUGIN_RUNTIME_ACTIVE = False
        _PLUGIN_RUNTIME_EPOCH += 1
    BAMBU_REVOKE_SCHEDULER.stop()
    BACKGROUND_WORKER.stop()
    BAMBU_BRIDGE_RUNTIME.stop()
    return True


class _PluginRuntimeLifecycleMixin:
    """Use the common lifecycle supplied by every current capability base."""

    def on_load(self):
        configure_plugin_storage()
        start_plugin_runtime(storage_initialized=True)

    def on_cancelled(self):
        stop_plugin_runtime()

    def on_unload(self):
        stop_plugin_runtime()


# --------------------------------------------------------------------------- #
# Slices leaving the slicer
# --------------------------------------------------------------------------- #
# FilamentHub is told only what identifies a slice: the file's name and the
# machine it was sliced for, which Orca writes into the G-code's config block.
# No weights or times — those come from reading the file itself, so a listed
# slice and a calculation can never disagree. The path stays here, behind a key:
# it carries a person's folders, and the site asks for the file through the
# window bridge when they want a calculation.
# Older hosts have no slicing pipeline at all: the capability is declared only
# when the base class exists, so the plugin still loads there without it.
_SLICING = getattr(orca, "slicing", None)
_SLICE_CAPABILITY_BASE = getattr(_SLICING, "SlicingPipelineCapabilityBase", None)
_TAIL_BYTES = 300000
_SLICE_INDEX_FILE = os.path.join(PLUGIN_DIR, ".fh_slices.json")
_SLICE_REPORT_OUTBOX_FILE = os.path.join(PLUGIN_DIR, ".fh_slice_reports.json")
_SLICE_INDEX_LIMIT = 300
_SLICE_INDEX_LOCK = threading.Lock()
_SLICE_REPORT_OUTBOX_LIMIT = 300
_SLICE_REPORT_OUTBOX_LOCK = threading.Lock()
# Sending a print writes the G-code to a temporary file the host deletes right
# after the upload, so the path alone would be worthless by the time a person
# asks for a calculation. Those slices are kept here instead, newest few only.
_SLICE_CACHE_DIR = os.path.join(PLUGIN_DIR, "slices")
_SLICE_CACHE_FILES = 5
_SLICE_CACHE_BYTES = 500 * 1024 * 1024
_FHUB_IDENTITY_KEY = "fhub_identity_v1"
_FHUB_IDENTITY_KINDS = {
    "material_preset": (user_filament_dir, None),
    "print_profile": (user_process_dir, "process"),
    "printer_profile": (user_machine_dir, "machine"),
}
_FHUB_IDENTITY_RE = re.compile(
    r"^kind=(material_preset|print_profile|printer_profile);"
    r"(?:(?:tool=(\d+));)?id=(\d+)$"
)
_MAX_FHUB_TOOL_INDEX = 255
_MAX_FHUB_IDENTITY_ID = 2 ** 63 - 1


def _serialized_config_values(value):
    """Decode Orca's opt_serialize output without losing material slot order."""
    if value is None:
        return []
    try:
        return [item.strip() for item in next(csv.reader(
            [str(value)], delimiter=";", quotechar='"', escapechar="\\"
        ))]
    except (csv.Error, StopIteration):
        return []


def _managed_identity_id(value, identity_kind):
    """Resolve one selected profile only through a plugin-owned managed file."""
    spec = _FHUB_IDENTITY_KINDS.get(identity_kind)
    if spec is None or not isinstance(value, str):
        return None
    stem = value.strip().strip('"\'').replace("\\", "/").rsplit("/", 1)[-1]
    if not stem or stem in {".", ".."} or "\x00" in stem:
        return None
    folder_factory, managed_kind = spec
    folder = os.path.realpath(folder_factory())
    path = os.path.realpath(os.path.join(folder, stem + ".json"))
    try:
        if os.path.commonpath([folder, path]) != folder or not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            profile = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(profile, dict):
        return None
    if identity_kind == "material_preset":
        return managed_preset_id(path, profile)
    return managed_profile_id(path, profile, managed_kind)


def _fhub_identity_line(identity_kind, entity_id, tool_index=None):
    parts = ["kind=%s" % identity_kind]
    if tool_index is not None:
        parts.append("tool=%d" % int(tool_index))
    parts.append("id=%d" % int(entity_id))
    return "; %s = %s" % (_FHUB_IDENTITY_KEY, ";".join(parts))


def _parse_fhub_identity_value(value):
    match = _FHUB_IDENTITY_RE.fullmatch((value or "").strip())
    if match is None:
        return None
    identity_kind, tool_index, entity_id = match.groups()
    if identity_kind == "material_preset" and tool_index is None:
        return None
    if identity_kind != "material_preset" and tool_index is not None:
        return None
    entity_id = int(entity_id)
    if (
        entity_id <= 0
        or entity_id > _MAX_FHUB_IDENTITY_ID
        or (tool_index is not None and int(tool_index) > _MAX_FHUB_TOOL_INDEX)
    ):
        return None
    return {
        "kind": identity_kind,
        "tool_index": int(tool_index) if tool_index is not None else None,
        "id": entity_id,
    }


def _slice_managed_identities(ctx):
    """Stable FilamentHub identities selected in the resolved slice config."""
    identities = []
    try:
        material_values = _serialized_config_values(
            ctx.config_value("filament_settings_id")
        )
    except Exception:
        material_values = []
    for tool_index, value in enumerate(material_values):
        preset_id = _managed_identity_id(value, "material_preset")
        if preset_id is not None:
            identities.append({
                "kind": "material_preset",
                "tool_index": tool_index,
                "id": preset_id,
            })

    for config_key, identity_kind in (
        ("print_settings_id", "print_profile"),
        ("printer_settings_id", "printer_profile"),
    ):
        try:
            values = _serialized_config_values(ctx.config_value(config_key))
        except Exception:
            values = []
        if not values:
            continue
        profile_id = _managed_identity_id(values[0], identity_kind)
        if profile_id is not None:
            identities.append({"kind": identity_kind, "tool_index": None, "id": profile_id})
    return identities


def _append_fhub_slice_identities(path, identities):
    """Append missing namespaced identity comments; repeated host calls are safe."""
    lines = [
        _fhub_identity_line(item["kind"], item["id"], item.get("tool_index"))
        for item in identities
    ]
    if not lines:
        return True
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - _TAIL_BYTES))
            tail = fh.read().decode("utf-8", errors="replace")
        existing = {line.strip() for line in tail.splitlines()}
        missing = [line for line in lines if line not in existing]
        if not missing:
            return True
        with open(path, "ab") as fh:
            if size > 0 and not tail.endswith(("\n", "\r")):
                fh.write(b"\n")
            fh.write(("\n".join(missing) + "\n").encode("utf-8"))
        return True
    except OSError as exc:
        fh_log("slice identity annotation failed: %s" % exc)
        return False


def _read_slice_identity(path):
    """The preset and model Orca names in a produced G-code, plus its version."""
    identity = {}
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(2000)
            fh.seek(max(0, size - _TAIL_BYTES))
            tail = fh.read()
    except OSError:
        return None

    match = re.search(r"generated by OrcaSlicer\s+([\w.+-]+)", head)
    if match:
        identity["slicer_version"] = match.group(1)[:50]
    for line in tail.splitlines():
        s = line.strip()
        if not s.startswith(";"):
            continue
        if "printer_settings_id =" in s:
            identity["printer_settings_id"] = s.split("=", 1)[1].strip().strip('"')[:200]
        elif "print_settings_id =" in s:
            identity["print_settings_id"] = s.split("=", 1)[1].strip().strip('"')[:200]
        elif "printer_model =" in s:
            identity["printer_model"] = s.split("=", 1)[1].strip().strip('"')[:200]
        elif s.startswith("; %s =" % _FHUB_IDENTITY_KEY):
            item = _parse_fhub_identity_value(s.split("=", 1)[1])
            if item is None:
                continue
            if item["kind"] == "printer_profile":
                identity["fhub_printer_profile_id"] = item["id"]
            elif item["kind"] == "print_profile":
                identity["fhub_print_profile_id"] = item["id"]
    return identity or None


def _prune_slice_cache():
    """Keep the newest few copies while they fit the budget; the newest always."""
    try:
        names = os.listdir(_SLICE_CACHE_DIR)
    except OSError:
        return
    entries = []
    for name in names:
        cached = os.path.join(_SLICE_CACHE_DIR, name)
        try:
            info = os.stat(cached)
        except OSError:
            continue
        if os.path.isfile(cached):
            entries.append((info.st_mtime, info.st_size, cached))
    entries.sort(reverse=True)
    total = 0
    for position, (_mtime, size, cached) in enumerate(entries):
        total += size
        if position == 0 or (position < _SLICE_CACHE_FILES and total <= _SLICE_CACHE_BYTES):
            continue
        try:
            os.remove(cached)
        except OSError:
            pass


def _cache_slice_file(path, key):
    """A copy the plugin owns, for G-code the host is about to delete."""
    try:
        os.makedirs(_SLICE_CACHE_DIR, exist_ok=True)
        cached = os.path.join(_SLICE_CACHE_DIR, key + ".gcode")
        shutil.copyfile(path, cached)
    except OSError:
        return None
    _prune_slice_cache()
    return cached


def _remember_slice_path(path, file_name=""):
    """Keep path and name under a key so the site can ask by key alone.

    The name matters on its own: a cached copy is named after the key, and a
    calculation labelled with a hash tells a person nothing.
    """
    stamp = "%s|%s" % (path, os.path.getmtime(path))
    key = hashlib.sha256(stamp.encode("utf-8")).hexdigest()
    file_name = file_name or os.path.basename(path)
    # The host owns this working file, including File exports' .pp copies.
    # Keep our own bounded copy without probing the OS temporary directory.
    path = _cache_slice_file(path, key)
    if not path:
        raise OSError("Could not retain the sliced file")
    with _SLICE_INDEX_LOCK:
        index = _load_slice_index()
        index[key] = {"path": path, "name": file_name}
        if len(index) > _SLICE_INDEX_LIMIT:
            for stale in list(index)[: len(index) - _SLICE_INDEX_LIMIT]:
                index.pop(stale, None)
        write_json_atomic(_SLICE_INDEX_FILE, index, mode=0o600)
    return key


def _load_slice_index():
    try:
        with open(_SLICE_INDEX_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def slice_entry_for_key(key):
    """The file a key stands for and its name, if it is still where it was."""
    with _SLICE_INDEX_LOCK:
        index = _load_slice_index()
    entry = index.get(key)
    if isinstance(entry, str):  # written by 0.0.7 before names were kept
        entry = {"path": entry, "name": os.path.basename(entry)}
    if not isinstance(entry, dict):
        return None
    path = entry.get("path")
    if not path or not os.path.exists(path):
        return None
    return {"path": path, "name": entry.get("name") or os.path.basename(path)}


def slice_path_for_key(key):
    entry = slice_entry_for_key(key)
    return entry["path"] if entry else None


_SLICE_DELIVERY_TARGET_LOCK = threading.Lock()
_SLICE_DELIVERY_TARGET = None


def _set_slice_delivery_target(target):
    global _SLICE_DELIVERY_TARGET
    with _SLICE_DELIVERY_TARGET_LOCK:
        _SLICE_DELIVERY_TARGET = target


def _slice_delivery_target():
    with _SLICE_DELIVERY_TARGET_LOCK:
        return _SLICE_DELIVERY_TARGET


def _load_slice_report_outbox():
    try:
        with open(_SLICE_REPORT_OUTBOX_FILE, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _queue_slice_report(identity):
    source_key = identity.get("source_key")
    if not isinstance(source_key, str) or not source_key:
        raise ValueError("slice report has no source key")
    with _SLICE_REPORT_OUTBOX_LOCK:
        pending = [
            item for item in _load_slice_report_outbox()
            if item.get("source_key") != source_key
        ]
        pending.append(dict(identity))
        pending = pending[-_SLICE_REPORT_OUTBOX_LIMIT:]
        write_json_atomic(_SLICE_REPORT_OUTBOX_FILE, pending, mode=0o600)
    return source_key


def _acknowledge_slice_reports(source_keys):
    acknowledged = {
        key for key in source_keys
        if isinstance(key, str) and 0 < len(key) <= 64
    }
    if not acknowledged:
        return 0
    with _SLICE_REPORT_OUTBOX_LOCK:
        pending = _load_slice_report_outbox()
        kept = [item for item in pending if item.get("source_key") not in acknowledged]
        if len(kept) != len(pending):
            write_json_atomic(_SLICE_REPORT_OUTBOX_FILE, kept, mode=0o600)
        return len(pending) - len(kept)


def _deliver_pending_slice_reports(target=None):
    target = target or _slice_delivery_target()
    if target is None:
        return False
    with _SLICE_REPORT_OUTBOX_LOCK:
        pending = _load_slice_report_outbox()[:25]
    if not pending:
        return False
    target._deliver(
        "slice-report-batch",
        requestId="slice-report-" + uuid.uuid4().hex,
        slices=pending,
    )
    return True


def report_slice(gcode_path, output_name="", host=""):
    """Queue one slice for the signed-in FilamentHub page to report."""
    identity = _read_slice_identity(gcode_path)
    if identity is None:
        return False, ui_text("sliceUnreadable")
    identity["file_name"] = (
        os.path.basename(output_name or gcode_path) or "print.gcode"
    )[:300]
    identity["source_key"] = _remember_slice_path(gcode_path, identity["file_name"])
    identity["source_instance_id"] = plugin_source_instance_id()
    if host:
        identity["target_host"] = host[:50]
    _queue_slice_report(identity)
    _deliver_pending_slice_reports()
    return True, identity["file_name"]


# The name the host matches against a process preset's slicing_pipeline_plugin.
SLICE_CAPABILITY_NAME = "filamenthub-slice-reporter"
SLICE_SETTINGS_DEFAULTS = {"report_slices": False}
SLICE_SETTINGS_COPY_KEYS = (
    "sliceSettingsTitle", "sliceSettingsPurpose", "sliceSettingsLocal",
    "sliceSettingsRemote", "sliceSettingsPermission", "sliceSettingsEnable",
)
SLICE_SETTINGS_PAGE = SETTINGS_PAGE.split("</style>", 1)[0] + r"""</style>
<h3 data-copy="sliceSettingsTitle"></h3>
<p data-copy="sliceSettingsPurpose"></p>
<p class="note" data-copy="sliceSettingsLocal"></p>
<p class="note" data-copy="sliceSettingsRemote"></p>
<p class="note" data-copy="sliceSettingsPermission"></p>
<p><code id="slice-endpoint" style="overflow-wrap:anywhere"></code></p>
<label class="row" style="margin-top:16px"><input type="checkbox" id="report-slices"><span data-copy="sliceSettingsEnable"></span></label>
<script>
(function () {
  var copy = __COPY__;
  var checkbox = document.getElementById("report-slices");
  var settings = {};
  document.querySelectorAll("[data-copy]").forEach(function (node) {
    node.textContent = copy[node.getAttribute("data-copy")];
  });
  document.getElementById("slice-endpoint").textContent = __ENDPOINT__;
  checkbox.disabled = true;
  window.orca.onConfig(function (config) {
    settings = config && typeof config === "object" && !Array.isArray(config) ? config : {};
    checkbox.checked = settings.report_slices === true;
    checkbox.disabled = !!(window.orca.getContext() || {}).readOnly;
  });
  checkbox.addEventListener("change", function () {
    settings.report_slices = checkbox.checked;
    window.orca.saveConfig(settings);
  });
})();
</script>"""


def render_slice_settings_page():
    catalog = resolved_ui_catalog(refresh_ui_language())
    copy = {key: catalog.get(key, key) for key in SLICE_SETTINGS_COPY_KEYS}
    return SLICE_SETTINGS_PAGE.replace(
        "__COPY__", json.dumps(copy, ensure_ascii=False).replace("</", "<\\/")
    ).replace(
        "__ENDPOINT__", json.dumps(API_BASE + "/orcaslicer/slices").replace("</", "<\\/")
    )


def slice_reporting_enabled(capability):
    get_config = getattr(capability, "get_config", None)
    if not callable(get_config):
        return False
    try:
        settings = json.loads(get_config())
    except Exception as exc:
        fh_log("slice settings unreadable: %s" % type(exc).__name__)
        return False
    return isinstance(settings, dict) and settings.get("report_slices") is True


class _SliceReporterMixin(_PluginRuntimeLifecycleMixin):
    def get_name(self):
        return SLICE_CAPABILITY_NAME

    def has_config_ui(self):
        return True

    def get_config_ui(self):
        return render_slice_settings_page()

    def get_default_config(self):
        return dict(SLICE_SETTINGS_DEFAULTS)

    def execute(self, ctx):
        step = getattr(ctx, "step", None)
        step_enum = getattr(_SLICING, "Step", None)
        post = getattr(step_enum, "psGCodePostProcess", None)
        if post is None:
            post = getattr(_SLICING, "psGCodePostProcess", None)
        if step is not None and post is not None and step != post:
            return orca.ExecutionResult.skipped(ui_text("sliceWrongStep"))

        if not slice_reporting_enabled(self):
            return orca.ExecutionResult.skipped(ui_text("sliceReportingDisabled"))

        path = getattr(ctx, "gcode_path", "") or ""
        if not path or not os.path.exists(path):
            return orca.ExecutionResult.skipped(ui_text("sliceNotReady"))

        try:
            if not _append_fhub_slice_identities(path, _slice_managed_identities(ctx)):
                return orca.ExecutionResult.skipped(ui_text("sliceUnreadable"))
            sent, reason = report_slice(
                path,
                getattr(ctx, "output_name", "") or "",
                getattr(ctx, "host", "") or "",
            )
        except Exception as exc:
            # A failed report must never spoil an export the person asked for.
            fh_log("slice report failed: %s" % exc)
            return orca.ExecutionResult.skipped(ui_text("sliceReportFailed"))
        if not sent:
            return orca.ExecutionResult.skipped(reason)
        return orca.ExecutionResult.success(ui_text("sliceQueued", name=reason))


if _SLICE_CAPABILITY_BASE is not None:
    class FilamentHubSliceReporter(_SliceReporterMixin, _SLICE_CAPABILITY_BASE):
        pass
else:
    FilamentHubSliceReporter = None


# --------------------------------------------------------------------------- #
# The capability
# --------------------------------------------------------------------------- #
class FilamentHubCatalog(
    _PluginRuntimeLifecycleMixin,
    orca.script.ScriptPluginCapabilityBase,
):
    win = None

    def get_name(self):
        return "FilamentHub Catalog"

    def _open(self):
        # Idempotent: repeated Run keeps the existing host-managed window.
        if self.win is not None and self.win.is_open():
            return False
        self._session_sync_started = False
        self._local_window = None
        self._local_dialog_session = ""
        self._local_dialog_context = None
        self._direct_bridge_session = secrets.token_urlsafe(32)
        self.win = orca.host.ui.create_window(
            title="FilamentHub", html=render_direct_page(self._direct_bridge_session),
            width=1080,
            height=760,
            on_message=self.on_message,
            on_close=self.on_close,
        )
        _set_slice_delivery_target(self)
        return True

    def _report_local_dialog_state(self, open_, outcome=None):
        context = self._local_dialog_context or {}
        provider = context.get("provider")
        if provider not in {"bambu", "moonraker"}:
            return
        payload = {"provider": provider, "open": bool(open_)}
        if provider == "bambu":
            payload.update(
                physicalPrinterId=context.get("physicalPrinterId"),
                materialSystemId=context.get("materialSystemId"),
            )
        if not open_ and outcome in {"saved", "cancelled", "removed"}:
            payload["outcome"] = outcome
        self._deliver("local-printer-setup-state", **payload)

    def _on_local_dialog_close(self):
        if self._local_window is None:
            return
        self._local_window = None
        self._local_dialog_session = ""
        self._report_local_dialog_state(False, "cancelled")
        self._local_dialog_context = None

    def _close_local_dialog(self, outcome="cancelled"):
        window = self._local_window
        if window is None:
            return
        self._report_local_dialog_state(False, outcome)
        self._local_window = None
        self._local_dialog_session = ""
        self._local_dialog_context = None
        try:
            window.close()
        except Exception:
            pass

    def _on_local_dialog_message(self, msg):
        """Bind messages from the native setup window to that window instance.

        Older Orca hosts can serialize the page message differently and may not
        preserve the extra session field reliably.  The callback itself is
        already registered only on the separately-created local dialog, so it
        is the stronger binding boundary.  Keep the direct page's bridge
        session checks unchanged.
        """
        fh_log("Local setup host callback entered: %s" % type(msg).__name__)
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except (TypeError, ValueError):
                fh_log("Local setup host callback rejected non-JSON string")
                return
        if not isinstance(msg, dict):
            fh_log("Local setup host callback rejected non-object payload")
            return
        fh_log(
            "Local setup host callback payload: type=%s source=%s has_bridge=%s has_local=%s"
            % (
                str(msg.get("type") or "")[:80],
                str(msg.get("source") or "")[:80],
                bool(msg.get("bridgeSession")),
                bool(msg.get("localDialogSession")),
            )
        )
        bound = dict(msg)
        bound.pop("bridgeSession", None)
        bound["localDialogSession"] = self._local_dialog_session
        self.on_message(bound)

    def _open_local_dialog(self, action):
        """Open one host-owned credential dialog without any local listener."""
        if not isinstance(action, dict):
            return False
        action_type = action.get("type")
        provider = "bambu" if action_type == "configure-bambu" else "moonraker"
        if action_type not in {"configure-bambu", "printer-setup-manual"}:
            return False
        if provider == "bambu":
            action = {
                key: action.get(key)
                for key in (
                    "type",
                    "physicalPrinterId",
                    "materialSystemId",
                    "printerName",
                    "pairingCode",
                    "connectionRef",
                )
            }
        else:
            action = {
                key: action.get(key)
                for key in ("type", "requestId", "host", "connectionRef", "copy")
            }
        current = self._local_window
        if current is not None:
            try:
                if current.is_open():
                    return False
            except Exception:
                pass
        self._local_dialog_session = secrets.token_urlsafe(32)
        self._local_dialog_context = {
            "provider": provider,
            "physicalPrinterId": action.get("physicalPrinterId"),
            "materialSystemId": action.get("materialSystemId"),
        }
        self._local_window = orca.host.ui.create_window(
            title="FilamentHub",
            html=render_local_dialog(action, self._local_dialog_session),
            width=640,
            height=720 if provider == "bambu" else 460,
            on_message=(
                self._on_local_dialog_message
                if provider == "bambu"
                else self.on_message
            ),
            on_close=self._on_local_dialog_close,
        )
        self._report_local_dialog_state(True)
        return True

    def _host_profiles(self, scope):
        profiles = {}
        for kind in PROFILE_KINDS:
            if sync_scope_includes(scope, kind):
                items, complete = scan_user_profiles_checked(kind)
                profiles[kind] = {"items": items, "complete": complete}
        return profiles

    def _start_sync(self, scope="all", announce=True, operation_id="", trigger="manual"):
        if scope not in SYNC_SCOPES:
            return False
        saved = load_saved_auth() or {}
        token = saved.get("accessToken") or ""
        if not token:
            # An automatic run without a capability simply waits for the page
            # to hand one over after sign-in; only an explicit Sync explains it.
            if operation_id or trigger == "manual":
                self._deliver_sync_result(
                    ui_text("syncSignIn"),
                    operation_id=operation_id,
                    scope=scope,
                    status="warning",
                )
            return False
        operation_id = operation_id or ("sync-" + secrets.token_hex(8))
        include_filaments = sync_scope_includes(scope, "filament")
        include_printers = sync_scope_includes(scope, "machine")
        known = self._known_filament_preset_names() if include_filaments else set()
        if include_filaments:
            refresh_user_preset_folder()
        observations = observe_printer_presets() if include_printers else []
        moonraker_connections = observe_local_moonraker_connections(observations)
        source_instance_id = plugin_source_instance_id()
        active_filaments = scan_active_user_filaments() if include_filaments else []
        loaded_preset_ids = loaded_managed_preset_ids() if include_filaments else None
        host_profiles = self._host_profiles(scope)
        BACKGROUND_WORKER.submit(
            self._do_sync,
            token,
            known,
            announce,
            active_filaments,
            host_profiles,
            observations,
            source_instance_id,
            moonraker_connections,
            loaded_preset_ids,
            scope,
            operation_id,
            trigger,
        )
        return True

    def _auto_sync(self, announce=False, scope="all", trigger="auto"):
        return self._start_sync(
            scope=scope,
            announce=announce,
            trigger=trigger,
        )

    def execute(self):
        self._open()
        return orca.ExecutionResult.success(ui_text("catalogOpened"))

    def on_close(self):
        self._close_local_dialog()
        if _slice_delivery_target() is self:
            _set_slice_delivery_target(None)
        self.win = None

    def on_unload(self):
        self.on_close()
        stop_plugin_runtime()

    def _known_filament_preset_names(self):
        # Names of every filament preset OrcaSlicer currently has (system + user).
        # Read on the UI thread; used to validate an imported preset's parent.
        names = set()
        try:
            filaments = orca.host.preset_bundle().filaments
            for i in range(filaments.size()):
                names.add(filaments.preset(i).name)
        except Exception:
            pass
        return names

    def _slice_hook_state(self):
        """Whether the process preset in use asks the host to run our step.

        Host reads only happen on the UI thread, so this is gathered in
        on_message and handed to the worker that answers the site.
        """
        try:
            preset = orca.host.preset_bundle().current_process_preset()
            enabled = preset.config_value("slicing_pipeline_plugin")
            name = preset.name
        except Exception:
            return None
        if isinstance(enabled, str):
            enabled = [part for part in re.split(r"[;,]", enabled) if part]
        elif not isinstance(enabled, (list, tuple)):
            enabled = []
        return {
            "enabled": SLICE_CAPABILITY_NAME in [str(item).strip() for item in enabled],
            "preset": str(name or "")[:120],
        }

    def _deliver(self, message_type, **data):
        payload = {"source": "filamenthub-host", "type": message_type}
        payload.update(data)
        return post_window(self.win, payload)

    def _deliver_local(self, message_type, **data):
        payload = {"source": "filamenthub-host", "type": message_type}
        payload.update(data)
        return post_window(self._local_window, payload)

    def _deliver_sync_result(self, text, draft_count=0, operation_id="", scope="all",
                             status="success", contours=None, notify=True,
                             connection_review=False):
        draft_count = max(0, int(draft_count or 0))
        payload = {
            "text": text,
            "draftCount": draft_count,
            "operationId": operation_id,
            "scope": scope,
            "status": status,
            "contours": list(contours or []),
            "notify": bool(notify),
            "connectionReview": bool(connection_review),
        }
        self._deliver("sync-result", **payload)

    def _deliver_notice(self, text, status="info"):
        payload = {"text": text, "status": status}
        self._deliver("plugin-notice", **payload)

    def _deliver_printer_bundle_result(
        self,
        request_id,
        text,
        status="success",
        physical_printer_id=0,
        installed=False,
    ):
        payload = {
            "requestId": request_id,
            "text": text,
            "status": status,
            "physicalPrinterId": int(physical_printer_id or 0),
            "installed": bool(installed),
        }
        self._deliver("printer-bundle-result", **payload)

    def _deliver_printer_bundle_status(self, request_id, installed_printer_ids):
        payload = {
            "requestId": request_id,
            "status": "success",
            "installedPrinterIds": sorted(set(installed_printer_ids)),
        }
        self._deliver("printer-bundle-status-result", **payload)

    def _deliver_printer_recovery(self, message_type, request_id, status="success", **data):
        payload = {"requestId": request_id, "status": status}
        payload.update(data)
        self._deliver(message_type, **payload)

    def _deliver_recovery(self, items):
        self._deliver("recover-list", items=items)

    def _deliver_slice_result(self, result):
        self._deliver("parsed-slice", result=result)

    def _deliver_happy_hare_result(self, request_id, result):
        self._deliver(
            "happy-hare-result",
            requestId=request_id,
            result=result,
        )

    def _deliver_bambu_material_result(self, request_id, result):
        self._deliver(
            "bambu-material-result",
            requestId=request_id,
            result=result,
        )

    def _begin_immediate_material_request(self, provider, request_id, fingerprint):
        """Bound and deduplicate device commands within this open host session."""
        if not hasattr(self, "_material_request_lock"):
            self._material_request_lock = threading.Lock()
            self._material_requests = {}
        now = time.monotonic()
        key = (provider, request_id)
        cached_result = None
        replay_mismatch = False
        with self._material_request_lock:
            self._material_requests = {
                item_key: item for item_key, item in self._material_requests.items()
                if item["expires"] > now
            }
            existing = self._material_requests.get(key)
            if existing is not None:
                if existing.get("fingerprint") != fingerprint:
                    replay_mismatch = True
                else:
                    cached_result = existing.get("result")
            else:
                self._material_requests[key] = {
                    "expires": now + 300.0,
                    "fingerprint": fingerprint,
                    "result": None,
                }
        if existing is not None:
            if replay_mismatch:
                cached_result = {
                    "ok": False,
                    "code": "replay_mismatch",
                    "operation": fingerprint[0],
                    "physicalPrinterId": fingerprint[1],
                    "materialSystemId": fingerprint[2],
                    "applied": False,
                    "observationUploaded": False,
                }
            if cached_result is not None:
                if provider == "bambu":
                    self._deliver_bambu_material_result(request_id, cached_result)
                else:
                    self._deliver_happy_hare_result(request_id, cached_result)
            return False
        return True

    def _finish_immediate_material_request(self, provider, request_id, result):
        if hasattr(self, "_material_request_lock"):
            with self._material_request_lock:
                entry = self._material_requests.get((provider, request_id))
                if entry is not None:
                    entry["result"] = dict(result)
        if provider == "bambu":
            self._deliver_bambu_material_result(request_id, result)
        else:
            self._deliver_happy_hare_result(request_id, result)

    def _setup_discovery(
        self,
        context,
        observations=(),
        refresh=False,
        scan_network=True,
    ):
        cached = getattr(self, "_printer_discovery", {})
        now = time.monotonic()
        same_account = cached.get("account_scope") == context["account_scope"]
        if same_account and now < cached.get("expires", 0) and (
            not scan_network
            or not refresh
            or now - cached.get("scanned", 0) < 5
        ):
            return cached
        if scan_network:
            network, complete = discover_lan_printers()
        else:
            network, complete = [], False
        known_bambu = [item for item in load_bambu_config()["printers"]
                       if item.get("device_identity") and item["device_identity"] ==
                       _bambu_device_identity(context["discovery_key"], item.get("serial"))]
        bound = {item["connection_ref"]: item for item in context["bindings"]
                 if item.get("status") == "bound"}
        items = {}
        for candidate in network:
            item = dict(candidate)
            identity = item.get("serial") or item.get("print_host") or item["host"]
            ref = "lan-" + _printer_evidence_token(context["discovery_key"], "discovery", item["provider"] + "\0" + identity)
            item.update(connection_ref=ref, account_scope=context["account_scope"])
            item["physical_printer_id"] = (bound.get(ref) or {}).get("physical_printer_id")
            if item["provider"] == "bambu":
                matches = [known for known in known_bambu if _normalized_bambu_serial(known.get("serial")) == item.get("serial")]
                if len(matches) == 1:
                    item["physical_printer_id"] = matches[0]["physical_printer_id"]
            items[ref] = item
        # Saved access remains useful while the device is quiet. Never call it found.
        for known in known_bambu:
            if any(item.get("physical_printer_id") == known["physical_printer_id"] for item in items.values()):
                continue
            ref = "lan-" + _printer_evidence_token(context["discovery_key"], "discovery", "bambu\0" + known["serial"])
            items[ref] = {"provider": "bambu", "connection_ref": ref, "host": known["host"],
                          "serial": known["serial"], "label": "Bambu Lab", "source": "saved",
                          "physical_printer_id": known["physical_printer_id"], "account_scope": context["account_scope"]}
        for observation in observations:
            model = str(observation.get("printer_model") or "")
            if not model.lower().startswith("bambu") and observation.get("host_type") != "bambu":
                continue
            host = _bambu_host_hint(observation.get("print_host"))
            if not host or any(item.get("host") == host for item in items.values()):
                continue
            ref = observation.get("connection_ref") or "lan-" + _printer_evidence_token(context["discovery_key"], "discovery", "bambu\0" + host)
            items[ref] = {"provider": "bambu", "connection_ref": ref, "host": host,
                          "label": str(observation.get("preset_name") or model or "Bambu Lab")[:200],
                          "printer_model": model[:200], "source": "profile",
                          "physical_printer_id": (bound.get(ref) or {}).get("physical_printer_id"),
                          "account_scope": context["account_scope"]}
        cached = {
            "account_scope": context["account_scope"],
            "scanned": now if scan_network else 0,
            "expires": now + 300,
            "items": list(items.values())[:_DISCOVERY_LIMIT],
            "complete": complete,
            "attempted": scan_network,
        }
        self._printer_discovery = cached
        return cached

    def _do_prepare_bambu(self, binding, observations, token):
        refresh = binding.get("refresh") is True
        context = {}
        # Explicit Search local network is a host-local operation. Do not make
        # it wait for, or depend on, the remote setup context endpoint.
        if token and not refresh:
            try:
                context = printer_setup_context(token)
            except (OSError, RuntimeError, ValueError, TypeError, KeyError):
                # The selected Orca profile is still a useful local-only hint
                # when an old account token cannot resolve the exact binding.
                context = {}
        candidates = []
        discovery_attempted = refresh
        discovery_complete = True
        if refresh:
            try:
                network, discovery_complete = discover_lan_printers()
            except (OSError, PluginLifecycleStopped):
                network, discovery_complete = [], False
            candidates = [dict(item) for item in network if item.get("provider") == "bambu"]
        if context:
            discovery = self._setup_discovery(
                context,
                observations,
                refresh=False,
                scan_network=False,
            )
            if not refresh:
                discovery_attempted = discovery.get("attempted") is True
                discovery_complete = discovery.get("complete", True)
                candidates = [dict(item) for item in discovery["items"] if item["provider"] == "bambu"
                              and item.get("physical_printer_id") in {None, binding["physicalPrinterId"]}]
            selected_ref = binding.get("connectionRef")
            candidates.sort(key=lambda item: (item["connection_ref"] != selected_ref,
                            item.get("physical_printer_id") != binding["physicalPrinterId"], item["source"] != "network"))
        seen = {item["host"].lower() for item in candidates}
        candidates.extend(dict(item, source="profile") for item in bambu_host_candidates(
            observations, context, binding["physicalPrinterId"],
        ) if item["host"].lower() not in seen)
        # Only the host-owned local dialog receives addresses/serials. The web gets opaque refs.
        saved_connections = load_bambu_config()["printers"]
        has_saved_connection = any(
            item.get("physical_printer_id") == binding["physicalPrinterId"]
            for item in saved_connections
        )
        if context:
            has_saved_connection = any(
                item.get("physical_printer_id") == binding["physicalPrinterId"]
                and item.get("device_identity") == _bambu_device_identity(
                    context["discovery_key"], item.get("serial")
                )
                for item in saved_connections
            )
        self._deliver_native_setup(
            "bambu-setup-candidates",
            requestId=binding.get("requestId", ""),
            physicalPrinterId=binding["physicalPrinterId"],
            materialSystemId=binding["materialSystemId"],
            pairingCode=binding["pairingCode"],
            candidates=[{key: item.get(key, "") for key in ("host", "label", "serial", "source", "connection_ref")}
                        for item in candidates[:_DISCOVERY_LIMIT]],
            discoveryComplete=discovery_complete,
            discoveryAttempted=discovery_attempted,
            hasSavedConnection=has_saved_connection,
        )

    def _deliver_native_setup(self, message_type, **payload):
        if message_type == "printer-setup-auth-required":
            action = dict(payload)
            action["type"] = "printer-setup-manual"
            self._open_local_dialog(action)
            return
        if message_type in {"bambu-setup-candidates", "bambu-setup-result"}:
            if self._deliver_local(message_type, **payload):
                return
        self._deliver(message_type, **payload)

    def _do_check_slices(self, wanted, hook):
        alive = [key for key in wanted if slice_path_for_key(key)]
        self._deliver("slices-alive", keys=alive, hook=hook)

    def _do_configure_bambu(
        self,
        physical_printer_id,
        material_system_id,
        host,
        access_code,
        serial,
        pairing_code,
        request_id="",
    ):
        def finish(key, status):
            if request_id:
                self._deliver_native_setup("bambu-setup-result", requestId=request_id, ok=status == "success", code=key)
            else:
                self._deliver_notice(ui_text(key), status)

        bridge_token = ""
        previous_local = None
        try:
            _resolved_bambu_address(host)
            # An empty serial is the normal case: the wildcard report topic
            # carries it, so the address and the access code are enough.
            serial = _normalized_bambu_serial(serial)
            pending = {
                "physical_printer_id": physical_printer_id,
                "material_system_id": material_system_id,
                "host": host,
                "access_code": access_code,
                "serial": serial,
            }
            fh_log("Bambu setup: reading local MQTT snapshot")
            discovered_serial, report = read_bambu_lan_snapshot(pending)
            connected_serial = _normalized_bambu_serial(discovered_serial) or serial
            if not connected_serial:
                fh_log("Bambu setup: MQTT response did not contain a serial")
                finish("bambuSerialRequired", "error")
                return
            fh_log("Bambu setup: local MQTT snapshot received")
            local = load_bambu_config()
            _assert_bambu_binding_available(
                local,
                physical_printer_id,
                connected_serial,
            )
            # A missing config produces a fresh source id. Persist it before
            # pairing so configure_bambu_bridge() cannot generate a second id
            # and make the immediately following snapshot fail its binding.
            # This also proves local durability before the one-time code is
            # consumed on the server.
            save_bambu_config(local)
            previous_local = json.loads(json.dumps(local))
            # Pairing rotates the server credential immediately. Reserve one
            # durable compensation slot before consuming the one-time code so
            # a later network failure can never evict an older pending token.
            if not can_queue_fresh_bambu_revoke():
                finish("bambuPairingFailed", "error")
                return
            pair_status, pair_body = http_post_json(
                "/printer-bridge/pair",
                "",
                {
                    "pairing_code": pairing_code,
                    "provider": "bambu",
                    "transport": "orca_plugin_lan",
                    "source_instance_id": local["source_instance_id"],
                    "plugin_version": PLUGIN_VERSION,
                    "capabilities": _bambu_capabilities(report),
                },
            )
            fh_log("Bambu setup: pairing request returned HTTP %s" % pair_status)
            if pair_status != 200:
                finish("bambuPairingFailed", "error")
                return
            paired = json.loads(pair_body.decode("utf-8"))
            bridge_token = paired.get("bridge_token") if isinstance(paired, dict) else ""
            if not isinstance(bridge_token, str) or not bridge_token.startswith("fhpb_"):
                finish("bambuPairingFailed", "error")
                return
            if (paired.get("physical_printer_id") != physical_printer_id
                    or paired.get("material_system_id") != material_system_id):
                # Reject the newly issued credential without replacing or
                # removing a previous local connection for this printer.
                rejected_token, bridge_token = bridge_token, ""
                revoke_fresh_bridge_token(rejected_token)
                finish("bambuPairingFailed", "error")
                return
            device_identity = _bambu_device_identity(
                paired.get("printer_discovery_key"),
                connected_serial,
            )
            configure_bambu_bridge(
                physical_printer_id,
                material_system_id,
                host,
                access_code,
                connected_serial,
                bridge_token,
                device_identity,
            )
            configured = load_bambu_config()
            stored = next(
                (
                    item
                    for item in configured["printers"]
                    if item["physical_printer_id"] == physical_printer_id
                ),
                None,
            )
            if stored is None:
                raise ValueError("Bambu bridge was not persisted")
            snapshot = build_bambu_bridge_snapshot(
                stored,
                configured["source_instance_id"],
                report,
            )
            snapshot_status, _, _ = http_post_bridge_json(
                "/printer-bridge/snapshot", bridge_token, snapshot
            )
            if snapshot_status in {401, 409}:
                if snapshot_status == 409:
                    revoke_fresh_bridge_token(bridge_token)
                remove_bambu_bridge(physical_printer_id)
                finish("bambuPairingFailed", "error")
                return
            if snapshot_status != 200:
                # The durable local binding is valid and the background
                # reader will retry.  Do not claim that data was received;
                # the site distinguishes a paired bridge from last_seen_at.
                fh_log("Initial Bambu bridge upload failed: HTTP %s" % snapshot_status)
        except (
            OSError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            PluginLifecycleStopped,
        ) as exc:
            fh_log("Bambu setup failed: %s" % type(exc).__name__)
            # Pairing consumes the one-time code.  If local persistence fails
            # afterwards, revoke the fresh server credential so the site never
            # remains green while no local reader can possibly use it.
            if bridge_token:
                try:
                    revoke_fresh_bridge_token(bridge_token)
                except (OSError, TypeError, ValueError):
                    pass
                if previous_local is not None:
                    remove_interrupted_bambu_binding(
                        physical_printer_id,
                        bridge_token,
                        previous_local,
                    )
            finish("bambuInvalid", "error")
            return
        wake_bambu_bridge_runtime()
        finish("bambuSaved", "success")

    def _do_remove_bambu(self, physical_printer_id):
        local = load_bambu_config()
        configured = next(
            (
                item
                for item in local["printers"]
                if item["physical_printer_id"] == physical_printer_id
            ),
            None,
        )
        bridge_token = configured.get("bridge_token") if configured else ""
        if bridge_token:
            revoke_status = http_delete_bridge("/printer-bridge/connection", bridge_token)
            if revoke_status not in {204, 401}:
                self._deliver_notice(ui_text("bambuRemoveFailed"), "error")
                return
        remove_bambu_bridge(physical_printer_id)
        wake_bambu_bridge_runtime()
        self._deliver_notice(ui_text("bambuRemoved"), "success")

    def _do_bambu_material_action(
        self,
        request_id,
        operation,
        physical_printer_id,
        material_system_id,
        token,
        host_profiles,
        expected_desired=None,
    ):
        def finish(**result):
            result.setdefault("operation", operation)
            result.setdefault("physicalPrinterId", physical_printer_id)
            result.setdefault("materialSystemId", material_system_id)
            self._deliver_bambu_material_result(request_id, result)

        if not token:
            finish(ok=False, code="auth")
            return
        local, binding = _bambu_local_binding(
            physical_printer_id, material_system_id
        )
        if binding is None:
            finish(ok=False, code="connection_not_found")
            return
        inventory, inventory_error = _plugin_material_server_inventory(
            token, source_instance_id=local["source_instance_id"]
        )
        if inventory_error or inventory is None:
            finish(ok=False, code=inventory_error or "server")
            return
        device = next(
            (
                item
                for item in inventory["printers"]
                if item.get("id") == physical_printer_id
            ),
            None,
        )
        if device is None:
            finish(ok=False, code="connection_not_found")
            return
        assignments = _bambu_server_assignments(device, material_system_id)
        if assignments is None:
            finish(ok=False, code="material_system_not_found")
            return
        current_expected = _bambu_assignment_snapshot(assignments)
        if operation == "apply" and expected_desired != current_expected:
            finish(ok=False, code="stale_preview", desiredAssignments=current_expected)
            return
        try:
            serial, report = read_bambu_lan_snapshot(binding)
        except (OSError, PermissionError, TimeoutError, ValueError):
            finish(ok=False, code="unreachable")
            return
        if binding.get("serial") and serial != binding.get("serial"):
            finish(ok=False, code="printer_changed")
            return
        changes, unresolved, targets = _bambu_material_preview(
            report, assignments, host_profiles
        )
        print_state = _BAMBU_STATES.get(
            str(report.get("gcode_state") or "").strip().upper(), "unknown"
        )
        common = {
            "printState": print_state,
            "changes": changes,
            "unresolved": unresolved,
            "desiredAssignments": current_expected,
        }
        if operation == "preview":
            finish(ok=True, **common)
            return
        if not changes:
            finish(ok=True, applied=True, remainingChanges=[], **common)
            return
        selected_targets = {
            item["slot"]: targets[item["slot"]]
            for item in changes
            if item["slot"] in targets
        }
        try:
            applied = apply_bambu_material_targets(binding, selected_targets)
        except (OSError, PermissionError, TimeoutError, ValueError):
            finish(ok=False, code="unreachable", **common)
            return
        final_report = applied.get("report") if isinstance(applied, dict) else None
        if isinstance(final_report, dict):
            snapshot = build_bambu_bridge_snapshot(
                binding,
                local["source_instance_id"],
                final_report,
            )
            status, _, _ = http_post_bridge_json(
                "/printer-bridge/snapshot", binding["bridge_token"], snapshot
            )
            if status == 401:
                remove_bambu_bridge(physical_printer_id)
            elif status != 200:
                fh_log("Bambu post-apply snapshot upload failed: HTTP %s" % status)
        if not applied.get("ok"):
            finish(ok=False, code=applied.get("code") or "verification_failed", **common)
            return
        final_changes, final_unresolved, _ = _bambu_material_preview(
            final_report, assignments, host_profiles
        )
        finish(
            ok=True,
            applied=True,
            changes=changes,
            unresolved=final_unresolved,
            desiredAssignments=current_expected,
            remainingChanges=final_changes,
            printState=_BAMBU_STATES.get(
                str(final_report.get("gcode_state") or "").strip().upper(),
                "unknown",
            ),
        )
        wake_bambu_bridge_runtime()

    def _do_bambu_material_immediate(
        self,
        request_id,
        operation,
        physical_printer_id,
        material_system_id,
        token,
        host_profiles,
        commit,
        deadline,
    ):
        def finish(**result):
            result.setdefault("operation", operation)
            result.setdefault("physicalPrinterId", physical_printer_id)
            result.setdefault("materialSystemId", material_system_id)
            self._finish_immediate_material_request(
                "bambu", request_id, result
            )

        if not token:
            finish(ok=False, code="auth", applied=False, observationUploaded=False)
            return
        local, binding = _bambu_local_binding(
            physical_printer_id, material_system_id
        )
        if binding is None:
            finish(ok=False, code="connection_not_found", applied=False,
                   observationUploaded=False)
            return

        if operation == "refresh":
            try:
                serial, report = read_bambu_lan_snapshot(binding)
                current, source_instance_id = _prepare_bambu_observation(
                    binding, serial
                )
                snapshot = build_bambu_bridge_snapshot(
                    current, source_instance_id, report
                )
            except (OSError, PermissionError, TimeoutError, TypeError, ValueError):
                finish(ok=False, code="unreachable", applied=False,
                       observationUploaded=False)
                return
            status, _, _ = http_post_bridge_json(
                "/printer-bridge/snapshot", current["bridge_token"], snapshot
            )
            if status == 401:
                remove_bambu_bridge(physical_printer_id)
            finish(
                ok=status == 200,
                code=None if status == 200 else "snapshot_failed",
                applied=False,
                observationUploaded=status == 200,
            )
            return

        if time.monotonic() > deadline:
            finish(ok=False, code="expired", applied=False,
                   observationUploaded=False)
            return
        _device, _system, _slot, context_error = _material_commit_context(
            token,
            local["source_instance_id"],
            "bambu",
            physical_printer_id,
            material_system_id,
            commit,
        )
        if context_error:
            finish(ok=False, code=context_error, applied=False,
                   observationUploaded=False)
            return
        if commit.get("desired") is None:
            finish(ok=False, code="physical_clear_unsupported", applied=False,
                   observationUploaded=False)
            return
        if (
            commit["desired"].get("presetId") is None
            or commit["desired"].get("spoolId") is None
        ):
            finish(ok=False, code="assignment_incomplete", applied=False,
                   observationUploaded=False)
            return
        target, target_error = _bambu_committed_spool_target(
            binding, commit, host_profiles
        )
        if target_error:
            finish(ok=False, code=target_error, applied=False,
                   observationUploaded=False)
            return
        if time.monotonic() > deadline:
            finish(ok=False, code="expired", applied=False,
                   observationUploaded=False)
            return
        # Re-read the server commit immediately before the first device read.
        _device, _system, _slot, context_error = _material_commit_context(
            token,
            local["source_instance_id"],
            "bambu",
            physical_printer_id,
            material_system_id,
            commit,
        )
        if context_error:
            finish(ok=False, code=context_error, applied=False,
                   observationUploaded=False)
            return
        if time.monotonic() >= deadline:
            finish(ok=False, code="expired", applied=False,
                   observationUploaded=False)
            return
        try:
            applied = apply_bambu_material_targets(
                binding,
                {commit["providerIndex"]: target},
                absolute_deadline=deadline,
            )
        except (OSError, PermissionError, TimeoutError, TypeError, ValueError):
            finish(ok=False, code="unreachable", applied=False,
                   observationUploaded=False)
            return
        report = applied.get("report") if isinstance(applied, dict) else None
        upload_status = 0
        if isinstance(report, dict):
            try:
                snapshot = build_bambu_bridge_snapshot(
                    binding, local["source_instance_id"], report
                )
                upload_status, _, _ = http_post_bridge_json(
                    "/printer-bridge/snapshot", binding["bridge_token"], snapshot
                )
            except (KeyError, TypeError, ValueError):
                upload_status = 0
            if upload_status == 401:
                remove_bambu_bridge(physical_printer_id)
        write_ok = bool(isinstance(applied, dict) and applied.get("ok"))
        if not write_ok:
            finish(
                ok=False,
                code=(applied.get("code") if isinstance(applied, dict) else None)
                or "verification_failed",
                applied=False,
                observationUploaded=upload_status == 200,
            )
            return
        if upload_status != 200:
            finish(ok=False, code="snapshot_failed", applied=True,
                   observationUploaded=False)
            return
        finish(ok=True, code=None, applied=True, observationUploaded=True)
        wake_bambu_bridge_runtime()

    # on_message runs on the UI thread — offload network + disk work to a worker.
    def _do_parse_slice(self, key, token, file_name=""):
        entry = slice_entry_for_key(key)
        path = entry["path"] if entry else ""
        if not path:
            self._deliver_slice_result({"error": "gone"})
            return
        if not token:
            self._deliver_slice_result({"error": "auth"})
            return
        # The list is what a person is looking at, so the name they see there
        # wins; the remembered one covers slices seen before names were kept.
        status, body = http_post_file(
            "/orcaslicer/slices/parse", token, path, file_name=file_name or entry["name"]
        )
        if status != 200:
            fh_log("slice parse HTTP %s for %s" % (status, os.path.basename(path)))
            self._deliver_slice_result({"error": "http", "status": status})
            return
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._deliver_slice_result({"error": "body"})
            return
        self._deliver_slice_result({"parsed": parsed})

    def _do_happy_hare_action(
        self,
        request_id,
        operation,
        physical_printer_id,
        material_system_id,
        token,
        local_connections,
        expected_desired=None,
    ):
        def finish(**result):
            result.setdefault("operation", operation)
            result.setdefault("physicalPrinterId", physical_printer_id)
            result.setdefault("materialSystemId", material_system_id)
            self._deliver_happy_hare_result(request_id, result)

        if not token:
            finish(ok=False, code="auth")
            return
        try:
            extra = verified_local_setup_connections(token)
        except (ValueError, OSError):
            finish(ok=False, code="server")
            return
        local_connections = list(local_connections) + extra
        connection, snapshot, device, error = resolve_happy_hare_connection(
            token,
            local_connections,
            physical_printer_id,
        )
        if error or connection is None or snapshot is None or device is None:
            finish(ok=False, code=error or "connection_not_found")
            return
        snapshot_status, _snapshot_result = upload_happy_hare_snapshot(
            token, physical_printer_id, snapshot
        )
        if snapshot_status != 200:
            finish(
                ok=False,
                code=(
                    "auth" if snapshot_status == 401
                    else "access" if snapshot_status == 403
                    else "server"
                ),
                status=snapshot_status,
            )
            return
        if "inventory_key_digest" in device and (
            not snapshot.get("inventory_key_digest")
            or snapshot["inventory_key_digest"] != device["inventory_key_digest"]
        ):
            finish(ok=False, code="inventory_not_connected")
            return
        desired = _desired_happy_hare_spools(device, material_system_id)
        if desired is None:
            finish(ok=False, code="material_system_not_found")
            return
        preview_status, reconciliation = request_happy_hare_reconciliation(
            token,
            "preview",
            physical_printer_id,
            material_system_id,
            connection,
            snapshot,
        )
        if preview_status != 200:
            finish(
                ok=False,
                code=(
                    "auth" if preview_status == 401
                    else "access" if preview_status == 403
                    else "server"
                ),
                status=preview_status,
            )
            return
        changes = reconciliation.get("changes") or []
        import_changes = reconciliation.get("importChanges") or []
        common = {
            "gateCount": snapshot["gate_count"],
            "printerHostname": snapshot.get("printer_hostname") or None,
            "spoolmanSupport": snapshot.get("spoolman_support") or None,
            "printState": snapshot.get("print_state") or None,
            "changes": changes,
            "importChanges": import_changes,
            "unresolved": reconciliation.get("unresolved") or [],
            "desiredAssignments": reconciliation.get("desiredAssignments") or [],
        }
        desired = {
            item["gate"]: item.get("spool_id")
            for item in common["desiredAssignments"]
        }
        if operation == "preview":
            finish(ok=True, **common)
            return
        current_expected = reconciliation.get("desiredAssignments") or []
        if expected_desired != current_expected:
            finish(ok=False, code="stale_preview", **common)
            return
        if operation == "adopt":
            needs_refresh = any(
                item.get("source") == "last_known" for item in import_changes
            )
            if needs_refresh and snapshot.get("spoolman_support") != "pull":
                finish(ok=False, code="pull_required", **common)
                return
            if needs_refresh and snapshot.get("print_state") in {"printing", "paused"}:
                finish(ok=False, code="printer_busy", **common)
                return
            adopt_status, adopted = request_happy_hare_reconciliation(
                token,
                "adopt",
                physical_printer_id,
                material_system_id,
                connection,
                snapshot,
                expected_desired=current_expected,
            )
            if adopt_status != 200:
                finish(
                    ok=False,
                    code=(
                        "auth" if adopt_status == 401
                        else "access" if adopt_status == 403
                        else "stale_preview" if adopt_status == 409
                        else "server"
                    ),
                    status=adopt_status,
                    **common,
                )
                return
            if not needs_refresh:
                finish(
                    ok=True,
                    adopted=True,
                    adoptedGates=adopted.get("adoptedGates") or 0,
                    **common,
                )
                return
            for item in import_changes:
                desired[item["gate"]] = item.get("proposedSpoolId")
            common["adopted"] = True
            common["adoptedGates"] = adopted.get("adoptedGates") or 0
        elif snapshot.get("spoolman_support") != "pull":
            finish(ok=False, code="pull_required", **common)
            return
        elif not snapshot.get("spool_ids_known"):
            finish(ok=False, code="spool_ids_unavailable", **common)
            return
        if snapshot.get("print_state") in {"printing", "paused"}:
            finish(ok=False, code="printer_busy", **common)
            return
        if operation == "apply" and not changes:
            finish(ok=True, applied=False, remainingChanges=[], **common)
            return

        # The browser can select only this allowlisted operation. In pull mode
        # Happy Hare rebuilds the map from the FilamentHub-backed Spoolman API;
        # no web-supplied G-code or LAN credential crosses this boundary.
        command_status, _command_result, _command_error = _moonraker_json(
            connection,
            "/printer/gcode/script",
            {"script": "MMU_SPOOLMAN REFRESH=1"},
        )
        if command_status != 200:
            finish(ok=False, code="command_failed", status=command_status, **common)
            return
        refreshed = None
        remaining = changes
        for delay in (0.5, 1.0, 2.0, 3.0):
            time.sleep(delay)
            try:
                candidate = read_happy_hare_snapshot(connection)
            except (RuntimeError, ValueError):
                continue
            refreshed = candidate
            remaining = (
                _happy_hare_assignment_changes(
                    candidate["actual_spool_ids"], desired
                )
                if candidate.get("spool_ids_known")
                else changes
            )
            if not remaining:
                break
        if refreshed is None:
            finish(ok=False, code="verification_failed", **common)
            return
        upload_happy_hare_snapshot(token, physical_printer_id, refreshed)
        final_common = dict(common)
        for key in (
            "gateCount",
            "printerHostname",
            "spoolmanSupport",
            "printState",
            "changes",
        ):
            final_common.pop(key, None)
        finish(
            ok=not remaining,
            code=None if not remaining else "not_applied",
            applied=True,
            remainingChanges=remaining,
            gateCount=refreshed["gate_count"],
            printerHostname=refreshed.get("printer_hostname") or None,
            spoolmanSupport=refreshed.get("spoolman_support") or None,
            printState=refreshed.get("print_state") or None,
            changes=changes,
            **final_common,
        )

    def _do_happy_hare_material_immediate(
        self,
        request_id,
        operation,
        physical_printer_id,
        material_system_id,
        token,
        local_connections,
        commit,
        deadline,
    ):
        def finish(**result):
            result.setdefault("operation", operation)
            result.setdefault("physicalPrinterId", physical_printer_id)
            result.setdefault("materialSystemId", material_system_id)
            self._finish_immediate_material_request(
                "happy-hare", request_id, result
            )

        if not token:
            finish(ok=False, code="auth", applied=False, observationUploaded=False)
            return
        try:
            extra = verified_local_setup_connections(token)
        except (ValueError, OSError):
            finish(ok=False, code="server", applied=False, observationUploaded=False)
            return
        local_connections = list(local_connections) + extra
        source_instance_id = plugin_source_instance_id()
        inventory, inventory_error = _plugin_material_server_inventory(
            token, source_instance_id=source_instance_id
        )
        if inventory_error or inventory is None:
            finish(ok=False, code=inventory_error or "server", applied=False,
                   observationUploaded=False)
            return
        device = next(
            (item for item in inventory["printers"]
             if item.get("id") == physical_printer_id),
            None,
        )
        if device is None:
            finish(ok=False, code="connection_not_found", applied=False,
                   observationUploaded=False)
            return
        requested_system = next(
            (
                item for item in device.get("material_systems") or []
                if isinstance(item, dict)
                and item.get("id") == material_system_id
                and item.get("provider") == "happy_hare"
            ),
            None,
        )
        if requested_system is None:
            finish(ok=False, code="material_system_not_found", applied=False,
                   observationUploaded=False)
            return
        if operation == "assign":
            if time.monotonic() > deadline:
                finish(ok=False, code="expired", applied=False,
                       observationUploaded=False)
                return
            device, _system, _slot, context_error = _material_commit_context(
                token,
                source_instance_id,
                "happy_hare",
                physical_printer_id,
                material_system_id,
                commit,
            )
            if context_error:
                finish(ok=False, code=context_error, applied=False,
                       observationUploaded=False)
                return
            if commit.get("desired") is None:
                finish(ok=False, code="physical_clear_unsupported", applied=False,
                       observationUploaded=False)
                return
            if (
                commit["desired"].get("presetId") is None
                or commit["desired"].get("spoolId") is None
            ):
                finish(ok=False, code="assignment_incomplete", applied=False,
                       observationUploaded=False)
                return
            inventory = {
                "source_instance_id": source_instance_id,
                "printers": [device],
            }

        connection, snapshot, device, error = resolve_happy_hare_connection(
            token,
            local_connections,
            physical_printer_id,
            inventory=inventory,
        )
        if error or connection is None or snapshot is None or device is None:
            finish(ok=False, code=error or "connection_not_found", applied=False,
                   observationUploaded=False)
            return
        if "inventory_key_digest" in device and (
            not snapshot.get("inventory_key_digest")
            or snapshot["inventory_key_digest"] != device["inventory_key_digest"]
        ):
            finish(ok=False, code="inventory_not_connected", applied=False,
                   observationUploaded=False)
            return

        if operation == "refresh":
            status, _result = upload_happy_hare_snapshot(
                token, physical_printer_id, snapshot
            )
            finish(
                ok=status == 200,
                code=None if status == 200 else (
                    "auth" if status == 401
                    else "access" if status == 403
                    else "snapshot_failed"
                ),
                applied=False,
                observationUploaded=status == 200,
            )
            return

        if snapshot.get("spoolman_support") != "pull":
            finish(ok=False, code="pull_required", applied=False,
                   observationUploaded=False)
            return
        if not snapshot.get("spool_ids_known"):
            finish(ok=False, code="spool_ids_unavailable", applied=False,
                   observationUploaded=False)
            return
        if snapshot.get("print_state") in {"printing", "paused"}:
            finish(ok=False, code="printer_busy", applied=False,
                   observationUploaded=False)
            return
        desired = _desired_happy_hare_spools(device, material_system_id)
        if desired is None:
            finish(ok=False, code="material_system_not_found", applied=False,
                   observationUploaded=False)
            return
        provider_index = commit.get("providerIndex")
        if (
            provider_index not in desired
            or provider_index >= snapshot.get("gate_count", 0)
        ):
            finish(ok=False, code="slot_not_found", applied=False,
                   observationUploaded=False)
            return
        changes = _happy_hare_assignment_changes(
            snapshot["actual_spool_ids"], desired
        )
        if not changes:
            _current, _system, _slot, context_error = _material_commit_context(
                token,
                source_instance_id,
                "happy_hare",
                physical_printer_id,
                material_system_id,
                commit,
            )
            if context_error:
                finish(ok=False, code=context_error, applied=False,
                       observationUploaded=False)
                return
            status, _result = upload_happy_hare_snapshot(
                token, physical_printer_id, snapshot
            )
            finish(
                ok=status == 200,
                code=None if status == 200 else "snapshot_failed",
                applied=status == 200,
                observationUploaded=status == 200,
            )
            return
        if time.monotonic() > deadline:
            finish(ok=False, code="expired", applied=False,
                   observationUploaded=False)
            return
        # The command pulls the newest server map. The repeated exact commit
        # check prevents an old browser request from initiating that pull.
        current_device, _system, _slot, context_error = _material_commit_context(
            token,
            source_instance_id,
            "happy_hare",
            physical_printer_id,
            material_system_id,
            commit,
        )
        if context_error:
            finish(ok=False, code=context_error, applied=False,
                   observationUploaded=False)
            return
        desired = _desired_happy_hare_spools(
            current_device, material_system_id
        )
        if desired is None:
            finish(ok=False, code="material_system_not_found", applied=False,
                   observationUploaded=False)
            return
        if time.monotonic() >= deadline:
            finish(ok=False, code="expired", applied=False,
                   observationUploaded=False)
            return
        command_status, _command_result, _command_error = _moonraker_json(
            connection,
            "/printer/gcode/script",
            {"script": "MMU_SPOOLMAN REFRESH=1"},
        )
        if command_status != 200:
            finish(ok=False, code="command_failed", applied=False,
                   observationUploaded=False)
            return
        refreshed = None
        remaining = changes
        for delay in (0.5, 1.0, 2.0, 3.0):
            time.sleep(delay)
            try:
                candidate = read_happy_hare_snapshot(connection)
            except (RuntimeError, ValueError):
                continue
            refreshed = candidate
            remaining = (
                _happy_hare_assignment_changes(
                    candidate["actual_spool_ids"], desired
                )
                if candidate.get("spool_ids_known")
                else changes
            )
            if not remaining:
                break
        if refreshed is None:
            finish(ok=False, code="verification_failed", applied=False,
                   observationUploaded=False)
            return
        status, _result = upload_happy_hare_snapshot(
            token, physical_printer_id, refreshed
        )
        physically_applied = not remaining
        if status != 200:
            finish(ok=False, code="snapshot_failed", applied=physically_applied,
                   observationUploaded=False)
            return
        finish(
            ok=physically_applied,
            code=None if physically_applied else "not_applied",
            applied=physically_applied,
            observationUploaded=True,
        )

    def _do_printer_setup(self, msg, token, local_connections, observations=()):
        request_id = msg["requestId"]

        def finish(**result):
            self._deliver("printer-setup-result", requestId=request_id, result=result)

        try:
            context = printer_setup_context(token)
            local = list({item["connection_ref"]: item for item in
                          list(local_connections) + local_setup_connections(context)}.values())
            operation = msg.get("operation")
            discovery = None
            if operation == "list":
                discovery = (self._setup_discovery(context, observations, refresh=True)
                             if msg.get("discovery") is True else {"items": [], "complete": True})
            else:
                cached = getattr(self, "_printer_discovery", {})
                if cached.get("account_scope") == context["account_scope"] and cached.get("expires", 0) > time.monotonic():
                    discovery = cached
            if discovery:
                endpoints = {_connection_endpoint_token(context["discovery_key"], item.get("print_host"), "moonraker")
                             for item in local}
                for item in discovery["items"]:
                    if item["provider"] == "moonraker" and _connection_endpoint_token(
                        context["discovery_key"], item.get("print_host"), "moonraker",
                    ) not in endpoints:
                        local.append(item)
            if operation == "list":
                names = msg.get("labels") or {}
                bound = {item["connection_ref"]: item for item in context["bindings"]
                         if item.get("status") == "bound"}
                detached = {item["connection_ref"] for item in context["bindings"]
                            if item.get("status") == "detached"}
                candidates = [{
                    "connectionRef": item["connection_ref"],
                    "label": str(item.get("label") or names.get(item["connection_ref"]) or "Moonraker")[:200],
                    "physicalPrinterId": (bound.get(item["connection_ref"]) or {}).get("physical_printer_id"),
                    "provider": "moonraker", "source": item.get("source") or ("saved" if item.get("account_scope") else "profile"),
                } for item in local if item["connection_ref"] not in detached]
                candidates.extend({"connectionRef": item["connection_ref"], "label": item["label"],
                    "physicalPrinterId": item.get("physical_printer_id"), "provider": item["provider"],
                    "source": item["source"], "printerModel": item.get("printer_model", ""),
                } for item in discovery["items"] if item["provider"] != "moonraker" and item["connection_ref"] not in detached)
                finish(ok=True, candidates=candidates[:256], discoveryComplete=discovery["complete"])
                return
            pending = {
                key: value for key, value in getattr(self, "_printer_setup_pending", {}).items()
                if value["expires"] > time.monotonic()
            }
            self._printer_setup_pending = pending
            if operation == "probe":
                if msg.get("type") == "printer-setup-local":
                    host = _moonraker_base_url(msg.get("host"))
                    api_key = msg.get("apiKey", "")
                    if not isinstance(api_key, str) or len(api_key) > 1024 or "\n" in api_key or "\r" in api_key:
                        raise ValueError("invalid")
                    # A repeat of the same locally-entered endpoint reuses its saved ref.
                    found = [item for item in local_setup_connections(context)
                             if _moonraker_base_url(item["print_host"]) == host]
                    requested_ref = msg.get("connectionRef")
                    if requested_ref:
                        found = [item for item in local if item["connection_ref"] == requested_ref
                                 and _moonraker_base_url(item["print_host"]) == host]
                        if len(found) != 1:
                            raise ValueError("connection_not_found")
                    connection = {
                        "connection_ref": found[0]["connection_ref"] if found else "local-" + uuid.uuid4().hex,
                        "print_host": host, "api_key": api_key, "label": "Moonraker",
                    }
                    origin = "local_manual"
                else:
                    matches = [item for item in local if item["connection_ref"] == msg.get("connectionRef")]
                    if len(matches) != 1:
                        raise ValueError("connection_not_found")
                    connection = matches[0]
                    origin = "local_manual" if connection.get("account_scope") else "orca_profile"
                try:
                    evidence, snapshot = probe_printer_setup(context, connection, origin)
                except ValueError as exc:
                    if str(exc) == "printer_auth" and msg.get("type") != "printer-setup-local":
                        if discovery:
                            discovery["expires"] = time.monotonic() + 600
                        self._deliver_native_setup("printer-setup-auth-required", requestId=request_id,
                            connectionRef=connection["connection_ref"], host=connection["print_host"], copy=msg.get("copy") or {})
                        return
                    raise
                if len(pending) >= 16:
                    pending.pop(next(iter(pending)))
                probe_id = uuid.uuid4().hex
                pending[probe_id] = {
                    "account_scope": context["account_scope"], "connection": connection,
                    "evidence": evidence, "expires": time.monotonic() + 600,
                }
                finish(ok=True, probeId=probe_id, connection=evidence,
                       provider="happy_hare" if snapshot else "manual",
                       gateCount=snapshot["gate_count"] if snapshot else None,
                       printerHostname=snapshot.get("printer_hostname") if snapshot else None,
                       spoolmanSupport=snapshot.get("spoolman_support") if snapshot else None,
                       inventoryLinked=setup_inventory_linked(context, connection["connection_ref"], snapshot))
                return
            if operation != "activate":
                raise ValueError("invalid")
            saved = pending.get(msg.get("probeId"))
            if not saved or saved["account_scope"] != context["account_scope"]:
                raise ValueError("expired")
            printer_id = msg.get("physicalPrinterId")
            if isinstance(printer_id, bool) or not isinstance(printer_id, int) or printer_id < 1:
                raise ValueError("invalid")
            evidence = saved["evidence"]
            if not any(item.get("connection_ref") == evidence["connection_ref"]
                       and item.get("physical_printer_id") == printer_id and item.get("status") == "bound"
                       for item in context["bindings"]):
                raise ValueError("connection_not_found")
            connection = saved["connection"]
            if evidence["origin"] == "orca_profile":
                matches = [item for item in local_connections if item["connection_ref"] == evidence["connection_ref"]]
                if len(matches) != 1:
                    raise ValueError("connection_not_found")
                connection = matches[0]
            current, snapshot = probe_printer_setup(context, connection, evidence["origin"])
            if current != evidence:
                raise ValueError("identity_changed")
            if evidence["origin"] == "local_manual":
                save_local_setup_connection(context, connection, printer_id, evidence)
            if snapshot is not None:
                status, _result = upload_happy_hare_snapshot(token, printer_id, snapshot)
                if status != 200:
                    raise ValueError("snapshot_failed")
            # Keep a bounded retry token until expiry: response loss is not a new setup.
            finish(ok=True, physicalPrinterId=printer_id, observed=snapshot is not None,
                   inventoryLinked=setup_inventory_linked(context, evidence["connection_ref"], snapshot))
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
            # Exceptions can carry addresses, headers or response bodies. Never relay them.
            code = str(exc)
            finish(ok=False, code=code if code in {
                "auth", "setup_context", "printer_auth", "unreachable", "expired",
                "connection_not_found", "identity_changed", "identity_unavailable", "snapshot_failed",
            } else "setup_failed")

    def on_message(self, msg):
        original_type = type(msg).__name__
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except (TypeError, ValueError):
                fh_log("Plugin host message rejected: invalid JSON (%s)" % original_type)
                return
        if not isinstance(msg, dict):
            fh_log("Plugin host message rejected: non-object (%s)" % original_type)
            return
        fh_log(
            "Plugin host message received: type=%s source=%s has_bridge=%s has_local=%s"
            % (
                str(msg.get("type") or "")[:80],
                str(msg.get("source") or "")[:80],
                bool(msg.get("bridgeSession")),
                bool(msg.get("localDialogSession")),
            )
        )
        if msg.get("source") != "filamenthub-plugin":
            fh_log("Plugin host message ignored: source mismatch")
            return
        msg_type = msg.get("type")
        direct_session = str(getattr(self, "_direct_bridge_session", ""))
        direct_message = bool(direct_session) and secrets.compare_digest(
            str(msg.get("bridgeSession") or ""),
            direct_session,
        )
        local_message = secrets.compare_digest(
            str(msg.get("localDialogSession") or ""),
            str(getattr(self, "_local_dialog_session", "")),
        ) and bool(getattr(self, "_local_dialog_session", ""))
        if not direct_message and not local_message:
            fh_log("Plugin host message ignored: bridge binding mismatch")
            return
        local_only = {
            "printer-setup-local",
            "prepare-bambu-local",
            "configure-bambu-local",
            "local-dialog-close",
        }
        if local_message and msg_type not in local_only | {"remove-bambu-local"}:
            return
        if direct_message and msg_type in local_only:
            # A remote page may request a local dialog, but can never submit the
            # credentials collected by that separately bound host window.
            return
        if direct_message and msg_type in {"configure-bambu", "printer-setup-manual"}:
            self._open_local_dialog(msg)
            return
        if local_message and msg_type in {"prepare-bambu-local", "configure-bambu-local"}:
            fh_log("Bambu setup message received: %s" % msg_type)
        if local_message and msg_type == "local-dialog-close":
            self._close_local_dialog(str(msg.get("outcome") or "cancelled"))
            return
        if msg_type == "host-ready":
            # The session sync waits for the capability the signed-in page mints
            # right after this: a saved one is usually already expired.
            self._deliver("transport", push=True)
        elif msg_type == "request-slice-reports":
            _deliver_pending_slice_reports(self)
        elif msg_type == "slice-report-result":
            request_id = msg.get("requestId")
            source_keys = msg.get("sourceKeys")
            if not (
                isinstance(request_id, str)
                and request_id.startswith("slice-report-")
                and len(request_id) <= 100
                and isinstance(source_keys, list)
                and len(source_keys) <= 25
            ):
                return
            if msg.get("ok") is True:
                removed = _acknowledge_slice_reports(source_keys)
                fh_log("slice reports delivered through page: %d" % removed)
                if removed:
                    _deliver_pending_slice_reports(self)
            else:
                fh_log("slice report page delivery failed; queued reports kept")
        elif msg_type == "plugin-capabilities-request":
            self._deliver(
                "plugin-capabilities",
                pluginVersion=PLUGIN_VERSION,
                capabilities=list(PLUGIN_CAPABILITIES),
                developerMode=plugin_setting("developer_mode"),
            )
        elif msg_type in {"printer-setup", "printer-setup-local"}:
            request_id = msg.get("requestId")
            if not isinstance(request_id, str) or not 0 < len(request_id) <= 100:
                return
            observations = observe_printer_presets()
            local = observe_local_moonraker_connections(observations)
            msg = dict(msg)
            msg["labels"] = {item.get("connection_ref"): item.get("preset_name") for item in observations}
            token = (load_saved_auth() or {}).get("accessToken") or ""
            BACKGROUND_WORKER.submit(self._do_printer_setup, msg, token, local, observations)
        elif msg_type == "read-diagnostics" and plugin_setting("developer_mode"):
            BACKGROUND_WORKER.submit(
                lambda: self._deliver("diagnostics", text=diagnostic_report_text())
            )
        elif msg_type == "printer-recovery-state":
            request_id = msg.get("requestId")
            owner_user_id = msg.get("ownerUserId")
            if not (
                isinstance(request_id, str)
                and 0 < len(request_id) <= 100
                and not isinstance(owner_user_id, bool)
                and isinstance(owner_user_id, int)
                and owner_user_id > 0
            ):
                return
            refresh_user_preset_folder()
            original_observations = observe_recovery_originals()
            BACKGROUND_WORKER.submit(
                self._do_printer_recovery_state,
                request_id,
                owner_user_id,
                original_observations,
            )
        elif msg_type == "apply-printer-recovery":
            request_id = msg.get("requestId")
            bundle = msg.get("bundle")
            if not (
                isinstance(request_id, str)
                and 0 < len(request_id) <= 100
                and isinstance(bundle, dict)
            ):
                return
            refresh_user_preset_folder()
            BACKGROUND_WORKER.submit(
                self._do_apply_printer_recovery,
                request_id,
                bundle,
            )
        elif msg_type == "remove-printer-recovery":
            request_id = msg.get("requestId")
            artifact_keys = msg.get("artifactKeys")
            if not (
                isinstance(request_id, str)
                and 0 < len(request_id) <= 100
                and isinstance(artifact_keys, list)
                and 0 < len(artifact_keys) <= MAX_TRACKED_RECOVERY_ARTIFACTS
                and all(
                    isinstance(value, str) and 0 < len(value) <= 64
                    for value in artifact_keys
                )
            ):
                return
            refresh_user_preset_folder()
            BACKGROUND_WORKER.submit(
                self._do_remove_printer_recovery,
                request_id,
                list(dict.fromkeys(artifact_keys)),
            )
        elif msg_type == "install-printer-bundle":
            request_id = msg.get("requestId")
            physical_printer_id = msg.get("physicalPrinterId")
            if not (
                isinstance(request_id, str)
                and 0 < len(request_id) <= 100
                and not isinstance(physical_printer_id, bool)
                and isinstance(physical_printer_id, int)
                and physical_printer_id > 0
            ):
                return
            token = msg.get("token") or ""
            if not isinstance(token, str) or len(token) > MAX_TOKEN_LENGTH:
                return
            if not token:
                token = (load_saved_auth() or {}).get("accessToken") or ""
            refresh_user_preset_folder()
            BACKGROUND_WORKER.submit(
                self._do_install_printer_bundle,
                request_id,
                physical_printer_id,
                token,
            )
        elif msg_type == "remove-printer-bundle":
            request_id = msg.get("requestId")
            physical_printer_id = msg.get("physicalPrinterId")
            if not (
                isinstance(request_id, str)
                and 0 < len(request_id) <= 100
                and not isinstance(physical_printer_id, bool)
                and isinstance(physical_printer_id, int)
                and physical_printer_id > 0
            ):
                return
            refresh_user_preset_folder()
            BACKGROUND_WORKER.submit(
                self._do_remove_printer_bundle,
                request_id,
                physical_printer_id,
            )
        elif msg_type == "printer-bundle-status":
            request_id = msg.get("requestId")
            physical_printer_ids = msg.get("physicalPrinterIds")
            if not (
                isinstance(request_id, str)
                and 0 < len(request_id) <= 100
                and isinstance(physical_printer_ids, list)
                and len(physical_printer_ids) <= MAX_TRACKED_PRINTER_BUNDLES
                and all(
                    not isinstance(value, bool)
                    and isinstance(value, int)
                    and value > 0
                    for value in physical_printer_ids
                )
            ):
                return
            token = msg.get("token") or ""
            if not isinstance(token, str) or len(token) > MAX_TOKEN_LENGTH:
                return
            if not token:
                token = (load_saved_auth() or {}).get("accessToken") or ""
            refresh_user_preset_folder()
            BACKGROUND_WORKER.submit(
                self._do_printer_bundle_status,
                request_id,
                list(dict.fromkeys(physical_printer_ids)),
                token,
            )
        elif msg_type == "prepare-bambu-local":
            physical_printer_id = msg.get("physicalPrinterId")
            material_system_id = msg.get("materialSystemId")
            pairing_code = msg.get("pairingCode")
            if not isinstance(pairing_code, str):
                pairing_code = ""
            if not (
                type(physical_printer_id) is int
                and physical_printer_id > 0
                and type(material_system_id) is int
                and material_system_id > 0
            ):
                return
            observations = observe_printer_presets()
            token = (load_saved_auth() or {}).get("accessToken") or ""
            submitted = BACKGROUND_WORKER.submit(
                self._do_prepare_bambu,
                {
                    "physicalPrinterId": physical_printer_id,
                    "materialSystemId": material_system_id,
                    "pairingCode": pairing_code,
                    "connectionRef": str(msg.get("connectionRef") or "")[:120],
                    "requestId": str(msg.get("requestId") or "")[:120],
                    "refresh": msg.get("refresh") is True,
                },
                observations,
                token,
            )
            if submitted is False:
                fh_log("Bambu setup search worker unavailable")
                self._deliver_native_setup(
                    "bambu-setup-candidates",
                    requestId=str(msg.get("requestId") or "")[:120],
                    physicalPrinterId=physical_printer_id,
                    materialSystemId=material_system_id,
                    pairingCode=pairing_code,
                    candidates=[],
                    discoveryComplete=False,
                    discoveryAttempted=msg.get("refresh") is True,
                    hasSavedConnection=False,
                )
        elif msg_type == "configure-bambu-local":
            physical_printer_id = msg.get("physicalPrinterId")
            material_system_id = msg.get("materialSystemId")
            host = msg.get("host")
            access_code = msg.get("accessCode")
            serial = msg.get("serial") or ""
            pairing_code = msg.get("pairingCode")
            if not isinstance(pairing_code, str):
                pairing_code = ""
            if not (
                isinstance(physical_printer_id, int)
                and isinstance(material_system_id, int)
                and isinstance(host, str)
                and isinstance(access_code, str)
                and isinstance(serial, str)
            ):
                return
            request_id = str(msg.get("requestId") or "")[:120]
            if not 8 <= len(pairing_code) <= 32:
                self._deliver_native_setup(
                    "bambu-setup-result",
                    requestId=request_id,
                    ok=False,
                    code="bambuPairingFailed",
                )
                return
            submitted = BACKGROUND_WORKER.submit(
                self._do_configure_bambu,
                physical_printer_id,
                material_system_id,
                host,
                access_code,
                serial,
                pairing_code,
                request_id,
            )
            if submitted is False:
                fh_log("Bambu setup worker unavailable")
                self._deliver_native_setup(
                    "bambu-setup-result",
                    requestId=request_id,
                    ok=False,
                    code="bambuSetupUnavailable",
                )
        elif msg_type == "remove-bambu-local":
            physical_printer_id = msg.get("physicalPrinterId")
            if not isinstance(physical_printer_id, int) or physical_printer_id <= 0:
                return
            BACKGROUND_WORKER.submit(self._do_remove_bambu, physical_printer_id)
        elif msg_type in {
            "bambu-material-assign",
            "bambu-material-refresh",
            "happy-hare-material-assign",
            "happy-hare-material-refresh",
        }:
            request_id = msg.get("requestId")
            physical_printer_id = msg.get("physicalPrinterId")
            material_system_id = msg.get("materialSystemId")
            operation = "assign" if msg_type.endswith("-assign") else "refresh"
            provider = "bambu" if msg_type.startswith("bambu-") else "happy-hare"
            # bridgeSession is the tab binding every direct page command carries;
            # it was already verified above.
            allowed_keys = {
                "source", "type", "requestId", "physicalPrinterId",
                "materialSystemId", "bridgeSession",
            }
            if operation == "assign":
                allowed_keys.add("commit")
            if not (
                set(msg).issubset(allowed_keys)
                and isinstance(request_id, str)
                and 0 < len(request_id) <= 100
                and type(physical_printer_id) is int
                and physical_printer_id > 0
                and type(material_system_id) is int
                and material_system_id > 0
                and (
                    operation == "refresh"
                    or _valid_immediate_material_commit(msg.get("commit"))
                )
            ):
                return
            commit_fingerprint = (
                json.dumps(msg.get("commit"), sort_keys=True, separators=(",", ":"))
                if operation == "assign" else ""
            )
            fingerprint = (
                operation,
                physical_printer_id,
                material_system_id,
                commit_fingerprint,
            )
            if not self._begin_immediate_material_request(
                provider, request_id, fingerprint
            ):
                return
            token = (load_saved_auth() or {}).get("accessToken") or ""
            deadline = time.monotonic() + 20.0
            if provider == "bambu":
                host_profiles = scan_managed_host_filaments() if operation == "assign" else {}
                BACKGROUND_WORKER.submit(
                    self._do_bambu_material_immediate,
                    request_id,
                    operation,
                    physical_printer_id,
                    material_system_id,
                    token,
                    host_profiles,
                    msg.get("commit"),
                    deadline,
                )
            else:
                observations = observe_printer_presets()
                local_connections = observe_local_moonraker_connections(observations)
                BACKGROUND_WORKER.submit(
                    self._do_happy_hare_material_immediate,
                    request_id,
                    operation,
                    physical_printer_id,
                    material_system_id,
                    token,
                    local_connections,
                    msg.get("commit"),
                    deadline,
                )
        elif msg_type in {"bambu-material-preview", "bambu-material-apply"}:
            request_id = msg.get("requestId")
            physical_printer_id = msg.get("physicalPrinterId")
            material_system_id = msg.get("materialSystemId")
            expected_desired = msg.get("expectedDesiredAssignments")
            if not (
                isinstance(request_id, str)
                and 0 < len(request_id) <= 100
                and type(physical_printer_id) is int
                and physical_printer_id > 0
                and type(material_system_id) is int
                and material_system_id > 0
            ):
                return
            if msg_type == "bambu-material-apply":
                if not isinstance(expected_desired, list) or len(expected_desired) > 256:
                    return
                for item in expected_desired:
                    if not (
                        isinstance(item, dict)
                        and type(item.get("slot")) is int
                        and 0 <= item["slot"] <= 1023
                        and (
                            item.get("preset_id") is None
                            or type(item.get("preset_id")) is int
                            and item["preset_id"] > 0
                        )
                        and (
                            item.get("spool_id") is None
                            or type(item.get("spool_id")) is int
                            and item["spool_id"] > 0
                        )
                        and (
                            item.get("source_ts") is None
                            or isinstance(item.get("source_ts"), str)
                            and len(item["source_ts"]) <= 64
                        )
                    ):
                        return
            token = (load_saved_auth() or {}).get("accessToken") or ""
            host_profiles = scan_managed_host_filaments()
            BACKGROUND_WORKER.submit(
                self._do_bambu_material_action,
                request_id,
                "apply" if msg_type == "bambu-material-apply" else "preview",
                physical_printer_id,
                material_system_id,
                token,
                host_profiles,
                expected_desired,
            )
        elif msg_type == "check-slices":
            # The list on the site outlives the files behind it; answer which of
            # those slices can still be turned into a calculation.
            keys = msg.get("keys")
            if not isinstance(keys, list):
                return
            wanted = [k for k in keys if isinstance(k, str) and k][:50]
            hook = self._slice_hook_state()  # host read on the UI thread
            BACKGROUND_WORKER.submit(self._do_check_slices, wanted, hook)
        elif msg_type == "parse-slice":
            # The page cannot open a file on disk, so it asks by key and this
            # side sends the G-code straight to FilamentHub's own parser.
            key = msg.get("sourceKey")
            if not isinstance(key, str) or not key:
                return
            shown = msg.get("fileName")
            shown = os.path.basename(shown)[:300] if isinstance(shown, str) else ""
            token = (load_saved_auth() or {}).get("accessToken") or ""
            BACKGROUND_WORKER.submit(self._do_parse_slice, key, token, shown)
        elif msg_type == "sync":
            scope = msg.get("scope") or "all"
            operation_id = msg.get("operationId") or ""
            if not (
                scope in SYNC_SCOPES
                and isinstance(operation_id, str)
                and len(operation_id) <= 100
            ):
                return
            self._start_sync(
                scope=scope,
                announce=True,
                operation_id=operation_id,
                trigger="manual",
            )
        elif msg_type in {
            "happy-hare-preview",
            "happy-hare-apply",
            "happy-hare-adopt",
        }:
            request_id = msg.get("requestId")
            physical_printer_id = msg.get("physicalPrinterId")
            material_system_id = msg.get("materialSystemId")
            expected_desired = msg.get("expectedDesiredAssignments")
            if not (
                isinstance(request_id, str)
                and 0 < len(request_id) <= 100
                and type(physical_printer_id) is int
                and physical_printer_id > 0
                and type(material_system_id) is int
                and material_system_id > 0
            ):
                return
            if msg_type != "happy-hare-preview":
                if not isinstance(expected_desired, list) or len(expected_desired) > 256:
                    return
                for item in expected_desired:
                    if not (
                        isinstance(item, dict)
                        and type(item.get("gate")) is int
                        and item["gate"] >= 0
                        and (
                            item.get("spool_id") is None
                            or type(item.get("spool_id")) is int
                            and item["spool_id"] > 0
                        )
                    ):
                        return
            token = (load_saved_auth() or {}).get("accessToken") or ""
            observations = observe_printer_presets()
            local_connections = observe_local_moonraker_connections(observations)
            BACKGROUND_WORKER.submit(
                self._do_happy_hare_action,
                request_id,
                (
                    "apply" if msg_type == "happy-hare-apply"
                    else "adopt" if msg_type == "happy-hare-adopt"
                    else "preview"
                ),
                physical_printer_id,
                material_system_id,
                token,
                local_connections,
                expected_desired,
            )
        elif msg_type == "auth-token":
            # Login starts one visible session reconciliation. Token refreshes
            # update the credential but do not enqueue the same work again.
            access = msg.get("accessToken") or ""
            if isinstance(access, str) and 0 < len(access) <= MAX_TOKEN_LENGTH:
                save_auth(access)
                wake_bambu_bridge_runtime()
                if plugin_setting("auto_sync") and not getattr(
                    self, "_session_sync_started", False
                ):
                    self._session_sync_started = self._auto_sync(
                        announce=True,
                        scope="all",
                        trigger="session-auth",
                    )
        elif msg_type == "profile-changed" and plugin_setting("auto_sync"):
            # This event belongs to the filament library. Printer and process
            # profiles have their own explicit entry points.
            self._auto_sync(
                announce=True,
                scope="filament",
                trigger="profile-change",
            )
        elif msg_type == "open-oauth":
            self._start_external_oauth(
                msg.get("provider"),
                msg.get("path"),
                msg.get("requestId"),
            )
        elif msg_type == "open-external":
            self._open_site_path(msg.get("path"))
        elif msg_type == "auth-logout":
            clear_auth()
            self._session_sync_started = False
        elif msg_type == "recover":
            token = (load_saved_auth() or {}).get("accessToken") or ""
            BACKGROUND_WORKER.submit(self._do_recover_scan, token)
        elif msg_type == "recover-import":
            token = (load_saved_auth() or {}).get("accessToken") or ""
            BACKGROUND_WORKER.submit(self._do_recover_import, token, msg.get("names"))

    def _do_recover_scan(self, token):
        # Disk-only scan across every account + version backup; hand the list to
        # the embed to show its checkbox picker. Marks already-imported.
        candidates = scan_recovery_presets()
        imported = load_imported_draft_ids()
        self._deliver_recovery(
            [
                {
                    "key": c["key"],
                    "kind": c["kind"],
                    "name": c["name"],
                    "account": c["account"],
                    "source": c["source"],
                    "imported": (
                        _draft_id(c["key"]) in imported
                        or (
                            c["kind"] == "filament"
                            and _draft_id(c["name"]) in imported
                        )
                    ),
                }
                for c in candidates
            ]
        )

    def _do_recover_import(self, token, keys):
        # Push only the checked presets. Filaments remain drafts; machine/process
        # files reuse the normal delta contract. A connection-only machine is
        # recovered as physical-printer evidence rather than a duplicate profile.
        if not token:
            self._deliver_notice(ui_text("sessionExpired"), "warning")
            return
        if not isinstance(keys, list) or not keys:
            self._deliver_notice(ui_text("recoveryNone"), "warning")
            return
        wanted = {str(key) for key in keys}
        candidates = disambiguate_recovery_candidates(
            [c for c in scan_recovery_presets() if c["key"] in wanted]
        )
        imported = load_imported_draft_ids()
        recovered_keys = set()
        # A machine file identical to its parent and without a connection has
        # nothing to send, so it counts neither as recovered nor as failed.
        attempted_keys = set()

        filament_candidates = [c for c in candidates if c["kind"] == "filament"]
        attempted_keys.update(candidate["key"] for candidate in filament_candidates)
        sent_filaments = set(
            push_filament_drafts(token, filament_candidates, authoritative=False)
        )
        for candidate in filament_candidates:
            if candidate.get("_draft_sync_id") in sent_filaments:
                recovered_keys.add(candidate["key"])

        observations = []
        observation_keys = {}
        for kind in ("machine", "process"):
            kind_candidates = [c for c in candidates if c["kind"] == kind]
            sync_items = []
            keys_by_name = {}
            for candidate in kind_candidates:
                item = recovery_profile_sync_item(candidate)
                if item is None:
                    if kind == "machine":
                        observation = recovery_connection_observation(candidate)
                        if observation is not None:
                            observations.append(observation)
                            observation_keys.setdefault(candidate["name"], []).append(
                                candidate["key"]
                            )
                            attempted_keys.add(candidate["key"])
                    continue
                sync_items.append(item)
                keys_by_name.setdefault(candidate["name"], []).append(candidate["key"])
                attempted_keys.add(candidate["key"])
            if sync_items:
                sent, failed = push_user_profiles(
                    kind, token, sync_items, {}, authoritative=False
                )
                if failed == 0 and sent == len(sync_items):
                    for item in sync_items:
                        recovered_keys.update(keys_by_name.get(item["name"], []))

        if observations:
            sync_preferences = _sync_preferences(token)
            status, _result = send_printer_observations(
                token,
                _observations_for_sync(
                    observations,
                    share_endpoints=sync_preferences["sync_printer_endpoints"],
                    discovery_key=sync_preferences.get("printer_discovery_key", ""),
                ),
                plugin_source_instance_id(),
                snapshot_complete=False,
            )
            if status == 200:
                for observation in observations:
                    recovered_keys.update(
                        observation_keys.get(observation["preset_name"], [])
                    )

        for key in recovered_keys:
            imported[_draft_id(key)] = 1
        for candidate in filament_candidates:
            stable_id = candidate.get("_draft_sync_id")
            if stable_id in sent_filaments:
                imported[stable_id] = 1
        if recovered_keys:
            save_imported_draft_ids(imported)
        recovered = len(recovered_keys)
        attempted = len(attempted_keys)
        if attempted and not recovered:
            self._deliver_notice(ui_text("recoveryFailed"), "error")
        elif recovered < attempted:
            self._deliver_notice(
                ui_text("recoveryPartial", count=recovered, total=attempted), "warning"
            )
        else:
            self._deliver_notice(ui_text("recoveryDone", count=recovered), "success")

    def _do_printer_recovery_state(
        self, request_id, owner_user_id, original_observations
    ):
        try:
            local_state = current_printer_recovery_state(
                owner_user_id, original_observations
            )
        except (OSError, ValueError) as exc:
            fh_log("printer recovery inventory failed: %s" % exc)
            self._deliver_printer_recovery(
                "printer-recovery-state-result",
                request_id,
                status="error",
                message=ui_text("printerBundleInvalid"),
            )
            return
        self._deliver_printer_recovery(
            "printer-recovery-state-result",
            request_id,
            localState=local_state,
        )

    def _do_apply_printer_recovery(self, request_id, bundle):
        try:
            _scope, artifacts, counts = install_printer_recovery(bundle)
        except (OSError, ValueError) as exc:
            fh_log("printer recovery install failed: %s" % exc)
            self._deliver_printer_recovery(
                "printer-recovery-action-result",
                request_id,
                status="error",
                message=ui_text("printerBundleInvalid"),
                results=[],
            )
            return
        wrote_profiles = counts["machine"] + counts["process"] > 0
        reload_requested = (
            reload_managed_local_bundle_if_available() if wrote_profiles else False
        )
        result_state = (
            "reload_requested" if reload_requested else "written_restart_required"
        )
        self._deliver_printer_recovery(
            "printer-recovery-action-result",
            request_id,
            message=(
                ui_text(
                    "printerBundleInstalled",
                    machines=counts["machine"],
                    processes=counts["process"],
                )
                if wrote_profiles else ""
            ),
            results=[
                {
                    "kind": item["kind"],
                    "profileId": item["profile_id"],
                    "name": item["name"],
                    "state": "unchanged" if item["unchanged"] else result_state,
                }
                for item in artifacts
            ],
        )

    def _do_remove_printer_recovery(self, request_id, artifact_keys):
        try:
            outcome = remove_printer_recovery_artifacts(artifact_keys)
        except OSError as exc:
            fh_log("printer recovery removal failed: %s" % exc)
            self._deliver_printer_recovery(
                "printer-recovery-action-result",
                request_id,
                status="error",
                message=ui_text("printerBundleInvalid"),
                results=[],
            )
            return
        reload_requested = reload_managed_local_bundle_if_available()
        removed_state = (
            "removal_reload_requested"
            if reload_requested
            else "removed_restart_required"
        )
        results = [dict(item, state=removed_state) for item in outcome["removed"]]
        results.extend(dict(item, state="error") for item in outcome["failed"])
        self._deliver_printer_recovery(
            "printer-recovery-action-result",
            request_id,
            status="warning" if outcome["failed"] else "success",
            message=ui_text("summaryRemoved", count=len(outcome["removed"])),
            results=results,
        )

    def _do_install_printer_bundle(self, request_id, physical_printer_id, token):
        if not token:
            self._deliver_printer_bundle_result(
                request_id, ui_text("importSignIn"), "error"
            )
            return
        status, body = http_get(
            "/physical-printers/%d/orcaslicer-bundle" % int(physical_printer_id),
            token=token,
        )
        if status == 401:
            clear_auth()
            self._deliver_printer_bundle_result(
                request_id, ui_text("sessionExpired"), "error"
            )
            return
        if status != 200:
            self._deliver_printer_bundle_result(
                request_id,
                ui_text("printerBundleFailed", status=status),
                "error",
            )
            return
        try:
            bundle = json.loads(body.decode("utf-8"))
            counts = install_printer_bundle(bundle, physical_printer_id)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            fh_log("printer bundle install failed: %s" % exc)
            self._deliver_printer_bundle_result(
                request_id, ui_text("printerBundleInvalid"), "error"
            )
            return
        # The host API only confirms that a reload was requested. It does not
        # prove the new presets became selectable in the current session.
        reload_managed_local_bundle_if_available()
        self._deliver_printer_bundle_result(
            request_id,
            ui_text(
                "printerBundleInstalled",
                machines=counts["machine"],
                processes=counts["process"],
            ),
            physical_printer_id=physical_printer_id,
            installed=True,
        )

    def _do_remove_printer_bundle(self, request_id, physical_printer_id):
        try:
            counts = remove_installed_printer_bundle(physical_printer_id)
        except OSError as exc:
            fh_log("printer bundle removal failed: %s" % exc)
            self._deliver_printer_bundle_result(
                request_id,
                ui_text("printerBundleInvalid"),
                "error",
                physical_printer_id=physical_printer_id,
                installed=True,
            )
            return
        reload_managed_local_bundle_if_available()
        self._deliver_printer_bundle_result(
            request_id,
            ui_text("summaryRemoved", count=counts["machine"] + counts["process"]),
            physical_printer_id=physical_printer_id,
            installed=False,
        )

    def _do_printer_bundle_status(
        self, request_id, physical_printer_ids, token
    ):
        installed = installed_printer_bundle_ids(physical_printer_ids)
        # Compatibility status is deliberately local-only. Reconstructing old
        # per-printer ownership by fetching every server bundle caused an N×GET
        # fan-out merely by opening the page and failed noisily when export was
        # disabled. The Recovery Center scans durable local markers instead.
        self._deliver_printer_bundle_status(request_id, installed)

    def _start_external_oauth(self, provider, path, request_id=None):
        """Open a server-created OAuth handoff without accepting an arbitrary URL."""
        if provider not in ("google", "yandex") or not isinstance(path, str):
            return
        parsed = urllib.parse.urlsplit(path)
        expected_path = "/oauth/plugin-start/%s" % provider
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or parsed.path != expected_path
            or not parsed.query
        ):
            return
        try:
            query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
        except ValueError:
            return
        flow_id = query.get("flow", [])
        if (
            set(query) != {"flow"}
            or len(flow_id) != 1
            or re.fullmatch(r"[A-Za-z0-9_-]{24,160}", flow_id[0]) is None
        ):
            return
        request_id = request_id if isinstance(request_id, str) and len(request_id) <= 100 else ""
        opened = open_in_system_browser(SITE_URL + path)
        self._deliver("oauth-browser-opened", opened=opened, requestId=request_id)

    def _open_site_path(self, path):
        # A wiki page links to other parts of the site. Inside this panel there is
        # nowhere for a second tab to go, so the link opens in the real browser.
        # Only a site-relative path is accepted and the origin is added here, so
        # the embedded page cannot turn this into "open any address".
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            return
        open_in_system_browser(SITE_URL + path)

    def _log_managed_preset_state(self, folder, remote_ids, loaded_preset_ids, failed_ids):
        """Record desired, on-disk and host-loaded counts as three separate facts.

        They routinely disagree: a profile written during this session only
        reaches Orca after a restart, and one Orca refused to parse never
        arrives at all. Reporting the file count as "synced" hides both.
        """
        on_disk = set(scan_local_fh_presets(folder))
        if failed_ids:
            fh_log("sync failed presets: %s" % sorted(set(failed_ids)))
        if loaded_preset_ids is None:
            fh_log(
                "sync state: desired=%d files=%d loaded=unknown"
                % (len(remote_ids), len(on_disk))
            )
            return
        loaded = on_disk & loaded_preset_ids
        pending_restart = sorted(on_disk - loaded_preset_ids)
        fh_log(
            "sync state: desired=%d files=%d loaded=%d pending_restart=%s"
            % (len(remote_ids), len(on_disk), len(loaded), pending_restart)
        )

    # --- two-way sync (plugin-side) ------------------------------------------ #
    def _pull_one(self, pid, token, known_presets, folder, remote):
        # Download a FilamentHub preset and write it locally under the FilamentHub
        # group. Returns the sync-state record to store, or None on failure.
        version_id = (remote or {}).get("selected_version_id")
        export_path = "/presets/%d/export/orcaslicer.json" % pid
        if isinstance(version_id, int):
            export_path += "?version_id=%d" % version_id
        status, body = http_get(export_path, token=token)
        if status != 200:
            fh_log("pull %d FAILED: export HTTP %s" % (pid, status))
            return None
        try:
            profile = validate_filament_profile(json.loads(body.decode("utf-8")))
        except (TypeError, ValueError) as exc:
            fh_log("pull %d FAILED: bad export payload: %r" % (pid, exc))
            return None
        ensure_parent_exists(profile, known_presets)
        ensure_filament_colour(profile)
        profile["bundle_id"] = "%s%d" % (BUNDLE_PREFIX, pid)
        source_name = profile.get("name") or ("FilamentHub preset %d" % pid)
        name = filament_display_name(profile, source_name)
        profile_path = preset_file_path(folder, name, pid)
        name = apply_managed_filename_identity(profile, profile_path)
        base = profile_path[:-len(".json")]
        # Re-check after the local adjustments: an already working file must never
        # be replaced by a profile Orca would refuse to load.
        try:
            validate_filament_profile(profile)
        except ValueError as exc:
            fh_log("pull %d FAILED: profile Orca would reject: %r" % (pid, exc))
            return None
        try:
            with side_effect_transaction():
                write_managed_info(base, pid, token, version_id)
                write_json_atomic(profile_path, profile)
                remove_stale_preset_files(folder, pid, profile_path)
        except OSError as exc:
            fh_log("pull %d FAILED: write error at %s: %r" % (pid, profile_path, exc))
            return None
        return {"updated_at": (remote or {}).get("updated_at") or "",
                "version_id": version_id,
                "hash": preset_content_hash(profile), "name": name}

    def _push_one(self, pid, token, local_entry, remote):
        # Send a locally-edited preset back to FilamentHub. The backend updates the
        # user's own preset or forks a non-owned one into a new user preset.
        profile = local_entry["profile"]
        local_name = profile.get("name") or ("FilamentHub preset %d" % pid)
        remote_name = (remote or {}).get("name") or ""
        normalized_remote_name = safe_filename(remote_name) if remote_name else ""
        automatic_local_names = set()
        if normalized_remote_name:
            automatic_display_name = safe_filename(
                filament_display_name(profile, normalized_remote_name)
            )
            legacy_display_name = safe_filename(
                _legacy_material_display_name(profile, normalized_remote_name)
            )
            automatic_local_names.update({
                normalized_remote_name,
                "%s (FH-%d)" % (normalized_remote_name, pid),
                automatic_display_name,
                "%s (FH-%d)" % (automatic_display_name, pid),
                legacy_display_name,
                "%s (FH-%d)" % (legacy_display_name, pid),
            })
        upload_name = (
            remote_name
            if local_name in automatic_local_names
            else filament_source_name(profile, local_name)
        )
        upload_profile = restore_remote_parent_for_upload(profile, pid, token)
        if upload_profile is None:
            fh_log("push %d deferred: canonical parent could not be verified" % pid)
            return None
        upload_profile["name"] = upload_name
        upload_profile["filament_settings_id"] = [upload_name]
        item = {
            "fhub_id": pid,
            "base_version_id": (
                local_entry.get("version_id")
                or (remote or {}).get("selected_version_id")
            ),
            "name": upload_name[:200],
            "orcaslicer_settings": upload_profile,
            "source": "orcaslicer",
        }
        info_path = local_entry["path"][:-len(".json")] + ".info"
        try:
            with open(info_path, "r", encoding="utf-8") as fh:
                item["info_content"] = fh.read()
        except OSError:
            pass
        status, response_body = http_post_json(
            "/orcaslicer/filaments/import", token, {"profiles": [item]}
        )
        if status != 200:
            fh_log("push %d FAILED: import HTTP %s" % (pid, status))
            return None
        try:
            response_items = (
                json.loads(response_body.decode("utf-8")) or {}
            ).get("results") or []
            response_item = response_items[0] if response_items else {}
        except (AttributeError, UnicodeDecodeError, ValueError):
            response_item = {}
        server_id = response_item.get("fhub_id")
        if not isinstance(server_id, int):
            server_id = pid
        server_version_id = response_item.get("version_id")
        if not isinstance(server_version_id, int):
            server_version_id = item.get("base_version_id")

        result_path = local_entry["path"]
        result_hash = local_entry["hash"]
        if server_id != pid:
            # Editing a foreign shared preset creates a personal fork. Move the
            # saved bytes to the new managed identity and quarantine the old
            # marker pair so the source can be downloaded again independently.
            fork_profile = dict(profile)
            fork_profile["bundle_id"] = "%s%d" % (BUNDLE_PREFIX, server_id)
            fork_profile["fhub_id"] = str(server_id)
            fork_profile["fhub_source"] = "filamenthub"
            fork_path = preset_file_path(
                os.path.dirname(local_entry["path"]),
                fork_profile.get("name") or upload_name,
                server_id,
            )
            apply_managed_filename_identity(fork_profile, fork_path)
            try:
                with side_effect_transaction():
                    write_managed_info(
                        fork_path[:-len(".json")], server_id, token, server_version_id
                    )
                    write_json_atomic(fork_path, fork_profile)
                    old_artifact = {
                        "json_path": local_entry["path"],
                        "info_path": local_entry["path"][:-len(".json")] + ".info",
                    }
                    if not _quarantine_managed_preset_artifact(
                        old_artifact, "forked-from-%d" % pid
                    ):
                        fh_log("push %d fork kept both marker pairs for recovery" % pid)
                        return None
            except OSError as exc:
                fh_log("push %d fork identity write FAILED: %r" % (pid, exc))
                return None
            result_path = fork_path
            result_hash = preset_content_hash(fork_profile)
        elif isinstance(server_version_id, int):
            try:
                write_managed_info(
                    local_entry["path"][:-len(".json")],
                    pid,
                    token,
                    server_version_id,
                )
            except OSError as exc:
                fh_log("push %d version marker write FAILED: %r" % (pid, exc))
                return None

        return {
            "updated_at": (remote or {}).get("updated_at") or "",
            "version_id": server_version_id,
            "hash": result_hash,
            "name": profile.get("name") or "",
            "preset_id": server_id,
            "path": result_path,
        }

    def _do_sync(self, token, known_presets, announce=True, active_filaments=None,
                 host_profiles=None, observations=None, source_instance_id="",
                 moonraker_connections=None, loaded_preset_ids=None, scope="all",
                 operation_id="", trigger="manual"):
        manual = trigger == "manual" or bool(operation_id)
        if not token or scope not in SYNC_SCOPES:
            if manual:
                self._deliver_sync_result(
                    ui_text("syncSignIn"), operation_id=operation_id,
                    scope=scope, status="warning",
                )
            return

        preferences = _sync_preferences(token)
        if not preferences["available"]:
            if preferences.get("status") == 401:
                # A rejected capability is not a sync failure: the signed-in page
                # mints a new one, and its arrival starts the session sync again.
                clear_auth_if_current(token)
                self._session_sync_started = False
                message_key = "sessionExpired"
            else:
                message_key = "syncUnreachable"
            if manual:
                self._deliver_sync_result(
                    ui_text(message_key), operation_id=operation_id,
                    scope=scope, status="warning",
                )
            return

        state = load_sync_state()
        contours = []
        overall_status = "success"
        new_draft_count = 0
        restart_required = False
        changed = False
        connection_review = False
        # "kind:detail" keys of the attention-worthy conditions found in this run.
        warning_keys = set()
        filament_report = None
        filament_report_results = None
        filament_report_requested = False

        def add_contour(kind, parts, status="success"):
            nonlocal overall_status
            summary = ", ".join(parts) if parts else ui_text("summaryNothing")
            contours.append({"kind": kind, "status": status, "summary": summary})
            if status == "error":
                overall_status = "error"
            elif status == "warning" and overall_status == "success":
                overall_status = "warning"

        if sync_scope_includes(scope, "filament"):
            filament_parts = []
            filament_status = "success"
            pulled = updated = pushed = skipped = failed = renamed = removed = conflicts = 0
            unsent = 0
            failed_ids = []
            remote_names = {}
            remote_ids = set()
            changed_file_ids = set()
            folder = user_filament_dir()
            allow_pull = preferences["allow_filament_presets_export"]
            allow_push = preferences["allow_filament_presets_import"]
            if allow_pull:
                ensure_bundle_metadata()
                try:
                    ensure_directory(folder)
                except OSError:
                    pass
                if source_instance_id and operation_id:
                    filament_report_requested = True
                    filament_report = begin_filament_sync_report(
                        token, source_instance_id
                    )
                remote_status, remote_body = http_get("/auth/my-presets", token=token)
                if remote_status == 401:
                    clear_auth_if_current(token)
                    self._session_sync_started = False
                    filament_parts.append(ui_text("sessionExpired"))
                    filament_status = "warning"
                    warning_keys.add("filament:session")
                    remote_items = None
                elif remote_status != 200:
                    fh_log("my-presets HTTP %s" % remote_status)
                    filament_parts.append(ui_text("summaryListFailed"))
                    if remote_status == 0:
                        filament_status = "warning"
                        warning_keys.add("filament:preset-list")
                    else:
                        filament_status = "error"
                    remote_items = None
                else:
                    try:
                        remote_items = (
                            json.loads(remote_body.decode("utf-8")) or {}
                        ).get("items") or []
                    except (AttributeError, UnicodeDecodeError, ValueError):
                        fh_log("my-presets response could not be read")
                        remote_items = None
                        filament_parts.append(ui_text("summaryListFailed"))
                        filament_status = "error"

                if remote_items is not None:
                    remote_names = {
                        item.get("id"): str(item.get("name") or "").strip()
                        for item in remote_items
                        if isinstance(item, dict) and isinstance(item.get("id"), int)
                    }
                    local = scan_local_fh_presets(folder)
                    previous_managed_ids = set(local)
                    previous_managed_ids.update(
                        int(key) for key in state
                        if isinstance(key, str) and key.isdigit()
                    )
                    fh_log(
                        "sync start: plugin %s scope=%s trigger=%s remote=%d local=%d"
                        % (PLUGIN_VERSION, scope, trigger, len(remote_items), len(local))
                    )
                    for remote in remote_items:
                        preset_id = remote.get("id")
                        if not isinstance(preset_id, int):
                            continue
                        remote_ids.add(preset_id)
                        record = state.get(str(preset_id)) or {}
                        local_entry = local.get(preset_id)
                        remote_updated = remote.get("updated_at") or ""
                        if local_entry is None:
                            result = self._pull_one(
                                preset_id, token, known_presets, folder, remote
                            )
                            if result:
                                state[str(preset_id)] = result
                                pulled += 1
                                changed_file_ids.add(preset_id)
                            else:
                                failed += 1
                                failed_ids.append(preset_id)
                            continue
                        try:
                            migrated_name = migrate_managed_filament_display_name(
                                folder, preset_id, local_entry, remote
                            )
                        except (OSError, ValueError) as exc:
                            fh_log(
                                "preset %d display-name migration failed: %s"
                                % (preset_id, type(exc).__name__)
                            )
                            migrated_name = False
                        if migrated_name:
                            renamed += 1
                            changed_file_ids.add(preset_id)
                            if record:
                                record = dict(record)
                                record["hash"] = local_entry["hash"]
                                record["name"] = migrated_name
                                state[str(preset_id)] = record
                        if orca_transport_violations(local_entry["profile"]):
                            result = self._pull_one(
                                preset_id, token, known_presets, folder, remote
                            )
                            if result:
                                state[str(preset_id)] = result
                                updated += 1
                                changed_file_ids.add(preset_id)
                            else:
                                failed += 1
                                failed_ids.append(preset_id)
                            continue
                        if not record:
                            recovered = recover_sync_record(
                                preset_id, token, known_presets, local_entry,
                                remote,
                            )
                            if recovered is None:
                                skipped += 1
                                continue
                            if recovered is False:
                                if not allow_push:
                                    unsent += 1
                                    continue
                                result = self._push_one(
                                    preset_id, token, local_entry, remote
                                )
                                if result:
                                    pushed_id = result.get("preset_id") or preset_id
                                    state_record = {
                                        key: value for key, value in result.items()
                                        if key not in {"preset_id", "path"}
                                    }
                                    state[str(pushed_id)] = state_record
                                    if pushed_id != preset_id:
                                        remote_ids.add(pushed_id)
                                        changed_file_ids.add(pushed_id)
                                        restored = self._pull_one(
                                            preset_id, token, known_presets, folder, remote
                                        )
                                        if restored:
                                            state[str(preset_id)] = restored
                                            changed_file_ids.add(preset_id)
                                            pulled += 1
                                        else:
                                            state.pop(str(preset_id), None)
                                            failed += 1
                                            failed_ids.append(preset_id)
                                    else:
                                        remove_stale_preset_files(
                                            folder, preset_id, local_entry["path"]
                                        )
                                    pushed += 1
                                else:
                                    failed += 1
                                    failed_ids.append(preset_id)
                                continue
                            record = recovered
                            state[str(preset_id)] = record
                        local_changed = local_entry["hash"] != (
                            record.get("hash") or ""
                        )
                        remote_version_id = remote.get("selected_version_id")
                        if isinstance(remote_version_id, int):
                            remote_newer = remote_version_id != record.get("version_id")
                        else:
                            remote_newer = remote_updated > (
                                record.get("updated_at") or ""
                            )
                        if local_changed and remote_newer:
                            conflicts += 1
                            filament_status = "warning"
                            warning_keys.add("filament:conflict:%d" % preset_id)
                            fh_log(
                                "preset %d conflict: local and FilamentHub changed since the last sync"
                                % preset_id
                            )
                            continue
                        if local_changed:
                            if not allow_push:
                                unsent += 1
                                continue
                            result = self._push_one(
                                preset_id, token, local_entry, remote
                            )
                            if result:
                                pushed_id = result.get("preset_id") or preset_id
                                state_record = {
                                    key: value for key, value in result.items()
                                    if key not in {"preset_id", "path"}
                                }
                                state[str(pushed_id)] = state_record
                                if pushed_id != preset_id:
                                    remote_ids.add(pushed_id)
                                    changed_file_ids.add(pushed_id)
                                    restored = self._pull_one(
                                        preset_id, token, known_presets, folder, remote
                                    )
                                    if restored:
                                        state[str(preset_id)] = restored
                                        changed_file_ids.add(preset_id)
                                        pulled += 1
                                    else:
                                        state.pop(str(preset_id), None)
                                        failed += 1
                                        failed_ids.append(preset_id)
                                else:
                                    remove_stale_preset_files(
                                        folder, preset_id, local_entry["path"]
                                    )
                                pushed += 1
                            else:
                                failed += 1
                                failed_ids.append(preset_id)
                        elif remote_newer:
                            result = self._pull_one(
                                preset_id, token, known_presets, folder, remote
                            )
                            if result:
                                state[str(preset_id)] = result
                                updated += 1
                                changed_file_ids.add(preset_id)
                            else:
                                failed += 1
                                failed_ids.append(preset_id)
                        else:
                            name = local_entry["profile"].get("name") or (
                                "FilamentHub preset %d" % preset_id
                            )
                            canonical = preset_file_path(folder, name, preset_id)
                            if os.path.normcase(os.path.abspath(canonical)) != os.path.normcase(
                                os.path.abspath(local_entry["path"])
                            ):
                                if rename_managed_preset_artifact(
                                    local_entry["path"],
                                    canonical,
                                    managed_info_bytes(
                                        preset_id,
                                        local_entry.get("version_id")
                                        or record.get("version_id"),
                                    ),
                                ):
                                    local_entry["path"] = canonical
                                    renamed += 1
                                    changed_file_ids.add(preset_id)
                            remove_stale_preset_files(
                                folder, preset_id, local_entry["path"]
                            )
                            skipped += 1

                    removed, removed_ids = quarantine_unwanted_managed_preset_files(
                        folder, remote_ids
                    )
                    for key in list(state):
                        if key.isdigit() and int(key) not in remote_ids:
                            state.pop(key, None)
                    file_changes = bool(pulled or updated or removed or renamed)
                    bundle_reloaded = (
                        reload_managed_local_bundle_if_available()
                        if file_changes else False
                    )
                    if bundle_reloaded:
                        loaded_preset_ids = set(scan_local_fh_presets(folder))
                    self._log_managed_preset_state(
                        folder, remote_ids, loaded_preset_ids, failed_ids
                    )
                    restart_required = file_changes and not bundle_reloaded
                    if filament_report is not None:
                        on_disk_ids = set(scan_local_fh_presets(folder))
                        failed_id_set = set(failed_ids)
                        report_results = []
                        for preset_id in sorted(remote_ids):
                            error_code = None
                            if preset_id in failed_id_set:
                                observed_state = "error"
                                error_code = "local_write_or_validation_failed"
                            elif preset_id not in on_disk_ids:
                                observed_state = "error"
                                error_code = "managed_file_missing"
                            elif bundle_reloaded:
                                observed_state = "loaded"
                            elif loaded_preset_ids is None:
                                observed_state = "on_disk"
                            elif preset_id in changed_file_ids:
                                observed_state = "pending_restart"
                            elif preset_id in loaded_preset_ids:
                                observed_state = "loaded"
                            else:
                                observed_state = "error"
                                error_code = "host_did_not_load"
                            item = {
                                "preset_id": preset_id,
                                "preset_type": "filament",
                                "operation": "download",
                                "state": observed_state,
                            }
                            if error_code:
                                item["error_code"] = error_code
                            report_results.append(item)

                        confirmed_removed_ids = (
                            previous_managed_ids | set(removed_ids)
                        ) - remote_ids - on_disk_ids
                        report_results.extend(
                            {
                                "preset_id": preset_id,
                                "preset_type": "filament",
                                "operation": "delete",
                                "state": "removed",
                            }
                            for preset_id in sorted(confirmed_removed_ids)
                        )
                        filament_report_results = report_results
            elif not allow_push:
                filament_parts.append(ui_text("summaryDisabled"))

            if (
                active_filaments
                and allow_push
                and preferences["auto_import_local_presets"]
            ):
                imported = load_imported_draft_ids()
                sent_ids = push_filament_drafts(token, active_filaments)
                if sent_ids:
                    new_draft_count = len(sent_ids)
                    for draft_id in sent_ids:
                        imported[draft_id] = 1
                    save_imported_draft_ids(imported)
                    filament_parts.append(
                        ui_text("summaryDrafts", count=len(sent_ids))
                    )
            if pulled:
                filament_parts.append(ui_text("summaryNew", count=pulled))
            if updated:
                filament_parts.append(ui_text("summaryUpdated", count=updated))
            if pushed:
                filament_parts.append(ui_text("summarySent", count=pushed))
            if removed:
                filament_parts.append(ui_text("summaryRemoved", count=removed))
            if renamed:
                filament_parts.append(ui_text("summaryRenamed", count=renamed))
            if conflicts:
                filament_parts.append(ui_text("summaryConflict", count=conflicts))
            if unsent:
                filament_parts.append(ui_text("summaryUnsentDisabled", count=unsent))
            if skipped:
                filament_parts.append(ui_text("summaryCurrent", count=skipped))
            if failed:
                failed_names = [
                    remote_names.get(preset_id) or "FH-%d" % preset_id
                    for preset_id in dict.fromkeys(failed_ids)
                ]
                shown = ", ".join(failed_names[:3])
                if len(failed_names) > 3:
                    filament_parts.append(ui_text(
                        "summaryFailedNamesMore",
                        names=shown,
                        count=len(failed_names) - 3,
                    ))
                else:
                    filament_parts.append(ui_text("summaryFailedNames", names=shown))
                filament_status = "error"
            changed = changed or bool(
                pulled or updated or pushed or removed or renamed or new_draft_count
            )
            add_contour("filament", filament_parts, filament_status)

        for kind in ("machine", "process"):
            if not sync_scope_includes(scope, kind):
                continue
            permission_key = (
                "allow_printer_profiles_import"
                if kind == "machine"
                else "allow_print_profiles_import"
            )
            if not preferences[permission_key]:
                add_contour(kind, [ui_text("summaryDisabled")])
                continue
            scan = (host_profiles or {}).get(kind) or {}
            items = scan.get("items") or []
            complete = bool(scan.get("complete"))
            sent, failed = push_user_profiles(
                kind, token, items, state, authoritative=complete
            )
            changed = changed or bool(sent)
            parts = []
            if sent:
                parts.append(ui_text("summarySent", count=sent))
            if failed:
                parts.append(ui_text("summaryFailed", count=failed))
            status = "error" if failed else "success"
            if not complete:
                parts.append(ui_text("summaryScanIncomplete"))
                warning_keys.add("%s:scan" % kind)
                if status == "success":
                    status = "warning"
            add_contour(kind, parts, status)

        if sync_scope_includes(scope, "machine") and preferences[
            "allow_printer_profiles_import"
        ]:
            observation_status, _observation_result = send_printer_observations(
                token,
                _observations_for_sync(
                    observations,
                    share_endpoints=preferences["sync_printer_endpoints"],
                    discovery_key=preferences.get("printer_discovery_key", ""),
                    local_connections=moonraker_connections,
                ),
                source_instance_id,
            )
            if observation_status not in (None, 200):
                overall_status = "error"
                for item in contours:
                    if item["kind"] == "machine":
                        item["status"] = "error"
                        item["summary"] = "%s, %s" % (
                            item["summary"],
                            ui_text("summaryObservationFailed"),
                        )
                        break
            elif _observation_result.get("pending"):
                # Connections waiting for the person's confirmation are a to-do,
                # not a failed sync: the page offers the way there, calmly.
                connection_review = True
                for item in contours:
                    if item["kind"] == "machine":
                        item["summary"] += ", " + ui_text(
                            "summaryConnectionReview",
                            count=int(_observation_result.get("pending") or 0),
                        )
                        break
            sync_happy_hare_topologies(token, moonraker_connections)

        if sync_scope_includes(scope, "machine"):
            try:
                manual_connections = verified_local_setup_connections(token)
                sync_happy_hare_topologies(token, manual_connections)
            except (ValueError, OSError):
                fh_log("Local printer connection sync unavailable")

        # An automatic run reports a lasting condition once; repeating the same
        # warning at every start teaches people to stop reading it.
        announced = {
            key for key in state.get(ANNOUNCED_WARNINGS_KEY) or []
            if isinstance(key, str)
        }
        new_warning = bool(warning_keys - announced)
        state[ANNOUNCED_WARNINGS_KEY] = sorted(
            {
                key for key in announced
                if not sync_scope_includes(scope, key.split(":", 1)[0])
            }
            | warning_keys
        )
        save_sync_state(state)
        if filament_report_requested:
            report_ok = False
            if filament_report is not None and filament_report_results is not None:
                report_ok = complete_filament_sync_report(
                    token,
                    source_instance_id,
                    filament_report[0],
                    filament_report[1],
                    filament_report_results,
                )
            if not report_ok:
                overall_status = mark_sync_report_failed(contours, overall_status)
        labels = {
            "filament": ui_text("profileFilament"),
            "machine": ui_text("profileMachine"),
            "process": ui_text("profileProcess"),
        }
        title_key = {
            "success": "syncCompleteTitle",
            "warning": "syncAttentionTitle",
            "error": "syncPartialTitle",
        }[overall_status]
        text = ui_text(title_key) + "\n" + "\n".join(
            "%s: %s" % (labels[item["kind"]], item["summary"])
            for item in contours
        )
        if restart_required:
            text += "\n" + ui_text("dropdownRestart")
        fh_log(
            "sync done: scope=%s trigger=%s status=%s"
            % (scope, trigger, overall_status)
        )
        if announce or operation_id:
            # An explicit Sync always reports. An automatic run speaks only about
            # a change, a failure or a warning it has not shown before.
            self._deliver_sync_result(
                text,
                new_draft_count,
                operation_id=operation_id,
                scope=scope,
                status=overall_status,
                contours=contours,
                notify=(
                    manual
                    or overall_status == "error"
                    or new_warning
                    or (changed and plugin_setting("sync_success_notice"))
                ),
                connection_review=connection_review,
            )


_PAGES = getattr(orca, "pages", None)
_PAGE_CAPABILITY_BASE = getattr(_PAGES, "PagesPluginCapabilityBase", None)


class _PageWindowProxy:
    """Adapt the host Pages push API to the window helper contract."""

    def __init__(self, page):
        self._page = page

    def is_open(self):
        return self._page is not None

    def post(self, payload):
        self._page.post_message(payload)


if _PAGE_CAPABILITY_BASE is not None:
    class FilamentHubPage(_PluginRuntimeLifecycleMixin, _PAGE_CAPABILITY_BASE):
        def __init__(self):
            super().__init__()
            self._catalog = FilamentHubCatalog()
            self._catalog.win = _PageWindowProxy(self)
            self._catalog._session_sync_started = False
            self._catalog._direct_bridge_session = ""
            self._catalog._local_window = None
            self._catalog._local_dialog_session = ""
            self._catalog._local_dialog_context = None

        def get_name(self):
            return "FilamentHub"

        def get_icon(self):
            return ensure_icon()

        def on_load(self):
            apply_plugin_settings(read_capability_settings(self), apply_server=True)
            super().on_load()
            _set_slice_delivery_target(self._catalog)

        def has_config_ui(self):
            return True

        def get_config_ui(self):
            return render_settings_page()

        def get_default_config(self):
            return dict(PLUGIN_SETTINGS_DEFAULTS)

        def get_ui(self):
            apply_plugin_settings(read_capability_settings(self))
            self._catalog._direct_bridge_session = secrets.token_urlsafe(32)
            return render_direct_page(self._catalog._direct_bridge_session)

        def on_message(self, message):
            if isinstance(message, str):
                try:
                    message = json.loads(message)
                except ValueError:
                    return
            apply_plugin_settings(read_capability_settings(self))
            self._catalog.on_message(message)

        def on_unload(self):
            self._catalog.on_close()
            if _slice_delivery_target() is self._catalog:
                _set_slice_delivery_target(None)
            stop_plugin_runtime()
else:
    FilamentHubPage = None


def host_capability_lifecycle_available():
    """Whether every capability selected for this host has load/unload hooks."""
    bases = [
        _PAGE_CAPABILITY_BASE
        if _PAGE_CAPABILITY_BASE is not None
        else orca.script.ScriptPluginCapabilityBase
    ]
    if _SLICE_CAPABILITY_BASE is not None:
        bases.append(_SLICE_CAPABILITY_BASE)
    return all(
        callable(getattr(base, "on_load", None))
        and callable(getattr(base, "on_unload", None))
        for base in bases
    )


@orca.plugin
class FilamentHubPlugin(orca.base):
    def register_capabilities(self):
        # Hosts predating capability lifecycle hooks still need the registration
        # behavior used by earlier plugin releases. Current hosts start resources
        # from on_load and stop them through on_cancelled/on_unload instead.
        if not host_capability_lifecycle_available():
            start_plugin_runtime()
        if FilamentHubPage is not None:
            orca.register_capability(FilamentHubPage)
        else:
            orca.register_capability(FilamentHubCatalog)
        if FilamentHubSliceReporter is not None:
            orca.register_capability(FilamentHubSliceReporter)
