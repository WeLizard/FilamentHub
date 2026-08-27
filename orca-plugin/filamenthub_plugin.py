# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub"
# name = "FilamentHub"
# description = "Browse and sync community-rated filament profiles from FilamentHub, with spool inventory and print-cost tools."
# author = "FilamentHub"
# version = "0.1.4"
#
# # Proposed forward-looking key (see README gap). The current
# # host reads only name/description/author/version/dependencies and ignores unknown
# # keys, so declaring this today is harmless and documents intent.
# network = ["filamenthub.ru", "*.filamenthub.ru"]
# ///
"""FilamentHub plugin for OrcaSlicer's Python plugin system.

iframe passthrough: the plugin window is a thin shell that embeds our real React
catalog (https://filamenthub.ru/embed/catalog) in an <iframe>. The React app runs
chrome-less in embed mode and, when the user clicks "Import into OrcaSlicer" on a
preset, posts a message up to this shell via window.parent.postMessage. The shell
relays it through the injected window.orca bridge to Python on_message below, which
downloads the authenticated OrcaSlicer export and writes it into the user preset
folder, then shows a native "restart required" dialog. A separate explicit action
on a physical-printer card can restore managed machine and process profile copies;
they are never pulled automatically and never overwrite unmanaged Orca profiles.

The shell also renders an Orca-themed toolbar (host --orca-* CSS variables, same
role as the native Catalog/Profile/Wiki buttons of the C++ fork panel) and drives
the catalog by posting {type:'navigate', path} down into the iframe — the SPA
listens and switches routes without reloading. The catalog reports the signed-in
user (auth-state) for the toolbar label, and hands tokens over (auth-token) so
Python persists the scoped plugin capability in .auth.json next to the plugin.

External-browser OAuth: Google/Yandex refuse their consent pages inside an
embedded WebView, so the "Sign in with Google/Yandex" buttons post open-oauth up
here; Python opens the user's real browser at /oauth/plugin-start (falling back to
a copy-the-link overlay if the browser can't be launched). After the provider
round-trip the site redirects the minted session back to a loopback /d/<secret>
endpoint (guarded by a one-time nonce); the shell polls /s/<secret>, then hands
the session down to the iframe (auth-restore), which signs in exactly like the
normal flow. Account tokens are held in memory only — never written to disk.

  iframe (React) --window.parent.postMessage({source:'filamenthub-plugin',...})-->
      shell window --orca.postMessage(...)--> Python on_message
          --GET /presets/{id}/export/orcaslicer.json (Bearer token from the page)-->
              write {data_dir}/user/<active>/_local/filamenthub/filament/<name>.json
                  --> host restart dialog

Runtime surface used (confirmed against the current upstream plugin API):
  * orca.pages.PagesPluginCapabilityBase                    — native page
  * orca.script.ScriptPluginCapabilityBase.execute()        — old-host fallback
  * capability on_load/on_cancelled/on_unload hooks         — runtime lifecycle
  * orca.host.ui.create_window(...), message(...)           — fallback UI/notices
  * orca.host.plugin.storage(), app_language()              — private state/locale
  * the injected window.orca bridge (PluginWebDialog.cpp:ORCA_BRIDGE_JS)

Login/token: the user signs in inside the iframe on our own site (normal flow).
The page mints a short-lived, plugin-scoped capability for preset read/write
and reading an explicitly selected owned printer bundle;
the account access/refresh credentials never cross the iframe boundary. The
capability may be cached locally until expiry so a reopened window can resume.
"""

import csv
import datetime
import hashlib
import http.server
import ipaddress
import json
import os
import queue
import random
import re
import secrets
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

import orca


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
        self._lock = threading.Lock()
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

    def shutdown(self, wait_timeout=0.25):
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
            except Exception as exc:
                logger = globals().get("fh_log")
                if logger is not None:
                    logger("background job failed: %s" % exc)
            finally:
                try:
                    del self._local.generation
                except AttributeError:
                    pass
                self._jobs.task_done()


BACKGROUND_WORKER = ReusableDaemonWorker("filamenthub-worker")


def post_window(window, payload):
    """Best-effort host push, safe against a window closing during a worker job."""
    worker = globals().get("BACKGROUND_WORKER")
    if worker is not None and not worker.current_job_is_active():
        return False
    try:
        post = getattr(window, "post", None)
        if window is None or not window.is_open() or not callable(post):
            return False
        post(payload)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
PLUGIN_VERSION = "0.1.4"
PROD_SITE_URL = "https://filamenthub.ru"
SITE_URL = os.environ.get("FILAMENTHUB_SITE_URL", "http://localhost:3000").rstrip("/")
_SITE_PARTS = urllib.parse.urlsplit(SITE_URL)
SITE_ORIGIN = urllib.parse.urlunsplit(
    (_SITE_PARTS.scheme, _SITE_PARTS.netloc, "", "", "")
)
DEV_CONTOUR = SITE_URL != PROD_SITE_URL
SHOW_DIAGNOSTICS = DEV_CONTOUR and os.environ.get(
    "FILAMENTHUB_SHOW_LOG", ""
).strip().lower() in {"1", "true", "yes", "on"}
EMBED_URL = SITE_URL + "/embed/catalog"
API_BASE = SITE_URL + "/api/v1"
HTTP_TIMEOUT = 20
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_TOKEN_LENGTH = 8192
MAX_FILENAME_LENGTH = 120
MAX_MACHINE_BUNDLE_PROFILES = 32
MAX_PROCESS_BUNDLE_PROFILES = 200
_SSL_CTX = ssl.create_default_context()


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


def write_bytes_atomic(path, payload, mode=None):
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


def write_json_atomic(path, payload, mode=None):
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    write_bytes_atomic(path, encoded, mode=mode)


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
    """Cached folder, else the sole non-default account dir on disk, else 'default'."""
    if _user_preset_folder:
        return _user_preset_folder
    try:
        base = os.path.join(DATA_DIR, "user")
        subs = [d for d in os.listdir(base)
                if d != "default" and os.path.isdir(os.path.join(base, d))]
        if len(subs) == 1:
            return subs[0]
    except OSError:
        pass
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

    New hosts may expose ``orca.host.plugin.storage()``.  The current public
    plugin host does not, so it falls back to a stable directory outside the
    replaceable plugin package.  Existing sidecar state is copied once and
    retained as a rollback fallback.
    """
    global PLUGIN_STORAGE_DIR
    global SYNC_LOG_FILE, AUTH_FILE, BAMBU_CONFIG_FILE, IMPORTED_DRAFTS_FILE, SYNC_STATE_FILE
    global _SLICE_INDEX_FILE, _SLICE_CACHE_DIR

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
        ".fh_bambu.json",
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
    IMPORTED_DRAFTS_FILE = os.path.join(target_root, ".fh_imported.json")
    SYNC_STATE_FILE = os.path.join(target_root, ".fh_sync.json")
    _SLICE_INDEX_FILE = os.path.join(target_root, ".fh_slices.json")
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
        import datetime
        trim_sync_log()
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(SYNC_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (stamp, redact_home(str(msg))))
    except OSError:
        pass


def read_sync_log():
    """The log as text, empty when nothing has been written yet."""
    try:
        with open(SYNC_LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


# These are import-time legacy locations. configure_plugin_storage() redirects
# them to durable private storage during capability registration. The iframe's
# own storage is partitioned and dies with the window.
AUTH_FILE = os.path.join(PLUGIN_DIR, ".auth.json")
BAMBU_CONFIG_FILE = os.path.join(PLUGIN_DIR, ".fh_bambu.json")


# Shown in the user's real browser at the end of the external OAuth flow, right
# after the session has been handed back to the plugin over loopback.
OAUTH_DELIVER_OK_HTML = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>FilamentHub</title></head>"
    "<body style='font-family:sans-serif;background:#1e1e2e;color:#e0e0e0;"
    "display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
    "<div style='text-align:center'><h2>Signed in to FilamentHub</h2>"
    "<p>You can close this tab and return to OrcaSlicer.</p></div></body></html>"
)
OAUTH_DELIVER_ERR_HTML = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>FilamentHub</title></head>"
    "<body style='font-family:sans-serif;background:#1e1e2e;color:#e0e0e0;"
    "display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
    "<div style='text-align:center'><h2>Sign-in link expired</h2>"
    "<p>Return to OrcaSlicer and start the sign-in again.</p></div></body></html>"
)


class ShellServer:
    """Loopback-only HTTP host for the shell page.

    The host loads plugin HTML via WebView2 SetPage, which gives the document
    an opaque (null) origin — the site's frame-ancestors CSP can never match
    it, so the catalog iframe comes up as "refused to connect". Chromium also
    forbids navigating from an opaque page to file://, so a real origin needs
    HTTP. This server binds 127.0.0.1 on an ephemeral port and serves exactly
    one page under an unguessable path; the SetPage bootstrap hops onto it and
    the shell gains the http://127.0.0.1:* origin the site CSP allows. The
    page embeds the saved session tokens, hence the secret path and loopback
    bind — the exposure equals the plaintext .auth.json sitting next door.
    """

    def __init__(self):
        self._server = None
        self._server_stop = None
        self._html = b""
        self._path = ""
        # OAuth handoff: Google/Yandex refuse to render their consent pages in an
        # embedded WebView, so the provider flow runs in the user's real browser
        # and returns the session here over loopback. Two secret sibling paths on
        # the same server: /s/<secret> the shell polls for state, /d/<secret> the
        # external browser posts the session to. A per-attempt nonce guards /d.
        self._oauth_secret = secrets.token_urlsafe(24)
        self._oauth = None
        self._oauth_lock = threading.Lock()
        self._sync_lock = threading.Lock()
        self._sync_result = {"text": ""}
        self._recover_lock = threading.Lock()
        self._recover_items = None
        self._slice_lock = threading.Lock()
        self._slice_parse = None
        self._slice_alive = None

    def status_path(self):
        return "/s/" + self._oauth_secret

    def sync_status_path(self):
        return "/y/" + self._oauth_secret

    def recover_status_path(self):
        return "/r/" + self._oauth_secret

    def log_path(self):
        return "/l/" + self._oauth_secret

    def slice_parse_path(self):
        return "/g/" + self._oauth_secret

    def slice_alive_path(self):
        return "/k/" + self._oauth_secret

    def set_sync_result(self, payload):
        with self._sync_lock:
            self._sync_result = dict(payload)

    def _sync_status(self):
        with self._sync_lock:
            result = dict(self._sync_result)
            self._sync_result = {"text": ""}
        return result

    def set_recover_items(self, items):
        with self._recover_lock:
            self._recover_items = list(items)

    def _recover_status(self):
        with self._recover_lock:
            items = self._recover_items
            self._recover_items = None
        return {"ready": items is not None, "items": items or []}

    def set_slice_parse(self, payload):
        with self._slice_lock:
            self._slice_parse = payload

    def _slice_parse_status(self):
        with self._slice_lock:
            payload = self._slice_parse
            self._slice_parse = None
        return {"ready": payload is not None, "result": payload}

    def set_slice_alive(self, keys, hook=None):
        with self._slice_lock:
            self._slice_alive = {"alive": list(keys), "hook": hook}

    def _slice_alive_status(self):
        with self._slice_lock:
            payload = self._slice_alive
            self._slice_alive = None
        if payload is None:
            return {"ready": False, "alive": [], "hook": None}
        return {"ready": True, "alive": payload["alive"], "hook": payload["hook"]}

    def deliver_url(self):
        # Absolute loopback URL the external browser is redirected to with the
        # freshly minted session; empty until the server is bound (window open).
        if self._server is None:
            return ""
        return "http://127.0.0.1:%d/d/%s" % (self._server.server_address[1], self._oauth_secret)

    def arm_oauth(self, nonce, browser_opened, start_url):
        with self._oauth_lock:
            self._oauth = {"nonce": nonce, "browser_opened": bool(browser_opened),
                           "start_url": start_url, "delivered": None}

    def _oauth_status(self):
        with self._oauth_lock:
            state = self._oauth
            if not state:
                return {"stage": "idle"}
            if state.get("delivered"):
                tokens = state["delivered"]
                self._oauth = None  # one-shot: hand off exactly once
                return {"stage": "delivered",
                        "accessToken": tokens.get("access", ""),
                        "refreshToken": tokens.get("refresh", "")}
            out = {"stage": "awaiting", "browserOpened": bool(state.get("browser_opened"))}
            if not state.get("browser_opened"):
                out["startUrl"] = state.get("start_url", "")
            return out

    def _oauth_deliver(self, query):
        nonce = (query.get("nonce") or [""])[0]
        access = (query.get("access") or [""])[0]
        refresh = (query.get("refresh") or [""])[0]
        with self._oauth_lock:
            state = self._oauth
            if not state or not nonce or not secrets.compare_digest(state.get("nonce", ""), nonce):
                return False
            if not access or len(access) > MAX_TOKEN_LENGTH or len(refresh) > MAX_TOKEN_LENGTH:
                return False
            state["delivered"] = {"access": access, "refresh": refresh}
            return True

    @staticmethod
    def _serve(server, stop_event):
        server.timeout = 0.25
        try:
            while not stop_event.is_set():
                server.handle_request()
        finally:
            server.server_close()

    def url_for(self, html):
        self._html = html.encode("utf-8")
        if self._server is None:
            self._path = "/" + secrets.token_urlsafe(32)
            owner = self

            class Handler(http.server.BaseHTTPRequestHandler):
                def _send(self, status, content_type, body):
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header(
                        "Content-Security-Policy",
                        "default-src 'none'; "
                        "script-src 'unsafe-inline'; "
                        "style-src 'unsafe-inline'; "
                        "img-src data:; "
                        "connect-src 'self'; "
                        "frame-src %s; "
                        "object-src 'none'; "
                        "base-uri 'none'; "
                        "form-action 'none'" % SITE_ORIGIN,
                    )
                    self.end_headers()
                    self.wfile.write(body)

                def do_GET(self):
                    path = self.path.split("?", 1)[0]
                    if path == owner._path:
                        self._send(200, "text/html; charset=utf-8", owner._html)
                        return
                    if path == owner.status_path():
                        body = json.dumps(owner._oauth_status()).encode("utf-8")
                        self._send(200, "application/json; charset=utf-8", body)
                        return
                    if path == owner.sync_status_path():
                        body = json.dumps(owner._sync_status()).encode("utf-8")
                        self._send(200, "application/json; charset=utf-8", body)
                        return
                    if path == owner.recover_status_path():
                        body = json.dumps(owner._recover_status()).encode("utf-8")
                        self._send(200, "application/json; charset=utf-8", body)
                        return
                    if path == owner.slice_parse_path():
                        body = json.dumps(owner._slice_parse_status()).encode("utf-8")
                        self._send(200, "application/json; charset=utf-8", body)
                        return
                    if path == owner.slice_alive_path():
                        body = json.dumps(owner._slice_alive_status()).encode("utf-8")
                        self._send(200, "application/json; charset=utf-8", body)
                        return
                    if path == owner.log_path():
                        self._send(200, "text/plain; charset=utf-8",
                                   read_sync_log().encode("utf-8"))
                        return
                    if path == "/d/" + owner._oauth_secret:
                        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                        ok = owner._oauth_deliver(query)
                        html = OAUTH_DELIVER_OK_HTML if ok else OAUTH_DELIVER_ERR_HTML
                        self._send(200 if ok else 400, "text/html; charset=utf-8",
                                   html.encode("utf-8"))
                        return
                    self.send_error(404)

                def log_message(self, *args):
                    pass  # keep the secret paths out of stderr

            # Requests are tiny loopback shell/OAuth hand-offs. A single server
            # thread is sufficient and avoids creating one Python thread for
            # every status request.
            self._server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
            self._server_stop = threading.Event()
            server = self._server
            stop_event = self._server_stop
            worker = threading.Thread(
                target=self._serve,
                args=(server, stop_event),
                name="filamenthub-loopback",
                daemon=True,
            )
            try:
                worker.start()
            except Exception:
                stop_event.set()
                server.server_close()
                self._server = None
                self._server_stop = None
                raise
        return "http://127.0.0.1:%d%s" % (self._server.server_address[1], self._path)

    def stop(self):
        server, self._server = self._server, None
        stop_event, self._server_stop = self._server_stop, None
        with self._oauth_lock:
            self._oauth = None
        if server is not None and stop_event is not None:
            stop_event.set()


SHELL_SERVER = ShellServer()


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
    try:
        os.remove(AUTH_FILE)
    except OSError:
        pass


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


def preset_id_from_info_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return preset_id_from_info_content(fh.read())
    except OSError:
        pass
    return None


def managed_info_bytes(preset_id):
    return ("sync_info = filamenthub:preset:%d\n" % preset_id).encode("utf-8")


def write_managed_info(base, preset_id, token):
    """Persist durable identity even if the optional server .info is unavailable."""
    target = base + ".info"
    write_bytes_atomic(target, managed_info_bytes(preset_id))
    try:
        status, info = http_get(
            "/presets/%d/export/orcaslicer.info" % preset_id,
            token=token,
        )
        if status != 200:
            return
        decoded = info.decode("utf-8")
        if preset_id_from_info_content(decoded) == preset_id:
            write_bytes_atomic(target, info)
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
    moved = 0
    for source in paths:
        try:
            os.replace(source, os.path.join(batch, os.path.basename(source)))
        except OSError as exc:
            fh_log("managed preset quarantine move failed: %r" % exc)
        else:
            moved += 1
    if moved:
        fh_log("managed preset quarantined: reason=%s files=%d" % (reason, moved))
    return bool(moved)


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
        if _quarantine_managed_preset_artifact(artifact, "duplicate-%d" % int(preset_id)):
            removed += 1
    return removed


def quarantine_unwanted_managed_preset_files(folder, remote_ids):
    """Remove FilamentHub-owned artifacts absent from authoritative desired state.

    State-cache membership is deliberately irrelevant: old plugin versions and
    interrupted writes can lose that cache while leaving durable ownership in
    ``bundle_id`` or ``sync_info``. Unmarked files are never touched.
    """
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
        if _quarantine_managed_preset_artifact(leftover, "unmarked-bundle-file"):
            removed += 1
    return removed, removed_ids


def _managed_profile_id_from_info(path, kind):
    prefix = "filamenthub:%s:" % kind
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                key, separator, value = line.partition("=")
                if separator and key.strip() == "sync_info":
                    value = value.strip()
                    if value.startswith(prefix):
                        tail = value[len(prefix):]
                        return int(tail) if tail.isdigit() else None
    except OSError:
        pass


MAX_BAMBU_BRIDGES = 8


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
            printers.append(
                {
                    "physical_printer_id": physical_id,
                    "material_system_id": system_id,
                    "host": host[:253],
                    "access_code": access_code[:128],
                    "serial": serial[:80],
                    "bridge_token": bridge_token[:256],
                }
            )
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

    payload = load_bambu_config()
    printers = [
        item
        for item in payload["printers"]
        if item["physical_printer_id"] != physical_printer_id
    ]
    printers.append(
        {
            "physical_printer_id": physical_printer_id,
            "material_system_id": material_system_id,
            "host": host,
            "access_code": access_code,
            "serial": serial,
            "bridge_token": bridge_token,
        }
    )
    if len(printers) > MAX_BAMBU_BRIDGES:
        raise ValueError("too many Bambu bridges")
    payload["printers"] = printers
    save_bambu_config(payload)
    return payload


def remove_bambu_bridge(physical_printer_id):
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
        validated.append({"id": profile_id, "name": name.strip(), "profile": profile})
    return validated


def prepare_printer_bundle_install(bundle):
    if not isinstance(bundle, dict):
        raise ValueError("Printer bundle must be a JSON object")
    if bundle.get("format") != "filamenthub.orcaslicer.printer-bundle" or bundle.get("version") != 1:
        raise ValueError("Unsupported printer bundle format")

    machines = _validated_bundle_entries(
        bundle, "machine_profiles", "machine", MAX_MACHINE_BUNDLE_PROFILES
    )
    processes = _validated_bundle_entries(
        bundle, "process_profiles", "process", MAX_PROCESS_BUNDLE_PROFILES
    )
    if not machines:
        raise ValueError("Printer bundle has no machine profiles")

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


def install_printer_bundle(bundle):
    prepared = prepare_printer_bundle_install(bundle)
    ensure_bundle_metadata()
    counts = {"machine": 0, "process": 0}
    for kind, profile_id, path, profile in prepared:
        write_json_atomic(path, profile)
        write_managed_profile_info(path[:-len(".json")], kind, profile_id)
        remove_stale_managed_profile_files(
            os.path.dirname(path), profile_id, kind, path
        )
        counts[kind] += 1
    return counts


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
def http_get(path, token=None):
    headers = {"Accept": "application/json", "User-Agent": "FilamentHub-OrcaPlugin/" + PLUGIN_VERSION}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API_BASE + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=_SSL_CTX) as resp:
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
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=_SSL_CTX) as resp:
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
        },
    )
    if status != 200:
        fh_log("sync observation plan rejected: status=%s" % status)
        return None
    try:
        sync_version = (json.loads(body.decode("utf-8")) or {}).get("sync_version")
    except (AttributeError, UnicodeDecodeError, ValueError):
        sync_version = None
    if not isinstance(sync_version, int) or sync_version < 1:
        fh_log("sync observation plan returned no usable version")
        return None
    return sync_version


def complete_filament_sync_report(token, device_fingerprint, sync_version, results):
    """Report bounded per-preset facts; never send file paths or raw exceptions."""
    status, _body = http_post_json(
        "/orcaslicer/sync-complete",
        token,
        {
            "device_fingerprint": device_fingerprint,
            "sync_version": sync_version,
            "results": results,
        },
    )
    if status != 200:
        fh_log("sync observation report rejected: status=%s" % status)
        return False
    return True


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
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=_SSL_CTX) as resp:
            return resp.getcode(), _read_response_limited(resp), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_RESPONSE_BYTES), _bridge_retry_after_seconds(exc.headers)
    except (OSError, ValueError, urllib.error.URLError):
        return 0, b"", None


def http_delete_bridge(path, bridge_token):
    headers = {
        "Accept": "application/json",
        "User-Agent": "FilamentHub-OrcaPlugin/" + PLUGIN_VERSION,
        "X-FilamentHub-Bridge-Token": bridge_token,
    }
    req = urllib.request.Request(API_BASE + path, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=_SSL_CTX) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError, ValueError, urllib.error.URLError):
        return 0


def http_post_file(path, token, file_path, field="file", file_name=""):
    """Send one file to FilamentHub the way a browser upload would.

    The G-code never passes through the page: it goes from this machine straight
    to the server, so a 25 MB slice costs nothing in the WebView.
    """
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
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT * 4, context=_SSL_CTX) as resp:
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


def observe_printer_presets():
    """What OrcaSlicer knows about the machines this person has (UI thread —
    reads preset_bundle). Two kinds of entry, and printhost_apikey is in neither:

    * every saved user preset, including distinct endpoints/names;
    * visible system presets. Orca marks the models enabled by the person in its
      setup separately from the rest of each vendor bundle, so visibility is the
      evidence that a stock machine belongs in the user's workspace.
    """
    observed_connections = []
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
    except Exception as exc:
        fh_log("printer observation scan failed: %s" % exc)
    return observed_connections


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
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Moonraker address is not a plain HTTP(S) origin")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Moonraker port is invalid") from exc
    host = parsed.hostname
    if ":" in host:
        host = "[" + host + "]"
    return "%s://%s%s" % (
        parsed.scheme,
        host,
        (":" + str(port)) if port is not None else "",
    )


def _moonraker_json(connection, path, payload=None):
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
        with urllib.request.urlopen(
            request,
            timeout=min(HTTP_TIMEOUT, 10),
            context=_SSL_CTX,
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
)


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
                    "spoolman_support",
                    "has_bypass",
                    "tool",
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
        gates.append({
            "gate": gate,
            "status": hh_status,
            "material": material,
            "color_hex": color,
            "temperature": temperature,
        })

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
    bypass_selected = selected_tool == -2
    if bypass_selected:
        # A selected bypass is stronger evidence than an omitted capability
        # field from an older Happy Hare build.
        has_bypass = True
    bypass = None
    if has_bypass is True:
        raw_filament_pos = mmu.get("filament_pos")
        try:
            filament_pos = (
                float(raw_filament_pos)
                if not isinstance(raw_filament_pos, bool)
                else None
            )
        except (TypeError, ValueError):
            filament_pos = None
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
        "spoolman_support": str(mmu.get("spoolman_support") or "").strip().lower(),
        "print_state": print_state,
        "printer_hostname": hostname,
        "has_bypass": has_bypass,
        "bypass": bypass,
    }


def upload_happy_hare_snapshot(token, physical_printer_id, snapshot):
    payload = {
        "physical_printer_id": physical_printer_id,
        "gate_count": snapshot["gate_count"],
        "snapshot_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gates": snapshot["gates"],
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


def _plugin_material_server_inventory(token):
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
    unique_exact = {
        (item.get("connection_ref"), item.get("print_host")): item
        for item in exact
    }
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


def send_printer_observations(token, observations, source_instance_id=""):
    """POST observed printer connection data. The backend records it raw; the
    plugin makes no physical-printer identity decisions."""
    if not token or not observations:
        return None, {}
    status, body = http_post_json(
        "/orcaslicer/printer-connections/observe",
        token,
        {
            "observations": observations,
            "source_instance_id": source_instance_id or None,
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
    """The loaded account's own filament presets (UI thread — reads preset_bundle).
    Keep is_user() presets, skip system/vendor and our [fh] ones. Configuration
    comes from Orca's Preset API instead of reopening the backing JSON file."""
    candidates = []
    managed_names = set()
    for entry in scan_local_fh_presets(user_filament_dir()).values():
        managed_names.add(os.path.basename(entry["path"])[:-len(".json")])
    try:
        filaments = orca.host.preset_bundle().filaments
        for i in range(filaments.size()):
            preset = filaments.preset(i)
            if not preset.is_user():
                continue
            name = preset.name or ""
            if "[fh]" in name or "@fh" in name or name in managed_names:
                continue
            if preset_id_from_bundle(getattr(preset, "bundle_id", "")) is not None:
                continue
            profile = preset_config_dict(preset, include_metadata=True)
            if profile:
                candidates.append({
                    "name": name,
                    "profile": profile,
                    "locator": _local_profile_locator(preset, "filament", name),
                })
    except Exception:
        pass
    return candidates


def _sync_preferences(token):
    """Read account sync preferences through the plugin-scoped endpoint."""
    defaults = {
        "available": False,
        "auto_import_local_presets": False,
        "sync_printer_endpoints": False,
        "allow_filament_presets_import": False,
        "allow_filament_presets_export": False,
        "allow_printer_profiles_import": False,
        "allow_printer_profiles_export": False,
        "allow_print_profiles_import": False,
        "allow_print_profiles_export": False,
    }
    status, body = http_get("/orcaslicer/sync-prefs", token=token)
    if status != 200:
        fh_log("sync-prefs HTTP %s -> privacy-safe defaults" % status)
        return defaults
    try:
        raw = json.loads(body.decode("utf-8")) or {}
        return dict(defaults, **{
            "available": True,
            "auto_import_local_presets": bool(raw.get("auto_import_local_presets")),
            "sync_printer_endpoints": bool(raw.get("sync_printer_endpoints")),
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


def _observations_for_sync(observations, share_endpoints=False):
    """Keep LAN addresses local unless the account explicitly opted in."""
    prepared = []
    for observation in observations or []:
        item = dict(observation)
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
# A local edit always wins over a remote bump so an OrcaSlicer change is never
# silently lost.
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
    status, body = http_get("/presets/%d/export/orcaslicer.json" % pid, token=token)
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
    return {"updated_at": remote_updated or "",
            "hash": local_entry["hash"],
            "name": local_entry["profile"].get("name") or ""}


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
            }
    return out


# --------------------------------------------------------------------------- #
# Automatic printer (machine) and print (process) profile sync remains one-way:
# profiles are read from OrcaSlicer and handed to FilamentHub, so the site knows
# which machine a spool, a gate or a recommendation belongs to. A user may also
# explicitly restore the profiles linked to one physical-printer card. That
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
                return "file:" + os.path.normcase(relative).replace("\\", "/")
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
    try:
        spec = PROFILE_KINDS[kind]
        bundle = orca.host.preset_bundle()
        collection = getattr(bundle, spec["collection"])
        seen_names = set()
        for i in range(collection.size()):
            preset = collection.preset(i)
            name = str(getattr(preset, "name", "") or "")
            if name in seen_names:
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
    return out, True


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
# The shell page — an Orca-themed toolbar (host CSS variables, like the fork's
# native FilamentHubPanel buttons) above a full-window iframe, plus two relays:
# catalog -> Python (import) and toolbar -> catalog (SPA navigation, no reload).
# --------------------------------------------------------------------------- #
PAGE = r"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  html, body { margin:0; height:100%; }
  body {
    display:flex; flex-direction:column;
    background:var(--orca-bg,#1e1e2e);
    font-family:var(--orca-font,sans-serif);
  }
  #bar {
    flex:0 0 auto; display:flex; align-items:center;
    padding:4px 10px; gap:2px;
    background:var(--orca-bg,#1e1e2e);
    border-bottom:1px solid var(--orca-border,#3c3c4c);
  }
  #left { margin-right:auto; display:flex; align-items:center; gap:8px; }
  #brand {
    appearance:none; padding:4px 10px; border-radius:4px;
    border:1px solid var(--orca-border,#3c3c4c); background:transparent;
    color:var(--orca-fg,#e0e0e0); font:inherit; font-size:12px; font-weight:600;
  }
  #brand:not(:disabled):hover {
    border-color:var(--orca-accent,#8b7cf8);
    background:color-mix(in srgb, var(--orca-accent,#8b7cf8) 12%, transparent);
  }
  #brand:disabled { border-color:transparent; opacity:1; }
  #logout {
    display:none; padding:2px 8px; font-size:11px;
    color:var(--orca-muted,#a0a0a0); border-color:var(--orca-border,#3c3c4c);
  }
  #bar button {
    appearance:none; background:transparent; cursor:pointer;
    border:1px solid transparent; border-radius:0;
    color:var(--orca-fg,#e0e0e0); font:inherit; font-size:12px; padding:4px 14px;
  }
  #bar button:hover { border-color:var(--orca-border,#3c3c4c); }
  #bar button.active {
    color:var(--orca-fg,#e0e0e0);
    border-color:var(--orca-accent,#8b7cf8);
    background:color-mix(in srgb, var(--orca-accent,#8b7cf8) 14%, transparent);
  }
  #content { position:relative; flex:1 1 auto; min-height:0; display:flex; }
  iframe { flex:1 1 auto; border:0; width:100%; display:block; visibility:hidden; }
  #service-status {
    position:absolute; inset:0; z-index:10;
    display:flex; align-items:center; justify-content:center;
    padding:24px; box-sizing:border-box;
    background:var(--orca-bg,#1e1e2e); color:var(--orca-fg,#e0e0e0);
    text-align:center;
  }
  #service-status-card { max-width:520px; }
  #service-status h2 { margin:14px 0 8px; font-size:20px; font-weight:600; }
  #service-status p {
    margin:0; color:var(--orca-muted,#a0a0a0); font-size:13px; line-height:1.55;
  }
  #service-spinner {
    width:28px; height:28px; margin:0 auto;
    border:3px solid var(--orca-border,#3c3c4c);
    border-top-color:var(--orca-accent,#8b7cf8); border-radius:50%;
    animation:fh-spin .9s linear infinite;
  }
  #service-retry {
    display:none; margin:18px auto 0; padding:7px 18px;
    border:1px solid var(--orca-accent,#8b7cf8); border-radius:6px;
    background:transparent; color:var(--orca-accent,#8b7cf8);
    font:inherit; font-size:13px; cursor:pointer;
  }
  #service-retry:hover { background:rgba(139,124,248,.1); }
  #service-retry:focus-visible {
    outline:2px solid var(--orca-accent,#8b7cf8); outline-offset:3px;
  }
  @keyframes fh-spin { to { transform:rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) {
    #service-spinner { animation:none; }
  }
</style></head>
<body>
  <div id="bar">
    <span id="left">
      <button id="brand" type="button">Sign in</button>
      <button id="logout" title="Sign out">Sign out</button>
    </span>
    <button id="catalog" data-path="/" class="active">Catalog</button>
    <button id="profile" data-path="/profile">Profile</button>
    <button id="wiki" data-path="/wiki">Wiki</button>
    <button id="sync" title="Sync your FilamentHub presets with OrcaSlicer">Sync</button>
    <button id="recover" title="Find your local OrcaSlicer filament presets and import the ones you pick as drafts">Recover</button>
    <button id="diag" __DIAG_HIDDEN__ title="Copy the plugin log to the clipboard">Log</button>
  </div>
  <div id="content">
    <div id="service-status" role="status" aria-live="polite">
      <div id="service-status-card">
        <div id="service-spinner"></div>
        <h2 id="service-status-title">Connecting to FilamentHub...</h2>
        <p id="service-status-message">Please wait while the catalog is loaded.</p>
        <button id="service-retry" type="button">Try again</button>
      </div>
    </div>
    <iframe id="fh" src="__EMBED_URL__" title="FilamentHub catalog"
      sandbox="allow-scripts allow-same-origin allow-forms allow-downloads"
      allow="clipboard-write"></iframe>
  </div>
<script>
'use strict';
var SITE_ORIGIN = '__SITE_ORIGIN__';
var EMBED_URL = '__EMBED_URL__';
var OAUTH_STATUS_PATH = '__OAUTH_STATUS_PATH__';
var SYNC_STATUS_PATH = '__SYNC_STATUS_PATH__';
var RECOVER_STATUS_PATH = '__RECOVER_STATUS_PATH__';
var SLICE_PARSE_PATH = '__SLICE_PARSE_PATH__';
var SLICE_ALIVE_PATH = '__SLICE_ALIVE_PATH__';
var LOG_PATH = '__LOG_PATH__';
var frame = document.getElementById('fh');
var wasLoggedIn = false;
var hostPush = false;
var oauthPollTimer = null;
var oauthDeadline = 0;
var catalogReady = false;
var catalogReadyTimer = null;
var UI_COPY = __UI_COPY__;
var hostLanguage = '__HOST_UI_LANGUAGE__';
function normalizeUiLocale(value) {
  var token = String(value || '').replace(/-/g, '_');
  var lowered = token.toLowerCase();
  var aliases = { zh: 'zh_CN', zh_hans: 'zh_CN', zh_hans_cn: 'zh_CN',
                  zh_hant: 'zh_TW', zh_hant_tw: 'zh_TW' };
  if (aliases[lowered]) return aliases[lowered];
  var exact = Object.keys(UI_COPY).find(function(key) {
    return key.toLowerCase() === lowered;
  });
  if (exact) return exact;
  var base = lowered.split('_', 1)[0];
  return Object.prototype.hasOwnProperty.call(UI_COPY, base) ? base : 'en';
}
function resolveUiCopy(value) {
  var locale = normalizeUiLocale(value);
  var base = locale.split('_', 1)[0];
  return Object.assign({}, UI_COPY.en || {}, UI_COPY[base] || {}, UI_COPY[locale] || {});
}
var uiLocale = normalizeUiLocale(hostLanguage || navigator.language || 'en');
var uiCopy = resolveUiCopy(uiLocale);
document.documentElement.lang = uiLocale;

function applyShellCopy() {
  var setText = function (id, text) {
    var element = document.getElementById(id);
    if (element && typeof text === 'string' && text.length > 0) {
      element.textContent = text;
    }
  };
  var setTitle = function (id, text) {
    var element = document.getElementById(id);
    if (element && typeof text === 'string' && text.length > 0) {
      element.title = text;
    }
  };
  setText('brand', uiCopy.signIn);
  setText('logout', uiCopy.signOut);
  setText('catalog', uiCopy.catalog);
  setText('profile', uiCopy.profile);
  setText('wiki', uiCopy.wiki);
  setText('sync', uiCopy.sync);
  setText('recover', uiCopy.recover);
  setText('diag', uiCopy.log);
  setTitle('logout', uiCopy.signOut);
  setTitle('sync', uiCopy.syncTitle);
  setTitle('recover', uiCopy.recoverTitle);
  setTitle('diag', uiCopy.logTitle);
  if (typeof uiCopy.catalogTitle === 'string' && uiCopy.catalogTitle.length > 0) {
    frame.title = uiCopy.catalogTitle;
  }
}
applyShellCopy();


function showCatalogStatus(mode) {
  var unavailable = mode === 'unavailable';
  document.getElementById('service-status').style.display = 'flex';
  document.getElementById('service-spinner').style.display = unavailable ? 'none' : 'block';
  document.getElementById('service-status-title').textContent = unavailable
    ? uiCopy.unavailableTitle
    : uiCopy.connectTitle;
  document.getElementById('service-status-message').textContent = unavailable
    ? uiCopy.unavailableMessage
    : uiCopy.connectMessage;
  document.getElementById('service-retry').textContent = uiCopy.retry;
  document.getElementById('service-retry').style.display = unavailable ? 'block' : 'none';
}
function waitForCatalog() {
  catalogReady = false;
  frame.style.visibility = 'hidden';
  showCatalogStatus('connecting');
  if (catalogReadyTimer) clearTimeout(catalogReadyTimer);
  catalogReadyTimer = setTimeout(function () {
    if (!catalogReady) showCatalogStatus('unavailable');
  }, 10000);
}
function markCatalogReady() {
  catalogReady = true;
  if (catalogReadyTimer) {
    clearTimeout(catalogReadyTimer);
    catalogReadyTimer = null;
  }
  document.getElementById('service-status').style.display = 'none';
  frame.style.visibility = 'visible';
}
document.getElementById('service-retry').addEventListener('click', function () {
  waitForCatalog();
  var separator = EMBED_URL.indexOf('?') === -1 ? '?' : '&';
  frame.src = EMBED_URL + separator + 'fh_retry=' + Date.now();
});
waitForCatalog();

// Auth-only toolbar controls: Profile and Sync only make sense when signed in.
// When signed out, the "FilamentHub" brand label doubles as a sign-in trigger.
function setAuthControls(loggedIn) {
  var profileBtn = document.querySelector('#bar button[data-path="/profile"]');
  if (profileBtn) profileBtn.style.display = loggedIn ? '' : 'none';
  document.getElementById('sync').style.display = loggedIn ? 'inline-block' : 'none';
  var recoverBtn = document.getElementById('recover');
  if (recoverBtn) recoverBtn.style.display = loggedIn ? 'inline-block' : 'none';
  var brand = document.getElementById('brand');
  brand.disabled = loggedIn;
  brand.style.cursor = loggedIn ? 'default' : 'pointer';
  brand.title = loggedIn ? '' : (
    typeof uiCopy.signInTitle === 'string' && uiCopy.signInTitle.length > 0
      ? uiCopy.signInTitle
      : brand.textContent
  );
  // Keep the signed-out action readable even when the host accent is too dark
  // for the toolbar background.
  brand.style.color = 'var(--orca-fg,#e0e0e0)';
}
// Re-open the currently active tab inside the catalog (used right after sign-in).
function navigateActive() {
  var active = document.querySelector('#bar button[data-path].active') ||
               document.querySelector('#bar button[data-path]');
  if (!active) return;
  try {
    frame.contentWindow.postMessage(
      { source: 'filamenthub-plugin', type: 'navigate', path: active.getAttribute('data-path') },
      SITE_ORIGIN);
  } catch (e) { /* iframe not ready */ }
}
function sendPluginCapabilities() {
  try {
    frame.contentWindow.postMessage(
      { source: 'filamenthub-plugin', type: 'plugin-capabilities',
        pluginVersion: '__PLUGIN_VERSION__',
        capabilities: ['printer-bundle-install', 'printer-bundle-result-v1',
                       'bambu-lan-bridge', 'profile-sync', 'profile-sync-scopes-v1',
                       'bambu-material-write', 'happy-hare-moonraker', 'open-external'] },
      SITE_ORIGIN);
  } catch (e) { /* iframe not ready */ }
}
setAuthControls(false);  // hidden until the catalog reports a signed-in state

// Catalog -> shell. auth-state updates the toolbar label; open-oauth runs the
// provider sign-in in the real browser and waits for the session over loopback;
// everything else relays to Python.
window.addEventListener('message', function (event) {
  var data = event.data;
  if (event.source !== frame.contentWindow || event.origin !== SITE_ORIGIN) return;
  if (!data || data.source !== 'filamenthub-plugin') return;
  markCatalogReady();
  if (data.type === 'plugin-capabilities-request') {
    sendPluginCapabilities();
    return;
  }
  if (data.type === 'auth-state') {
    // label present = signed in: show the username + a sign-out button, and the
    // auth-only controls (Profile, Sync). On a fresh sign-in, return the catalog
    // to the active tab so the user isn't dropped on the app's default page.
    var loggedIn = !!data.label;
    document.getElementById('brand').textContent = data.label || uiCopy.signIn || 'Sign in';
    document.getElementById('logout').style.display = loggedIn ? 'inline-block' : 'none';
    setAuthControls(loggedIn);
    if (loggedIn && !wasLoggedIn) navigateActive();
    wasLoggedIn = loggedIn;
    return;
  }
  if (data.type === 'parse-slice') {
    // The catalog cannot read a file on disk; Python can, and sends it to the
    // same parser a manual upload goes through.
    try { orca.postMessage(data); } catch (e) { /* bridge not ready */ }
    startSlicePolling();
    return;
  }
  if (data.type === 'check-slices') {
    try { orca.postMessage(data); } catch (e) { /* bridge not ready */ }
    startSliceKeysPolling();
    return;
  }
  if (data.type === 'open-oauth') {
    // Google/Yandex refuse their consent pages inside this WebView. Hand the
    // request to Python (opens the system browser) and start polling loopback
    // for the session the external browser will deliver back.
    try { orca.postMessage(data); } catch (e) { /* bridge not ready */ }
    startOAuthPolling();
    return;
  }
  if (data.type === 'configure-bambu') {
    showBambuOverlay(data);
    return;
  }
  if (data.type === 'sync' || data.type === 'profile-changed' ||
      data.type === 'install-printer-bundle') {
    startSyncPolling(
      typeof data.operationId === 'string' ? data.operationId :
      typeof data.requestId === 'string' ? data.requestId : ''
    );
  }
  try { orca.postMessage(data); } catch (e) { /* bridge not ready */ }
});

// Poll the loopback status endpoint (same origin as this shell) for the session
// the external browser posts back after the provider flow completes.
function stopOAuthPolling() {
  if (oauthPollTimer) { clearTimeout(oauthPollTimer); oauthPollTimer = null; }
}
function startOAuthPolling() {
  stopOAuthPolling();
  oauthDeadline = Date.now() + 5 * 60 * 1000;  // give up after 5 minutes
  pollOAuthOnce();
}
function pollOAuthOnce() {
  if (Date.now() > oauthDeadline) { stopOAuthPolling(); hideOAuthOverlay(); return; }
  fetch(OAUTH_STATUS_PATH, { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (st) {
      if (st.stage === 'delivered') {
        stopOAuthPolling();
        hideOAuthOverlay();
        try {
          frame.contentWindow.postMessage(
            { source: 'filamenthub-plugin', type: 'auth-restore',
              accessToken: st.accessToken || '', refreshToken: st.refreshToken || '' },
            SITE_ORIGIN);
        } catch (e) { /* iframe not ready */ }
        return;
      }
      // Show the link proactively: even when the browser reports opened, we can't
      // be sure it actually surfaced (embedded-Python quirks), so the user always
      // has a manual path. Loopback delivery is identical either way.
      if (st.stage === 'awaiting' && st.startUrl) {
        showOAuthOverlay(st.startUrl);
      }
      oauthPollTimer = setTimeout(pollOAuthOnce, 1500);
    })
    .catch(function () { oauthPollTimer = setTimeout(pollOAuthOnce, 2000); });
}
function hideOAuthOverlay() {
  var ov = document.getElementById('oauth-overlay');
  if (ov) ov.remove();
}
function showOAuthOverlay(url) {
  var existing = document.getElementById('oauth-url');
  if (existing) { existing.value = url; return; }
  var ov = document.createElement('div');
  ov.id = 'oauth-overlay';
  ov.style.cssText = 'position:fixed;inset:0;z-index:2147483647;display:flex;' +
    'align-items:center;justify-content:center;background:rgba(0,0,0,0.7);';
  var box = document.createElement('div');
  box.style.cssText = 'max-width:520px;margin:16px;padding:20px;border-radius:10px;' +
    'background:var(--orca-bg,#1e1e2e);color:var(--orca-fg,#e0e0e0);' +
    'border:1px solid var(--orca-border,#3c3c4c);font-size:13px;';
  var title = document.createElement('div');
  title.textContent = uiCopy.oauthTitle;
  title.style.cssText = 'font-weight:600;margin-bottom:8px;';
  var hint = document.createElement('div');
  hint.textContent = uiCopy.oauthHint;
  hint.style.cssText = 'margin-bottom:10px;color:var(--orca-muted,#a0a0a0);';
  var input = document.createElement('input');
  input.id = 'oauth-url';
  input.readOnly = true;
  input.value = url;
  input.style.cssText = 'width:100%;box-sizing:border-box;padding:8px;margin-bottom:10px;' +
    'background:rgba(255,255,255,0.06);color:inherit;' +
    'border:1px solid var(--orca-border,#3c3c4c);border-radius:6px;';
  var row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;';
  var copy = document.createElement('button');
  copy.textContent = uiCopy.copyLink;
  copy.style.cssText = 'padding:6px 14px;border-radius:6px;cursor:pointer;' +
    'border:1px solid var(--orca-accent,#8b7cf8);background:transparent;' +
    'color:var(--orca-accent,#8b7cf8);font:inherit;';
  copy.addEventListener('click', function () {
    input.focus();
    input.select();
    var done = function () { copy.textContent = uiCopy.copied; };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(input.value).then(done, function () {
          try { document.execCommand('copy'); done(); } catch (e) {}
        });
      } else { document.execCommand('copy'); done(); }
    } catch (e) {}
  });
  var close = document.createElement('button');
  close.textContent = uiCopy.cancel;
  close.style.cssText = 'padding:6px 14px;border-radius:6px;cursor:pointer;' +
    'border:1px solid var(--orca-border,#3c3c4c);background:transparent;' +
    'color:var(--orca-fg,#e0e0e0);font:inherit;';
  close.addEventListener('click', function () { stopOAuthPolling(); hideOAuthOverlay(); });
  row.appendChild(copy);
  row.appendChild(close);
  box.appendChild(title);
  box.appendChild(hint);
  box.appendChild(input);
  box.appendChild(row);
  ov.appendChild(box);
  document.body.appendChild(ov);
}

function hideBambuOverlay() {
  var overlay = document.getElementById('bambu-overlay');
  if (overlay) overlay.remove();
}
function showBambuOverlay(binding) {
  hideBambuOverlay();
  var printerId = Number(binding.physicalPrinterId);
  var systemId = Number(binding.materialSystemId);
  var pairingCode = typeof binding.pairingCode === 'string' ? binding.pairingCode : '';
  if (!Number.isInteger(printerId) || printerId < 1 ||
      !Number.isInteger(systemId) || systemId < 1 || !pairingCode) return;
  var overlay = document.createElement('div');
  overlay.id = 'bambu-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483647;display:flex;' +
    'align-items:center;justify-content:center;background:rgba(0,0,0,0.72);';
  var box = document.createElement('form');
  box.style.cssText = 'width:min(520px,calc(100% - 32px));padding:22px;box-sizing:border-box;' +
    'border-radius:12px;background:var(--orca-bg,#1e1e2e);color:var(--orca-fg,#e0e0e0);' +
    'border:1px solid var(--orca-border,#3c3c4c);font-size:13px;';
  var title = document.createElement('div');
  title.textContent = uiCopy.bambuTitle + (binding.printerName ? ' · ' + binding.printerName : '');
  title.style.cssText = 'font-weight:650;font-size:16px;margin-bottom:7px;';
  var hint = document.createElement('div');
  hint.textContent = uiCopy.bambuHint;
  hint.style.cssText = 'color:var(--orca-muted,#a0a0a0);line-height:1.45;margin-bottom:16px;';
  function field(labelText, type, placeholder, required) {
    var wrap = document.createElement('label');
    wrap.style.cssText = 'display:block;margin-top:11px;color:var(--orca-muted,#a0a0a0);';
    var label = document.createElement('span');
    label.textContent = labelText;
    label.style.cssText = 'display:block;margin-bottom:5px;';
    var input = document.createElement('input');
    input.type = type;
    input.placeholder = placeholder || '';
    input.required = !!required;
    input.autocomplete = 'off';
    input.style.cssText = 'width:100%;box-sizing:border-box;padding:9px 10px;border-radius:7px;' +
      'background:rgba(255,255,255,.06);color:inherit;' +
      'border:1px solid var(--orca-border,#3c3c4c);font:inherit;';
    wrap.appendChild(label);
    wrap.appendChild(input);
    box.appendChild(wrap);
    return input;
  }
  box.appendChild(title);
  box.appendChild(hint);
  var host = field(uiCopy.bambuAddress, 'text', uiCopy.bambuAddressPlaceholder, true);
  var code = field(uiCopy.bambuCode, 'password', '', true);
  var serial = field(uiCopy.bambuSerial, 'text', uiCopy.bambuSerialHint, false);
  var local = document.createElement('div');
  local.textContent = uiCopy.bambuLocalOnly;
  local.style.cssText = 'margin-top:12px;color:var(--orca-muted,#a0a0a0);font-size:11px;line-height:1.45;';
  box.appendChild(local);
  var row = document.createElement('div');
  row.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;margin-top:18px;';
  function button(text, accent) {
    var element = document.createElement('button');
    element.type = 'button';
    element.textContent = text;
    element.style.cssText = 'padding:7px 14px;border-radius:7px;cursor:pointer;font:inherit;' +
      'border:1px solid ' + (accent ? 'var(--orca-accent,#8b7cf8)' : 'var(--orca-border,#3c3c4c)') + ';' +
      'background:' + (accent ? 'var(--orca-accent,#8b7cf8)' : 'transparent') + ';' +
      'color:' + (accent ? '#fff' : 'var(--orca-fg,#e0e0e0)') + ';';
    return element;
  }
  var remove = button(uiCopy.bambuRemove, false);
  remove.style.marginRight = 'auto';
  remove.addEventListener('click', function () {
    try {
      orca.postMessage({ source:'filamenthub-plugin', type:'remove-bambu-local',
        physicalPrinterId:printerId });
      startSyncPolling();
    } catch (e) {}
    hideBambuOverlay();
  });
  var cancel = button(uiCopy.cancel, false);
  cancel.addEventListener('click', hideBambuOverlay);
  var save = button(uiCopy.bambuSave, true);
  save.type = 'submit';
  row.appendChild(remove);
  row.appendChild(cancel);
  row.appendChild(save);
  box.appendChild(row);
  box.addEventListener('submit', function (event) {
    event.preventDefault();
    if (!host.value.trim() || !code.value.trim()) return;
    try {
      orca.postMessage({ source:'filamenthub-plugin', type:'configure-bambu-local',
        physicalPrinterId:printerId, materialSystemId:systemId,
        host:host.value.trim(), accessCode:code.value.trim(), serial:serial.value.trim(),
        pairingCode:pairingCode });
      startSyncPolling();
    } catch (e) {}
    code.value = '';
    hideBambuOverlay();
  });
  overlay.addEventListener('click', function (event) {
    if (event.target === overlay) hideBambuOverlay();
  });
  overlay.appendChild(box);
  document.body.appendChild(overlay);
  host.focus();
}

// Toolbar -> catalog: SPA navigation inside the iframe (no page reload).
var buttons = Array.prototype.slice.call(document.querySelectorAll('#bar button[data-path]'));
buttons.forEach(function (btn) {
  btn.addEventListener('click', function () {
    buttons.forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
    try {
      frame.contentWindow.postMessage(
        { source: 'filamenthub-plugin', type: 'navigate', path: btn.getAttribute('data-path') },
        SITE_ORIGIN);
    } catch (e) { /* iframe not ready */ }
  });
});

// Brand label doubles as a sign-in trigger when signed out — opens the catalog's
// login modal (?auth=login). When signed in it just shows the username.
document.getElementById('brand').addEventListener('click', function () {
  if (wasLoggedIn) return;
  try {
    frame.contentWindow.postMessage(
      { source: 'filamenthub-plugin', type: 'navigate', path: '/?auth=login' }, SITE_ORIGIN);
  } catch (e) { /* iframe not ready */ }
});

// Python writes the sync summary to loopback; poll it and relay a toast to the embed.
var syncPollTimer = null;
var syncDeadline = 0;
var syncExpectedOperationId = '';
function stopSyncPolling() {
  if (syncPollTimer) { clearTimeout(syncPollTimer); syncPollTimer = null; }
}
function startSyncPolling(operationId) {
  if (hostPush) return;
  stopSyncPolling();
  syncExpectedOperationId = operationId || '';
  syncDeadline = Date.now() + 30 * 1000;
  pollSyncOnce();
}
function pollSyncOnce() {
  if (Date.now() > syncDeadline) { stopSyncPolling(); return; }
  fetch(SYNC_STATUS_PATH, { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (st) {
      if (st.text) {
        var resultId = st.operationId || st.requestId || '';
        if (syncExpectedOperationId && resultId !== syncExpectedOperationId) {
          syncPollTimer = setTimeout(pollSyncOnce, 500);
          return;
        }
        stopSyncPolling();
        try {
          st.source = 'filamenthub-plugin';
          st.type = st.resultType || 'sync-result';
          frame.contentWindow.postMessage(st, SITE_ORIGIN);
        } catch (e) { /* iframe not ready */ }
        return;
      }
      syncPollTimer = setTimeout(pollSyncOnce, 1000);
    })
    .catch(function () { syncPollTimer = setTimeout(pollSyncOnce, 1500); });
}
document.getElementById('sync').addEventListener('click', function () {
  var operationId = 'sync-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  try { orca.postMessage({ source: 'filamenthub-plugin', type: 'sync',
    scope: 'all', operationId: operationId }); } catch (e) { /* bridge not ready */ }
  startSyncPolling(operationId);
});

// Recover: Python scans local presets and writes the list to loopback; poll it and
// hand the list to the embed, which shows a checkbox picker and posts back the choice.
var recoverPollTimer = null;
var recoverDeadline = 0;
function stopRecoverPolling() {
  if (recoverPollTimer) { clearTimeout(recoverPollTimer); recoverPollTimer = null; }
}
function startRecoverPolling() {
  if (hostPush) return;
  stopRecoverPolling();
  recoverDeadline = Date.now() + 30 * 1000;
  pollRecoverOnce();
}
function pollRecoverOnce() {
  if (Date.now() > recoverDeadline) { stopRecoverPolling(); return; }
  fetch(RECOVER_STATUS_PATH, { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (st) {
      if (st.ready) {
        stopRecoverPolling();
        try {
          frame.contentWindow.postMessage(
            { source: 'filamenthub-plugin', type: 'recover-list', items: st.items || [] }, SITE_ORIGIN);
        } catch (e) { /* iframe not ready */ }
        return;
      }
      recoverPollTimer = setTimeout(pollRecoverOnce, 800);
    })
    .catch(function () { recoverPollTimer = setTimeout(pollRecoverOnce, 1200); });
}
document.getElementById('recover').addEventListener('click', function () {
  try { orca.postMessage({ source: 'filamenthub-plugin', type: 'recover' }); } catch (e) { /* bridge not ready */ }
  startRecoverPolling();
});

var slicePollTimer = null;
var sliceDeadline = 0;
function stopSlicePolling() {
  if (slicePollTimer) { clearTimeout(slicePollTimer); slicePollTimer = null; }
}
function startSlicePolling() {
  if (hostPush) return;
  stopSlicePolling();
  // A big slice takes a while to travel and parse.
  sliceDeadline = Date.now() + 180 * 1000;
  pollSliceOnce();
}
function pollSliceOnce() {
  if (Date.now() > sliceDeadline) {
    stopSlicePolling();
    relaySliceResult({ error: 'timeout' });
    return;
  }
  fetch(SLICE_PARSE_PATH, { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (st) {
      if (st.ready) {
        stopSlicePolling();
        relaySliceResult(st.result || { error: 'empty' });
        return;
      }
      slicePollTimer = setTimeout(pollSliceOnce, 800);
    })
    .catch(function () { slicePollTimer = setTimeout(pollSliceOnce, 1200); });
}
var sliceKeysTimer = null;
var sliceKeysDeadline = 0;
function startSliceKeysPolling() {
  if (hostPush) return;
  if (sliceKeysTimer) { clearTimeout(sliceKeysTimer); sliceKeysTimer = null; }
  sliceKeysDeadline = Date.now() + 20 * 1000;
  pollSliceKeysOnce();
}
function pollSliceKeysOnce() {
  if (Date.now() > sliceKeysDeadline) { sliceKeysTimer = null; return; }
  fetch(SLICE_ALIVE_PATH, { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (st) {
      if (st.ready) {
        sliceKeysTimer = null;
        try {
          frame.contentWindow.postMessage(
            { source: 'filamenthub-plugin', type: 'slices-alive',
              keys: st.alive || [], hook: st.hook || null },
            SITE_ORIGIN);
        } catch (e) { /* iframe not ready */ }
        return;
      }
      sliceKeysTimer = setTimeout(pollSliceKeysOnce, 500);
    })
    .catch(function () { sliceKeysTimer = setTimeout(pollSliceKeysOnce, 800); });
}
function relaySliceResult(result) {
  try {
    frame.contentWindow.postMessage(
      { source: 'filamenthub-plugin', type: 'parsed-slice', result: result }, SITE_ORIGIN);
  } catch (e) { /* iframe not ready */ }
}

function relaySyncResult(data) {
  try {
    frame.contentWindow.postMessage(
      {
        source: 'filamenthub-plugin',
        type: 'sync-result',
        text: data.text || '',
        draftCount: Number(data.draftCount) || 0,
        operationId: data.operationId || '',
        scope: data.scope || 'all',
        status: data.status || 'success',
        contours: Array.isArray(data.contours) ? data.contours : []
      }, SITE_ORIGIN);
  } catch (e) { /* iframe not ready */ }
}
function relayNote(text, status) {
  try {
    frame.contentWindow.postMessage(
      { source: 'filamenthub-plugin', type: 'plugin-notice',
        text: text || '', status: status || 'info' }, SITE_ORIGIN);
  } catch (e) { /* iframe not ready */ }
}
function copyDiagnostics(text) {
  if (!text) {
    relayNote(uiCopy.logEmpty);
    return;
  }
  navigator.clipboard.writeText(text).then(function () {
    relayNote(uiCopy.logCopied);
  }, function () {
    relayNote(uiCopy.logCopyFailed);
  });
}
// The host handle can push worker results directly into this page. Keep the
// loopback status endpoints only as a compatibility fallback for older builds.
try {
  orca.onMessage(function (data) {
    if (!data || data.source !== 'filamenthub-host') return;
    hostPush = true;
    if (data.type === 'transport') return;
    if (data.type === 'sync-result') {
      stopSyncPolling();
      relaySyncResult(data);
    } else if (data.type === 'plugin-notice') {
      relayNote(data.text || '', data.status || 'info');
    } else if (data.type === 'printer-bundle-result') {
      try {
        frame.contentWindow.postMessage(
          { source: 'filamenthub-plugin', type: 'printer-bundle-result',
            requestId: data.requestId || '', text: data.text || '',
            status: data.status || 'success' }, SITE_ORIGIN);
      } catch (e) { /* iframe not ready */ }
    } else if (data.type === 'recover-list') {
      stopRecoverPolling();
      try {
        frame.contentWindow.postMessage(
          { source: 'filamenthub-plugin', type: 'recover-list', items: data.items || [] },
          SITE_ORIGIN);
      } catch (e) { /* iframe not ready */ }
    } else if (data.type === 'parsed-slice') {
      stopSlicePolling();
      relaySliceResult(data.result || { error: 'empty' });
    } else if (data.type === 'slices-alive') {
      if (sliceKeysTimer) { clearTimeout(sliceKeysTimer); sliceKeysTimer = null; }
      try {
        frame.contentWindow.postMessage(
          { source: 'filamenthub-plugin', type: 'slices-alive',
            keys: data.keys || [], hook: data.hook || null },
          SITE_ORIGIN);
      } catch (e) { /* iframe not ready */ }
    } else if (data.type === 'happy-hare-result') {
      try {
        frame.contentWindow.postMessage(
          { source: 'filamenthub-plugin', type: 'happy-hare-result',
            requestId: data.requestId || '', result: data.result || {} },
          SITE_ORIGIN);
      } catch (e) { /* iframe not ready */ }
    } else if (data.type === 'bambu-material-result') {
      try {
        frame.contentWindow.postMessage(
          { source: 'filamenthub-plugin', type: 'bambu-material-result',
            requestId: data.requestId || '', result: data.result || {} },
          SITE_ORIGIN);
      } catch (e) { /* iframe not ready */ }
    } else if (data.type === 'diagnostics') {
      copyDiagnostics(data.text || '');
    }
  });
  orca.postMessage({ source: 'filamenthub-plugin', type: 'host-ready' });
} catch (e) { /* old bridge: loopback polling remains available */ }
document.getElementById('diag').addEventListener('click', function () {
  if (hostPush) {
    try {
      orca.postMessage({ source: 'filamenthub-plugin', type: 'read-diagnostics' });
      return;
    } catch (e) { /* use the loopback fallback below */ }
  }
  fetch(LOG_PATH, { cache: 'no-store' })
    .then(function (r) { return r.text(); })
    .then(copyDiagnostics)
    .catch(function () { relayNote(uiCopy.logReadFailed); });
});

// Sign out: tell the catalog to log out; it clears the session and reports back
// (auth-state with no label), which hides this button again.
document.getElementById('logout').addEventListener('click', function () {
  try {
    frame.contentWindow.postMessage(
      { source: 'filamenthub-plugin', type: 'do-logout' }, SITE_ORIGIN);
  } catch (e) { /* iframe not ready */ }
});
</script>
</body>
</html>
""".replace("__SITE_ORIGIN__", SITE_ORIGIN).replace(
    "__PLUGIN_VERSION__", PLUGIN_VERSION).replace(
    "__UI_COPY__", json.dumps(UI_COPY, ensure_ascii=False).replace("</", "<\\/")).replace(
    "__OAUTH_STATUS_PATH__", SHELL_SERVER.status_path()).replace(
    "__SYNC_STATUS_PATH__", SHELL_SERVER.sync_status_path()).replace(
    "__RECOVER_STATUS_PATH__", SHELL_SERVER.recover_status_path()).replace(
    "__SLICE_PARSE_PATH__", SHELL_SERVER.slice_parse_path()).replace(
    "__SLICE_ALIVE_PATH__", SHELL_SERVER.slice_alive_path()).replace(
    "__LOG_PATH__", SHELL_SERVER.log_path()).replace(
    "__DIAG_HIDDEN__", "" if SHOW_DIAGNOSTICS else "hidden")


def render_page():
    language = refresh_ui_language()
    return PAGE.replace("__HOST_UI_LANGUAGE__", language).replace(
        "__EMBED_URL__", localized_embed_url(language))


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
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except ValueError:
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
        "filament_id": str(tray.get("tray_info_idx") or "").strip() or None,
        "setting_id": str(tray.get("setting_id") or "").strip() or None,
        "nozzle_temp_min": _bambu_int(tray.get("nozzle_temp_min")),
        "nozzle_temp_max": _bambu_int(tray.get("nozzle_temp_max")),
        # A zeroed uuid is how an empty or non-Bambu tray reports "no tag".
        "provider_uid": uid if uid.strip("0") else None,
    }


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
    raw = socket.socket(family, socktype, proto)
    raw.settimeout(timeout)
    try:
        raw.connect(sockaddr)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context.wrap_socket(raw, server_hostname=None)
    except Exception:
        raw.close()
        raise


def read_bambu_lan_snapshot(config, timeout=BAMBU_MQTT_TIMEOUT):
    """Read one full-ish Bambu MQTT report and disconnect.

    The access code is used only for this local TLS connection. The returned
    payload deliberately contains no address or credential.
    """
    host = config.get("host") or ""
    access_code = config.get("access_code") or ""
    serial = (config.get("serial") or "").strip()
    if not access_code:
        raise ValueError("missing Bambu access code")
    deadline = time.monotonic() + timeout
    sock = _open_bambu_mqtt(host, access_code, timeout)
    try:
        variable = _mqtt_field(b"MQTT") + bytes([4, 0xC2]) + struct.pack("!H", 30)
        client_id = ("fhub-" + secrets.token_hex(6)).encode("ascii")
        connection = (
            variable
            + _mqtt_field(client_id)
            + _mqtt_field(b"bblp")
            + _mqtt_field(access_code.encode("utf-8"))
        )
        sock.sendall(b"\x10" + _mqtt_len(len(connection)) + connection)
        header, connack = _mqtt_read_packet(sock, deadline)
        if (header & 0xF0) != 0x20 or len(connack) < 2 or connack[1] != 0:
            raise PermissionError("Bambu MQTT authentication rejected")

        report_topic = (
            "device/%s/report" % serial if serial else "device/+/report"
        ).encode("utf-8")
        subscribe = struct.pack("!H", 1) + _mqtt_field(report_topic) + b"\x00"
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
            sock.sendall(b"\x30" + _mqtt_len(len(publish)) + publish)

        if serial:
            request_full_snapshot(serial)

        fallback = None
        while time.monotonic() < deadline:
            header, packet = _mqtt_read_packet(sock, deadline)
            packet_type = header & 0xF0
            if packet_type == 0xC0:
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


def _publish_bambu_json(config, serial, payload, timeout=BAMBU_MQTT_TIMEOUT):
    """Publish one allowlisted local Bambu command over a short TLS session."""
    access_code = config.get("access_code") or ""
    if not access_code or not re.fullmatch(r"[A-Za-z0-9._-]{4,80}", serial or ""):
        raise ValueError("invalid Bambu command context")
    deadline = time.monotonic() + timeout
    sock = _open_bambu_mqtt(config.get("host") or "", access_code, timeout)
    try:
        variable = _mqtt_field(b"MQTT") + bytes([4, 0xC2]) + struct.pack("!H", 30)
        client_id = ("fhub-" + secrets.token_hex(6)).encode("ascii")
        connection = (
            variable
            + _mqtt_field(client_id)
            + _mqtt_field(b"bblp")
            + _mqtt_field(access_code.encode("utf-8"))
        )
        sock.sendall(b"\x10" + _mqtt_len(len(connection)) + connection)
        header, connack = _mqtt_read_packet(sock, deadline)
        if (header & 0xF0) != 0x20 or len(connack) < 2 or connack[1] != 0:
            raise PermissionError("Bambu MQTT authentication rejected")
        topic = ("device/%s/request" % serial).encode("utf-8")
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        publish = _mqtt_field(topic) + body
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
):
    """Apply non-RFID material metadata and prove the resulting printer state."""
    serial, report = read_bambu_lan_snapshot(config, timeout=timeout)
    expected_serial = str(config.get("serial") or "").strip()
    if expected_serial and serial != expected_serial:
        return {"ok": False, "code": "printer_changed", "report": report}
    state = str(report.get("gcode_state") or "").strip().upper()
    if state not in {"IDLE", "FINISH", "FAILED"}:
        return {"ok": False, "code": "printer_busy", "report": report}

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
            _publish_bambu_json(
                config,
                serial,
                _bambu_material_command(locator, target),
                timeout=timeout,
            )
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
        return float(value)
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
        slots.append(
            {
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
        )
    return {
        "material_system_id": config["material_system_id"],
        "provider": "bambu",
        "transport": "orca_plugin_lan",
        "source_instance_id": source_instance_id,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "printer": printer,
        "slots": slots,
        "slot_topology_complete": feed is not None,
    }


def _persist_discovered_bambu_serial(physical_printer_id, serial):
    if not serial:
        return
    payload = load_bambu_config()
    changed = False
    for item in payload["printers"]:
        if item["physical_printer_id"] == physical_printer_id and not item.get("serial"):
            item["serial"] = serial[:80]
            changed = True
    if changed:
        save_bambu_config(payload)


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


class BambuBridgeRuntime:
    """One bounded daemon serializes all configured local Bambu observations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._restart_requested = False
        self._last_snapshot_digest = {}
        self._last_snapshot_at = {}
        self._last_heartbeat_at = {}
        self._failure_count = {}
        self._retry_at = {}

    def _start_locked(self):
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="filamenthub-bambu-bridge",
            daemon=True,
        )
        self._thread.start()

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

    def _run(self):
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
                    serial, report = read_bambu_lan_snapshot(config)
                    snapshot = build_bambu_bridge_snapshot(
                        config, local["source_instance_id"], report
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
                        status, _, retry_after = http_post_bridge_json(
                            "/printer-bridge/snapshot",
                            config["bridge_token"],
                            snapshot,
                        )
                        if status == 200:
                            self._last_snapshot_digest[binding_key] = snapshot_digest
                            self._last_snapshot_at[binding_key] = now_monotonic
                            self._last_heartbeat_at[binding_key] = now_monotonic
                    elif heartbeat_due:
                        status, _, retry_after = http_post_bridge_json(
                            "/printer-bridge/heartbeat",
                            config["bridge_token"],
                            {
                                "material_system_id": config["material_system_id"],
                                "provider": "bambu",
                                "transport": "orca_plugin_lan",
                                "source_instance_id": local["source_instance_id"],
                                "observed_at": datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat(),
                            },
                        )
                        if status == 200:
                            self._last_heartbeat_at[binding_key] = now_monotonic
                    else:
                        status = 200
                        retry_after = None
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
                        _persist_discovered_bambu_serial(
                            config["physical_printer_id"], serial
                        )
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


_PLUGIN_RUNTIME_LOCK = threading.Lock()
_PLUGIN_RUNTIME_ACTIVE = False


def start_plugin_runtime():
    """Start process-wide resources once after a host lifecycle load."""
    global _PLUGIN_RUNTIME_ACTIVE
    with _PLUGIN_RUNTIME_LOCK:
        if _PLUGIN_RUNTIME_ACTIVE:
            return False
        _PLUGIN_RUNTIME_ACTIVE = True
    try:
        BACKGROUND_WORKER.activate()
        refresh_ui_language()
        configure_plugin_storage()
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
    global _PLUGIN_RUNTIME_ACTIVE
    with _PLUGIN_RUNTIME_LOCK:
        if not _PLUGIN_RUNTIME_ACTIVE:
            return False
        _PLUGIN_RUNTIME_ACTIVE = False
    BACKGROUND_WORKER.shutdown()
    BAMBU_BRIDGE_RUNTIME.stop()
    SHELL_SERVER.stop()
    return True


class _PluginRuntimeLifecycleMixin:
    """Use the common lifecycle supplied by every current capability base."""

    def on_load(self):
        start_plugin_runtime()

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
_SLICE_INDEX_LIMIT = 300
_SLICE_INDEX_LOCK = threading.Lock()
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


def _is_temporary_slice(path):
    """Whether the host wrote this G-code only to hand it to a printer."""
    if os.path.basename(path).startswith(".OrcaSlicer.upload"):
        return True
    try:
        temp_root = os.path.realpath(tempfile.gettempdir())
        return os.path.commonpath([temp_root, os.path.realpath(path)]) == temp_root
    except (OSError, ValueError):
        return False


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
    if _is_temporary_slice(path):
        path = _cache_slice_file(path, key) or path
    with _SLICE_INDEX_LOCK:
        index = _load_slice_index()
        index[key] = {"path": path, "name": file_name or os.path.basename(path)}
        if len(index) > _SLICE_INDEX_LIMIT:
            for stale in list(index)[: len(index) - _SLICE_INDEX_LIMIT]:
                index.pop(stale, None)
        try:
            write_json_atomic(_SLICE_INDEX_FILE, index, mode=0o600)
        except OSError:
            pass
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


def report_slice(gcode_path, output_name="", host=""):
    """Tell FilamentHub a slice exists. Returns (sent, reason)."""
    identity = _read_slice_identity(gcode_path)
    if identity is None:
        return False, ui_text("sliceUnreadable")
    token = (load_saved_auth() or {}).get("accessToken") or ""
    if not token:
        return False, ui_text("sliceNotSignedIn")
    identity["file_name"] = (
        os.path.basename(output_name or gcode_path) or "print.gcode"
    )[:300]
    identity["source_key"] = _remember_slice_path(gcode_path, identity["file_name"])
    identity["source_instance_id"] = plugin_source_instance_id()
    if host:
        identity["target_host"] = host[:50]
    status, _ = http_post_json("/orcaslicer/slices", token, {"slices": [identity]})
    if status != 200:
        return False, "HTTP %s" % status
    return True, identity["file_name"]


# The name the host matches against a process preset's slicing_pipeline_plugin.
SLICE_CAPABILITY_NAME = "filamenthub-slice-reporter"


class _SliceReporterMixin(_PluginRuntimeLifecycleMixin):
    def get_name(self):
        return SLICE_CAPABILITY_NAME

    def execute(self, ctx):
        step = getattr(ctx, "step", None)
        step_enum = getattr(_SLICING, "Step", None)
        post = getattr(step_enum, "psGCodePostProcess", None)
        if post is None:
            post = getattr(_SLICING, "psGCodePostProcess", None)
        if step is not None and post is not None and step != post:
            return orca.ExecutionResult.skipped(ui_text("sliceWrongStep"))

        path = getattr(ctx, "gcode_path", "") or ""
        if not path or not os.path.exists(path):
            return orca.ExecutionResult.skipped(ui_text("sliceNotReady"))

        try:
            _append_fhub_slice_identities(path, _slice_managed_identities(ctx))
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
        return orca.ExecutionResult.success(ui_text("sliceReported", name=reason))


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
        # Hop from the host's opaque-origin SetPage document onto the loopback
        # server, so the shell gains a real origin the site CSP can allow.
        shell_url = SHELL_SERVER.url_for(render_page())
        html = (
            "<!DOCTYPE html><html><body><script>location.replace("
            + json.dumps(shell_url)
            + ");</script></body></html>"
        )
        self.win = orca.host.ui.create_window(
            title="FilamentHub",
            html=html,
            width=1080,
            height=760,
            on_message=self.on_message,
            on_close=self.on_close,
        )
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
            if announce or operation_id:
                self._deliver_sync_result(
                    ui_text("syncSignIn"),
                    operation_id=operation_id,
                    scope=scope,
                    status="error",
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
        self.win = None
        # Stop serving the token-bearing shell while no window needs it; a
        # reopen spins up a fresh server with a new secret path.
        SHELL_SERVER.stop()

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

    def _deliver_sync_result(self, text, draft_count=0, operation_id="", scope="all",
                             status="success", contours=None):
        draft_count = max(0, int(draft_count or 0))
        payload = {
            "text": text,
            "draftCount": draft_count,
            "operationId": operation_id,
            "scope": scope,
            "status": status,
            "contours": list(contours or []),
        }
        if not self._deliver("sync-result", **payload):
            SHELL_SERVER.set_sync_result(payload)

    def _deliver_notice(self, text, status="info"):
        payload = {"text": text, "status": status}
        if not self._deliver("plugin-notice", **payload):
            SHELL_SERVER.set_sync_result(
                dict(payload, resultType="plugin-notice")
            )

    def _deliver_printer_bundle_result(self, request_id, text, status="success"):
        payload = {
            "requestId": request_id,
            "text": text,
            "status": status,
        }
        if not self._deliver("printer-bundle-result", **payload):
            SHELL_SERVER.set_sync_result(
                dict(payload, resultType="printer-bundle-result")
            )

    def _deliver_recovery(self, items):
        if not self._deliver("recover-list", items=items):
            SHELL_SERVER.set_recover_items(items)

    def _deliver_slice_result(self, result):
        if not self._deliver("parsed-slice", result=result):
            SHELL_SERVER.set_slice_parse(result)

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

    def _do_check_slices(self, wanted, hook):
        alive = [key for key in wanted if slice_path_for_key(key)]
        if not self._deliver("slices-alive", keys=alive, hook=hook):
            SHELL_SERVER.set_slice_alive(alive, hook)

    def _do_configure_bambu(
        self,
        physical_printer_id,
        material_system_id,
        host,
        access_code,
        serial,
        pairing_code,
    ):
        bridge_token = ""
        try:
            _resolved_bambu_address(host)
            pending = {
                "physical_printer_id": physical_printer_id,
                "material_system_id": material_system_id,
                "host": host,
                "access_code": access_code,
                "serial": serial,
            }
            discovered_serial, report = read_bambu_lan_snapshot(pending)
            local = load_bambu_config()
            # A missing config produces a fresh source id. Persist it before
            # pairing so configure_bambu_bridge() cannot generate a second id
            # and make the immediately following snapshot fail its binding.
            # This also proves local durability before the one-time code is
            # consumed on the server.
            save_bambu_config(local)
            pair_status, pair_body = http_post_json(
                "/printer-bridge/pair",
                "",
                {
                    "pairing_code": pairing_code,
                    "provider": "bambu",
                    "transport": "orca_plugin_lan",
                    "source_instance_id": local["source_instance_id"],
                    "plugin_version": PLUGIN_VERSION,
                    "capabilities": ["read", "write", "presence"],
                },
            )
            if pair_status != 200:
                self._deliver_notice(ui_text("bambuPairingFailed"), "error")
                return
            paired = json.loads(pair_body.decode("utf-8"))
            bridge_token = paired.get("bridge_token") if isinstance(paired, dict) else ""
            if not isinstance(bridge_token, str) or not bridge_token.startswith("fhpb_"):
                self._deliver_notice(ui_text("bambuPairingFailed"), "error")
                return
            configure_bambu_bridge(
                physical_printer_id,
                material_system_id,
                host,
                access_code,
                discovered_serial or serial,
                bridge_token,
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
            if snapshot_status == 401:
                remove_bambu_bridge(physical_printer_id)
                self._deliver_notice(ui_text("bambuPairingFailed"), "error")
                return
            if snapshot_status != 200:
                # The durable local binding is valid and the background
                # reader will retry.  Do not claim that data was received;
                # the site distinguishes a paired bridge from last_seen_at.
                fh_log("Initial Bambu bridge upload failed: HTTP %s" % snapshot_status)
        except (OSError, TypeError, ValueError, UnicodeDecodeError):
            # Pairing consumes the one-time code.  If local persistence fails
            # afterwards, revoke the fresh server credential so the site never
            # remains green while no local reader can possibly use it.
            if bridge_token:
                try:
                    http_delete_bridge("/printer-bridge/connection", bridge_token)
                except (OSError, TypeError, ValueError):
                    pass
                remove_bambu_bridge(physical_printer_id)
            self._deliver_notice(ui_text("bambuInvalid"), "error")
            return
        BAMBU_BRIDGE_RUNTIME.wake()
        self._deliver_notice(ui_text("bambuSaved"), "success")

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
        BAMBU_BRIDGE_RUNTIME.wake()
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
        inventory, inventory_error = _plugin_material_server_inventory(token)
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
        BAMBU_BRIDGE_RUNTIME.wake()

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

    def on_message(self, msg):
        if not isinstance(msg, dict):
            return
        if msg.get("source") != "filamenthub-plugin":
            return
        msg_type = msg.get("type")
        if msg_type == "host-ready":
            self._deliver("transport", push=True)
            if not getattr(self, "_session_sync_started", False):
                self._session_sync_started = self._auto_sync(
                    announce=True,
                    scope="all",
                    trigger="session-start",
                )
        elif msg_type == "read-diagnostics":
            BACKGROUND_WORKER.submit(
                lambda: self._deliver("diagnostics", text=read_sync_log())
            )
        elif msg_type == "import-preset":
            preset_id = msg.get("presetId")
            token = msg.get("token") or ""
            if not isinstance(token, str) or len(token) > MAX_TOKEN_LENGTH:
                return
            # The catalog only carries a token when it minted a fresh plugin
            # session this window; a session restored from .auth.json leaves it
            # empty. Fall back to the persisted token — the same source Sync uses.
            if not token:
                token = (load_saved_auth() or {}).get("accessToken") or ""
            known = self._known_filament_preset_names()  # host read on the UI thread
            refresh_user_preset_folder()
            BACKGROUND_WORKER.submit(self._do_import, preset_id, token, known)
        elif msg_type == "install-printer-bundle":
            request_id = msg.get("requestId")
            physical_printer_id = msg.get("physicalPrinterId")
            if not (
                isinstance(request_id, str)
                and 0 < len(request_id) <= 100
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
        elif msg_type == "configure-bambu-local":
            physical_printer_id = msg.get("physicalPrinterId")
            material_system_id = msg.get("materialSystemId")
            host = msg.get("host")
            access_code = msg.get("accessCode")
            serial = msg.get("serial") or ""
            pairing_code = msg.get("pairingCode") or ""
            if not (
                isinstance(physical_printer_id, int)
                and isinstance(material_system_id, int)
                and isinstance(host, str)
                and isinstance(access_code, str)
                and isinstance(serial, str)
                and isinstance(pairing_code, str)
                and 8 <= len(pairing_code) <= 32
            ):
                return
            BACKGROUND_WORKER.submit(
                self._do_configure_bambu,
                physical_printer_id,
                material_system_id,
                host,
                access_code,
                serial,
                pairing_code,
            )
        elif msg_type == "remove-bambu-local":
            physical_printer_id = msg.get("physicalPrinterId")
            if not isinstance(physical_printer_id, int) or physical_printer_id <= 0:
                return
            BACKGROUND_WORKER.submit(self._do_remove_bambu, physical_printer_id)
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
                BAMBU_BRIDGE_RUNTIME.wake()
                if not getattr(self, "_session_sync_started", False):
                    self._session_sync_started = self._auto_sync(
                        announce=True,
                        scope="all",
                        trigger="session-auth",
                    )
        elif msg_type == "profile-changed":
            # This event belongs to the filament library. Printer and process
            # profiles have their own explicit entry points.
            self._auto_sync(
                announce=True,
                scope="filament",
                trigger="profile-change",
            )
        elif msg_type == "open-oauth":
            self._start_external_oauth(msg.get("provider"))
        elif msg_type == "open-external":
            self._open_site_path(msg.get("path"))
        elif msg_type == "auth-logout":
            clear_auth()
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
        if not token or not isinstance(keys, list) or not keys:
            self._deliver_notice(ui_text("recoveryNone"), "warning")
            return
        wanted = {str(key) for key in keys}
        candidates = disambiguate_recovery_candidates(
            [c for c in scan_recovery_presets() if c["key"] in wanted]
        )
        imported = load_imported_draft_ids()
        recovered_keys = set()

        filament_candidates = [c for c in candidates if c["kind"] == "filament"]
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
                    continue
                sync_items.append(item)
                keys_by_name.setdefault(candidate["name"], []).append(candidate["key"])
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
                ),
                plugin_source_instance_id(),
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
        self._deliver_notice(
            ui_text("recoveryDone", count=len(recovered_keys)), "success"
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
            counts = install_printer_bundle(bundle)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            fh_log("printer bundle install failed: %s" % exc)
            self._deliver_printer_bundle_result(
                request_id, ui_text("printerBundleInvalid"), "error"
            )
            return
        self._deliver_printer_bundle_result(
            request_id,
            ui_text(
                "printerBundleInstalled",
                machines=counts["machine"],
                processes=counts["process"],
            )
        )

    def _start_external_oauth(self, provider):
        # Google/Yandex block their consent pages in embedded WebViews, so run the
        # provider flow in the user's real browser. Python opens a dedicated site
        # route that carries a loopback callback (cb) + one-time nonce; after the
        # provider round-trip the site redirects the session back to /d/<secret>,
        # which the shell is polling for. If the browser can't be launched (sandbox
        # or headless), the shell shows the URL so the user can open it manually.
        if provider not in ("google", "yandex"):
            return
        deliver = SHELL_SERVER.deliver_url()
        if not deliver:
            return
        nonce = secrets.token_urlsafe(24)
        start_url = "%s/oauth/plugin-start/%s?%s" % (
            SITE_URL, provider,
            urllib.parse.urlencode({"cb": deliver, "nonce": nonce}))
        opened = open_in_system_browser(start_url)
        SHELL_SERVER.arm_oauth(nonce, opened, start_url)

    def _open_site_path(self, path):
        # A wiki page links to other parts of the site. Inside this panel there is
        # nowhere for a second tab to go, so the link opens in the real browser.
        # Only a site-relative path is accepted and the origin is added here, so
        # the embedded page cannot turn this into "open any address".
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            return
        open_in_system_browser(SITE_URL + path)

    def _do_import(self, preset_id, token, known_presets):
        try:
            preset_id = int(preset_id)
        except (TypeError, ValueError):
            return
        if not token:
            orca.host.ui.message(
                ui_text("importSignIn"),
                title="FilamentHub", icon="warning")
            return
        try:
            status, body = http_get("/presets/%d/export/orcaslicer.json" % preset_id, token=token)
            if status == 401:
                clear_auth()
                orca.host.ui.message(
                    ui_text("sessionExpired"),
                    title="FilamentHub", icon="warning")
                return
            if status != 200:
                orca.host.ui.message(ui_text("exportFailed", status=status),
                                     title="FilamentHub", icon="error")
                return

            profile = validate_filament_profile(json.loads(body.decode("utf-8")))
            ensure_parent_exists(profile, known_presets)
            ensure_filament_colour(profile)
            # Namespace the managed preset with the same provider identity used by
            # the sync API; a plain user preset has no FilamentHub bundle_id.
            profile["bundle_id"] = "filamenthub:%d" % preset_id
            name = profile.get("name") or ("FilamentHub preset %d" % preset_id)
            ensure_bundle_metadata()
            target_dir = user_filament_dir()
            profile_path = preset_file_path(target_dir, name, preset_id)
            name = apply_managed_filename_identity(profile, profile_path)
            base = profile_path[:-len(".json")]
            validate_filament_profile(profile)
            write_managed_info(base, preset_id, token)
            write_json_atomic(profile_path, profile)
            remove_stale_preset_files(target_dir, preset_id, profile_path)
            fh_log("import %d written, pending restart: %s" % (preset_id, name))

            orca.host.ui.message(
                ui_text("importedRestart", name=name),
                title="FilamentHub", icon="info")
        except Exception as exc:
            orca.host.ui.message(
                ui_text("importFailed", error=exc), title="FilamentHub", icon="error")

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
        status, body = http_get("/presets/%d/export/orcaslicer.json" % pid, token=token)
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
        name = profile.get("name") or ("FilamentHub preset %d" % pid)
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
            write_managed_info(base, pid, token)
            write_json_atomic(profile_path, profile)
        except OSError as exc:
            fh_log("pull %d FAILED: write error at %s: %r" % (pid, profile_path, exc))
            return None
        remove_stale_preset_files(folder, pid, profile_path)
        return {"updated_at": (remote or {}).get("updated_at") or "",
                "hash": preset_content_hash(profile), "name": name}

    def _push_one(self, pid, token, local_entry, remote):
        # Send a locally-edited preset back to FilamentHub. The backend updates the
        # user's own preset or forks a non-owned one into a new user preset.
        profile = local_entry["profile"]
        local_name = profile.get("name") or ("FilamentHub preset %d" % pid)
        remote_name = (remote or {}).get("name") or ""
        normalized_remote_name = safe_filename(remote_name) if remote_name else ""
        automatic_local_names = {
            normalized_remote_name,
            "%s (FH-%d)" % (normalized_remote_name, pid),
        }
        upload_name = remote_name if local_name in automatic_local_names else local_name
        upload_profile = restore_remote_parent_for_upload(profile, pid, token)
        if upload_profile is None:
            fh_log("push %d deferred: canonical parent could not be verified" % pid)
            return None
        upload_profile["name"] = upload_name
        upload_profile["filament_settings_id"] = [upload_name]
        item = {
            "fhub_id": pid,
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
        status, _ = http_post_json("/orcaslicer/filaments/import", token, {"profiles": [item]})
        if status != 200:
            fh_log("push %d FAILED: import HTTP %s" % (pid, status))
            return None
        return {"updated_at": (remote or {}).get("updated_at") or "",
                "hash": local_entry["hash"], "name": profile.get("name") or ""}

    def _do_sync(self, token, known_presets, announce=True, active_filaments=None,
                 host_profiles=None, observations=None, source_instance_id="",
                 moonraker_connections=None, loaded_preset_ids=None, scope="all",
                 operation_id="", trigger="manual"):
        if not token or scope not in SYNC_SCOPES:
            if announce or operation_id:
                self._deliver_sync_result(
                    ui_text("syncSignIn"), operation_id=operation_id,
                    scope=scope, status="error",
                )
            return

        preferences = _sync_preferences(token)
        if not preferences["available"]:
            contours = [
                {
                    "kind": kind,
                    "status": "error",
                    "summary": ui_text("summaryPreferencesUnavailable"),
                }
                for kind in ("filament", "machine", "process")
                if sync_scope_includes(scope, kind)
            ]
            text = ui_text("syncCompleteTitle") + "\n" + "\n".join(
                "%s: %s" % (
                    ui_text(
                        "profileFilament" if item["kind"] == "filament"
                        else "profileMachine" if item["kind"] == "machine"
                        else "profileProcess"
                    ),
                    item["summary"],
                )
                for item in contours
            )
            self._deliver_sync_result(
                text, operation_id=operation_id, scope=scope,
                status="error", contours=contours,
            )
            return

        state = load_sync_state()
        contours = []
        overall_status = "success"
        new_draft_count = 0
        restart_required = False
        filament_report_version = None
        filament_report_results = None

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
            pulled = updated = pushed = skipped = failed = renamed = removed = 0
            failed_ids = []
            remote_ids = set()
            changed_file_ids = set()
            folder = user_filament_dir()
            allow_pull = preferences["allow_filament_presets_export"]
            allow_push = preferences["allow_filament_presets_import"]
            if allow_pull:
                ensure_bundle_metadata()
                try:
                    os.makedirs(folder, exist_ok=True)
                except OSError:
                    pass
                if source_instance_id and operation_id:
                    filament_report_version = begin_filament_sync_report(
                        token, source_instance_id
                    )
                remote_status, remote_body = http_get("/auth/my-presets", token=token)
                if remote_status == 401:
                    clear_auth()
                    filament_parts.append(ui_text("sessionExpired"))
                    filament_status = "error"
                    remote_items = None
                elif remote_status != 200:
                    filament_parts.append(ui_text("syncFailed", status=remote_status))
                    filament_status = "error"
                    remote_items = None
                else:
                    try:
                        remote_items = (
                            json.loads(remote_body.decode("utf-8")) or {}
                        ).get("items") or []
                    except (AttributeError, UnicodeDecodeError, ValueError):
                        remote_items = None
                        filament_parts.append(ui_text("syncUnexpected"))
                        filament_status = "error"

                if remote_items is not None:
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
                                remote_updated,
                            )
                            if recovered is None:
                                skipped += 1
                                continue
                            if recovered is False:
                                if not allow_push:
                                    skipped += 1
                                    filament_status = "warning"
                                    continue
                                result = self._push_one(
                                    preset_id, token, local_entry, remote
                                )
                                if result:
                                    state[str(preset_id)] = result
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
                        remote_newer = remote_updated > (
                            record.get("updated_at") or ""
                        )
                        if local_changed:
                            if not allow_push:
                                skipped += 1
                                filament_status = "warning"
                                continue
                            result = self._push_one(
                                preset_id, token, local_entry, remote
                            )
                            if result:
                                state[str(preset_id)] = result
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
                                try:
                                    os.replace(local_entry["path"], canonical)
                                except OSError:
                                    pass
                                else:
                                    local_entry["path"] = canonical
                                    try:
                                        write_bytes_atomic(
                                            canonical[:-len(".json")] + ".info",
                                            managed_info_bytes(preset_id),
                                        )
                                    except OSError:
                                        pass
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
                    self._log_managed_preset_state(
                        folder, remote_ids, loaded_preset_ids, failed_ids
                    )
                    restart_required = bool(pulled or updated or removed or renamed)
                    if filament_report_version is not None:
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
                filament_status = "warning"

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
            if skipped:
                filament_parts.append(ui_text("summaryCurrent", count=skipped))
            if failed:
                filament_parts.append(ui_text("summaryFailed", count=failed))
                filament_status = "error"
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
                add_contour(kind, [ui_text("summaryDisabled")], "warning")
                continue
            scan = (host_profiles or {}).get(kind) or {}
            items = scan.get("items") or []
            complete = bool(scan.get("complete"))
            sent, failed = push_user_profiles(
                kind, token, items, state, authoritative=complete
            )
            parts = []
            if sent:
                parts.append(ui_text("summarySent", count=sent))
            if failed:
                parts.append(ui_text("summaryFailed", count=failed))
            status = "error" if failed else "success"
            if not complete:
                parts.append(ui_text("summaryScanIncomplete"))
                status = "error"
            add_contour(kind, parts, status)

        if sync_scope_includes(scope, "machine") and preferences[
            "allow_printer_profiles_import"
        ]:
            observation_status, _observation_result = send_printer_observations(
                token,
                _observations_for_sync(
                    observations,
                    share_endpoints=preferences["sync_printer_endpoints"],
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
            sync_happy_hare_topologies(token, moonraker_connections)

        save_sync_state(state)
        if (
            filament_report_version is not None
            and filament_report_results is not None
        ):
            complete_filament_sync_report(
                token,
                source_instance_id,
                filament_report_version,
                filament_report_results,
            )
        labels = {
            "filament": ui_text("profileFilament"),
            "machine": ui_text("profileMachine"),
            "process": ui_text("profileProcess"),
        }
        text = ui_text("syncCompleteTitle") + "\n" + "\n".join(
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
            self._deliver_sync_result(
                text,
                new_draft_count,
                operation_id=operation_id,
                scope=scope,
                status=overall_status,
                contours=contours,
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

        def get_name(self):
            return "FilamentHub"

        def get_icon(self):
            return ensure_icon()

        def get_ui(self):
            shell_url = SHELL_SERVER.url_for(render_page())
            return (
                "<!DOCTYPE html><html><body><script>location.replace("
                + json.dumps(shell_url)
                + ");</script></body></html>"
            )

        def on_message(self, message):
            self._catalog.on_message(message)

        def on_unload(self):
            self._catalog.on_close()
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
