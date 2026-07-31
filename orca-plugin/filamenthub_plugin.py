# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub"
# name = "FilamentHub"
# description = "Browse and sync community-rated filament profiles from FilamentHub, with spool inventory and print-cost tools."
# author = "FilamentHub"
# version = "0.0.9"
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
folder, then shows a native "restart required" dialog.

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
  * orca.script.ScriptPluginCapabilityBase.execute()       — entry point
  * orca.host.ui.create_window(html, on_message, on_close)  — the shell window
  * orca.host.ui.message(...)                               — restart notice
  * the injected window.orca bridge (PluginWebDialog.cpp:ORCA_BRIDGE_JS)

Login/token: the user signs in inside the iframe on our own site (normal flow).
The page mints a short-lived, plugin-scoped capability for preset read/write;
the account access/refresh credentials never cross the iframe boundary. The
capability may be cached locally until expiry so a reopened window can resume.
"""

import hashlib
import http.server
import json
import os
import queue
import re
import secrets
import shutil
import ssl
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
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

    def submit(self, function, *args, **kwargs):
        self._jobs.put((function, args, kwargs))
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run,
                    name=self._name,
                    daemon=True,
                )
                self._thread.start()

    def _run(self):
        current = threading.current_thread()
        while True:
            try:
                function, args, kwargs = self._jobs.get(timeout=self._idle_timeout)
            except queue.Empty:
                with self._lock:
                    if self._jobs.empty():
                        if self._thread is current:
                            self._thread = None
                        return
                continue
            try:
                function(*args, **kwargs)
            except Exception as exc:
                logger = globals().get("fh_log")
                if logger is not None:
                    logger("background job failed: %s" % exc)
            finally:
                self._jobs.task_done()


BACKGROUND_WORKER = ReusableDaemonWorker("filamenthub-worker")


def post_window(window, payload):
    """Best-effort host push, safe against a window closing during a worker job."""
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
PLUGIN_VERSION = "0.0.9"
PROD_SITE_URL = "https://filamenthub.ru"
SITE_URL = os.environ.get("FILAMENTHUB_SITE_URL", "http://localhost:3000").rstrip("/")
DEV_CONTOUR = SITE_URL != PROD_SITE_URL
EMBED_URL = SITE_URL + "/embed/catalog"
API_BASE = SITE_URL + "/api/v1"
HTTP_TIMEOUT = 20
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_TOKEN_LENGTH = 8192
MAX_FILENAME_LENGTH = 120
_SSL_CTX = ssl.create_default_context()


def host_ui_language():
    """Return the supported Orca UI language, or defer to the WebView."""
    app_language = getattr(getattr(orca, "host", None), "app_language", None)
    if not callable(app_language):
        return ""
    try:
        language = str(app_language()).lower()
    except (AttributeError, RuntimeError):
        return ""
    if language.startswith("ru"):
        return "ru"
    if language.startswith("zh"):
        return "zh"
    return "en"


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
        for collection in (bundle.filaments, bundle.printers):
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


def user_filament_dir():
    return os.path.join(user_bundle_dir(), "filament")


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
    and that cache is wiped on update — sidecar state (.auth.json, .fh_sync.json,
    the icon) must live in the install dir, not wherever __file__ happens to be."""
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


def ensure_icon():
    return ICON_PATH if os.path.isfile(ICON_PATH) else ""


def configure_plugin_storage():
    """Use Orca's private plugin storage when the host exposes it.

    Existing sidecar state is copied once and retained as a rollback fallback.
    The API is called from register_capabilities(), where Orca can attribute the
    request to the plugin; importing this module must stay host-version agnostic.
    """
    global PLUGIN_STORAGE_DIR
    global SYNC_LOG_FILE, AUTH_FILE, IMPORTED_DRAFTS_FILE, SYNC_STATE_FILE
    global _SLICE_INDEX_FILE, _SLICE_CACHE_DIR

    plugin_host = getattr(getattr(orca, "host", None), "plugin", None)
    storage = getattr(plugin_host, "storage", None)
    if not callable(storage):
        return False
    try:
        target_root = os.path.abspath(storage())
        if not target_root:
            return False
        os.makedirs(target_root, exist_ok=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False

    file_names = (
        ".fh_sync.log",
        ".auth.json",
        ".fh_imported.json",
        ".fh_sync.json",
        ".fh_slices.json",
    )
    for name in file_names:
        source = os.path.join(PLUGIN_DIR, name)
        target = os.path.join(target_root, name)
        if source != target and os.path.isfile(source) and not os.path.exists(target):
            try:
                shutil.copy2(source, target)
            except OSError:
                pass

    legacy_cache = os.path.join(PLUGIN_DIR, "slices")
    target_cache = os.path.join(target_root, "slices")
    if legacy_cache != target_cache and os.path.isdir(legacy_cache) and not os.path.exists(target_cache):
        try:
            shutil.copytree(legacy_cache, target_cache)
        except OSError:
            pass

    PLUGIN_STORAGE_DIR = target_root
    SYNC_LOG_FILE = os.path.join(target_root, ".fh_sync.log")
    AUTH_FILE = os.path.join(target_root, ".auth.json")
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


# Session tokens live next to the plugin (inside data_dir, the allowed write
# root) so signing in survives window/OrcaSlicer restarts — the iframe's own
# storage is partitioned and dies with the window. Same role as the fork's
# AppConfig token storage.
AUTH_FILE = os.path.join(PLUGIN_DIR, ".auth.json")


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
        self._sync_result = ""
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

    def set_sync_result(self, text):
        with self._sync_lock:
            self._sync_result = text or ""

    def _sync_status(self):
        with self._sync_lock:
            text = self._sync_result
            self._sync_result = ""
        return {"text": text}

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


def reload_host_presets():
    """Live filament reload via our fork's orca.host.presets.reload_filaments():
    re-reads only the filament presets (additions and removals) and refreshes the
    filament combos, leaving the printer/process selection untouched. The method
    name is new, so on a stock or older build it's absent and we return False,
    falling back to a restart. Returns True if the host reloaded live.
    """
    presets = getattr(orca.host, "presets", None)
    reload = getattr(presets, "reload_filaments", None) if presets is not None else None
    if reload is None:
        return False
    try:
        reload()
        return True
    except Exception:
        return False


def remove_host_filament(bare_name):
    """Remove one filament preset from the running slicer by its bundle-canonical
    name (the same targeted delete OrcaSlicer's Delete button uses). Returns True
    if the host removed it live; False on a stock/older build (caller then deletes
    the files and the user restarts). delete_preset also removes the files."""
    presets = getattr(orca.host, "presets", None)
    remove = getattr(presets, "remove_filament", None) if presets is not None else None
    if remove is None:
        return False
    try:
        return bool(remove("_local/%s/%s" % (BUNDLE_ID, bare_name)))
    except Exception:
        return False


def safe_filename(name):
    cleaned = "".join(
        "_" if ch in '<>:"/\\|?*' or ord(ch) < 32 else ch
        for ch in (name or "preset")
    ).strip(" ._")
    cleaned = cleaned[:MAX_FILENAME_LENGTH].rstrip(" ._") or "preset"
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update("COM%d" % index for index in range(1, 10))
    reserved.update("LPT%d" % index for index in range(1, 10))
    if cleaned.split(".", 1)[0].upper() in reserved:
        cleaned = "_" + cleaned
    return cleaned


def validate_filament_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError("Preset export must be a JSON object")
    name = profile.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise ValueError("Preset name must be a non-empty string")
    return profile


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
        if isinstance(existing, dict) and preset_id_from_bundle(existing.get("bundle_id")) == int(preset_id):
            return candidate
    except (OSError, ValueError):
        pass
    return os.path.join(folder, "%s (FH-%d).json" % (stem, int(preset_id)))


def remove_stale_preset_files(folder, preset_id, keep_path):
    """Delete other files carrying this preset's bundle_id — the old
    `__fh_<id>`-suffixed naming and leftovers from a rename on FilamentHub —
    so one preset never shows up twice in the dropdown. Touches only files
    whose bundle_id we own."""
    try:
        names = os.listdir(folder)
    except OSError:
        return
    keep = os.path.normcase(os.path.abspath(keep_path))
    for fn in names:
        if not fn.endswith(".json"):
            continue
        path = os.path.join(folder, fn)
        if os.path.normcase(os.path.abspath(path)) == keep:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                profile = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(profile, dict) or preset_id_from_bundle(profile.get("bundle_id")) != int(preset_id):
            continue
        try:
            remove_host_filament(fn[:-len(".json")])  # best-effort live removal
        except Exception:
            pass
        for stale in (path, path[:-len(".json")] + ".info"):
            try:
                os.remove(stale)
            except OSError:
                pass


# Universal base filament preset present in every OrcaSlicer install.
FALLBACK_PARENT = "fdm_filament_common"


def ensure_parent_exists(profile, known_presets):
    """Make the imported preset's parent resolvable, mirroring the fork's import.

    A preset inherits a system preset by name. If that parent is not installed
    (the user has a different printer/vendor), the preset loads as incompatible
    and never shows in the dropdown. Fall back to the universal base so the
    preset always loads; its own overrides are preserved.
    """
    inherits = profile.get("inherits")
    if isinstance(inherits, list):
        inherits = inherits[0] if inherits else ""
    if not inherits or inherits not in known_presets:
        profile["inherits"] = FALLBACK_PARENT


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


def observe_printer_presets():
    """What OrcaSlicer knows about the machines this person has (UI thread —
    reads preset_bundle). Two kinds of entry, and printhost_apikey is in neither:

    * a preset with a network endpoint — the connection FilamentHub can observe;
    * every installed printer model, with no endpoint. A model is only present
      because the person picked that machine in Orca's setup wizard, so it is a
      statement of ownership rather than vendor data — which is how a Bambu, whose
      presets never carry an endpoint, becomes visible at all. Reported once per
      model: choosing one machine installs a preset per nozzle size, and those are
      four presets of one printer. The model alone is enough, since the catalog
      already mirrors Orca's models; an untouched vendor preset has nothing else
      worth copying.
    """
    observed = []
    seen_models = set()
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
            model = preset.config_value("printer_model") or ""
            host = preset.config_value("print_host") if preset.is_user() else ""
            if host:
                observed.append({
                    "preset_name": preset.name,
                    "printer_settings_id": preset.config_value("printer_settings_id") or "",
                    "inherits": preset.config_value("inherits") or "",
                    "printer_model": model,
                    "print_host": host,
                    "host_type": preset.config_value("host_type") or "",
                    "is_current": preset.name == current_name,
                })
            elif model and model not in seen_models:
                seen_models.add(model)
                observed.append({
                    "preset_name": model,
                    "printer_settings_id": model,
                    "inherits": "",
                    "printer_model": model,
                    "print_host": "",
                    "host_type": "",
                    "is_current": preset.name == current_name,
                })
    except Exception:
        pass
    return observed


def send_printer_observations(token, observations):
    """POST observed printer connection data. The backend records it raw; the
    plugin makes no physical-printer identity decisions."""
    if not token or not observations:
        return
    http_post_json("/orcaslicer/printer-connections/observe", token,
                   {"observations": observations})


def _collect_filament_presets(root, into, only_new):
    """Walk {root}/<account>/filament/ (incl. base/) and add each preset by name to
    `into`. only_new keeps existing entries (live set wins over older backups).
    Skips our [fh]-managed presets and a "filamenthub:<id>" bundle_id."""
    try:
        accounts = os.listdir(root)
    except OSError:
        return
    for account in accounts:
        base = os.path.join(root, account, "filament")
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(dirpath, fn), "r", encoding="utf-8") as fh:
                        profile = json.load(fh)
                except (OSError, ValueError):
                    continue
                if not isinstance(profile, dict) or not profile:
                    continue
                name = profile.get("name") or fn[:-len(".json")]
                if "[fh]" in name or "@fh" in name:
                    continue
                if preset_id_from_bundle(profile.get("bundle_id")) is not None:
                    continue
                if only_new and name in into:
                    continue
                into.setdefault(name, profile)


def scan_recovery_filaments():
    """Every filament preset the user has on disk, for the explicit "find lost
    filaments" action. Walks {data_dir}/user/<account>/filament/ (all accounts,
    incl. base/) then the user_backup-v* version snapshots, adding a backup preset
    only when its name is absent from the live set — so old/deleted presets are
    recovered without stale duplicates. Skips our [fh]-managed ones; the Orca
    system/ library is never touched. Vendor-materialized presets may come along;
    the user picks what to keep. Read-only; disk-only, so it runs off the UI thread."""
    by_name = {}
    _collect_filament_presets(os.path.join(DATA_DIR, "user"), by_name, only_new=False)
    try:
        backups = [d for d in os.listdir(DATA_DIR) if d.startswith("user_backup")]
    except OSError:
        backups = []
    for backup in backups:
        _collect_filament_presets(os.path.join(DATA_DIR, backup), by_name, only_new=True)
    return [{"name": name, "profile": profile} for name, profile in by_name.items()]


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


def scan_active_user_filaments():
    """The loaded account's own filament presets (UI thread — reads preset_bundle).
    Keep is_user() presets, skip system/vendor and our [fh] ones. Configuration
    comes from Orca's Preset API instead of reopening the backing JSON file."""
    candidates = []
    try:
        filaments = orca.host.preset_bundle().filaments
        for i in range(filaments.size()):
            preset = filaments.preset(i)
            if not preset.is_user():
                continue
            name = preset.name or ""
            if "[fh]" in name or "@fh" in name:
                continue
            if preset_id_from_bundle(getattr(preset, "bundle_id", "")) is not None:
                continue
            profile = preset_config_dict(preset, include_metadata=True)
            if profile:
                candidates.append({"name": name, "profile": profile})
    except Exception:
        pass
    return candidates


def _auto_import_enabled(token):
    """Whether the user opted into auto-importing local presets. Uses the
    plugin-scoped /orcaslicer/sync-prefs (the plugin has no full account session)."""
    status, body = http_get("/orcaslicer/sync-prefs", token=token)
    if status != 200:
        fh_log("sync-prefs HTTP %s -> auto-import off" % status)
        return False
    try:
        return bool(json.loads(body.decode("utf-8")).get("auto_import_local_presets"))
    except ValueError:
        return False


def _draft_id(name):
    return "orca_local_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:12]


IMPORTED_DRAFTS_FILE = os.path.join(PLUGIN_DIR, ".fh_imported.json")


def load_imported_draft_ids():
    """Draft-ids already pushed by auto-import, kept next to the plugin so each
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


def push_filament_drafts(token, candidates):
    """Push candidate presets to FilamentHub as private drafts (batched ≤50). The
    backend creates one draft per preset and dedups by a stable fhub_draft_id.
    Returns the draft-ids accepted (HTTP 200)."""
    sent_ids = []
    batch = []
    batch_ids = []
    for c in candidates:
        did = _draft_id(c["name"])
        settings = dict(c["profile"])
        settings["fhub_draft_id"] = did
        batch.append({"name": c["name"][:200], "orcaslicer_settings": settings, "source": "orcaslicer"})
        batch_ids.append(did)
        if len(batch) >= 50:
            st, _ = http_post_json("/orcaslicer/filaments/import", token, {"profiles": batch})
            if st == 200:
                sent_ids.extend(batch_ids)
            batch, batch_ids = [], []
    if batch:
        st, _ = http_post_json("/orcaslicer/filaments/import", token, {"profiles": batch})
        if st == 200:
            sent_ids.extend(batch_ids)
    return sent_ids


# --------------------------------------------------------------------------- #
# Two-way sync (all plugin-side; the host is never touched). Mirrors the fork's
# model: identity is the "filamenthub:<id>" bundle_id; the FilamentHub version is
# preset.updated_at; a local edit is detected by a content hash. A small state
# file next to the plugin records, per preset, the (updated_at, hash) at the last
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
    if preset_content_hash(remote) != local_entry["hash"]:
        return False
    return {"updated_at": remote_updated or "",
            "hash": local_entry["hash"],
            "name": local_entry["profile"].get("name") or ""}


def scan_local_fh_presets(folder):
    # Map preset_id -> {path, profile, hash} for every local file that carries a
    # filamenthub bundle_id. These are the presets under our sync management.
    out = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".json"):
            continue
        path = os.path.join(folder, fn)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                profile = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(profile, dict):
            continue
        pid = preset_id_from_bundle(profile.get("bundle_id"))
        if pid is not None:
            out[pid] = {"path": path, "profile": profile, "hash": preset_content_hash(profile)}
    return out


# --------------------------------------------------------------------------- #
# Printer (machine) and print (process) profiles travel one way: read out of
# OrcaSlicer and handed to FilamentHub, so the site knows which machine a spool,
# a gate or a recommendation belongs to. Nothing is ever written back into the
# slicer — OrcaCloud already syncs a user's own machine and process presets
# across their installs, and FilamentHub's own library is filament presets. Each
# profile is sent once and again only after it changes; the content hash lives in
# the shared sync state.
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

# A printer preset carries the credentials of its network host. They stay on the
# user's machine: the profile is stripped before anything goes to FilamentHub.
PRINTHOST_SECRET_KEYS = ("printhost_apikey", "printhost_password", "printhost_user")


def strip_printhost_secrets(settings):
    return {k: v for k, v in settings.items() if k not in PRINTHOST_SECRET_KEYS}


def scan_user_profiles(kind):
    """The loaded account's own presets of one collection (UI thread — reads
    preset_bundle). Values come from config_value, which resolves inheritance:
    the file on disk holds only the overrides, so a nozzle inherited from the
    system preset would otherwise never reach FilamentHub."""
    out = []
    try:
        collection = getattr(orca.host.preset_bundle(), PROFILE_KINDS[kind]["collection"])
        for i in range(collection.size()):
            preset = collection.preset(i)
            if not preset.is_user():
                continue
            name = preset.name or ""
            if "[fh]" in name or "@fh" in name:
                continue
            if str(getattr(preset, "bundle_id", "") or "").startswith(BUNDLE_ID):
                continue
            settings = preset_config_dict(preset)
            if settings:
                out.append({"name": name, "settings": settings})
    except Exception:
        pass
    return out


def push_user_profiles(kind, token, items, state):
    """Send the profiles whose content changed since the last sync. Returns
    (sent, failed); unchanged profiles are silently left alone."""
    spec = PROFILE_KINDS[kind]
    changed = []
    for item in items:
        settings = item["settings"]
        if kind == "machine":
            settings = strip_printhost_secrets(settings)
        key = "%s:%s" % (spec["state_prefix"], _draft_id(item["name"]))
        digest = preset_content_hash(settings)
        if state.get(key) == digest:
            continue
        # setting_id is how FilamentHub ties a network observation of this printer
        # back to its profile, so it must travel with the profile, not only as the
        # external id.
        orca_id = str(settings.get(spec["id_key"]) or item["name"])[:200]
        changed.append((key, digest, {
            "name": item["name"][:200],
            "external_id": orca_id,
            "setting_id": orca_id,
            "orcaslicer_settings": settings,
            "source": "orcaslicer",
        }))
    sent = failed = 0
    for batch_start in range(0, len(changed), 25):
        batch = changed[batch_start:batch_start + 25]
        status, _ = http_post_json(spec["import_path"], token,
                                   {"profiles": [entry[2] for entry in batch]})
        if status == 200:
            for key, digest, _payload in batch:
                state[key] = digest
            sent += len(batch)
        else:
            fh_log("%s push HTTP %s for %d profile(s)" % (kind, status, len(batch)))
            failed += len(batch)
    return sent, failed


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
  #brand { color:var(--orca-fg,#e0e0e0); font-size:13px; font-weight:600; }
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
    color:var(--orca-accent,#8b7cf8);
    border-color:var(--orca-accent,#8b7cf8);
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
      <span id="brand">Sign in</span>
      <button id="logout" title="Sign out">Sign out</button>
    </span>
    <button data-path="/" class="active">Catalog</button>
    <button data-path="/profile">Profile</button>
    <button data-path="/wiki">Wiki</button>
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
    <iframe id="fh" src="__EMBED_URL__" title="FilamentHub catalog" allow="clipboard-write"></iframe>
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
var STATUS_COPY = {
  en: {
    connectTitle: 'Connecting to FilamentHub...',
    connectMessage: 'Please wait while the catalog is loaded.',
    unavailableTitle: 'FilamentHub is temporarily unavailable',
    unavailableMessage: 'The service may be undergoing maintenance. Your local OrcaSlicer presets are safe. Please try again later.',
    retry: 'Try again'
  },
  ru: {
    connectTitle: 'Подключение к FilamentHub…',
    connectMessage: 'Подождите, пока загрузится каталог.',
    unavailableTitle: 'FilamentHub временно недоступен',
    unavailableMessage: 'Возможно, сейчас идут технические работы. Ваши локальные профили OrcaSlicer в безопасности. Попробуйте ещё раз позже.',
    retry: 'Повторить'
  },
  zh: {
    connectTitle: '正在连接 FilamentHub…',
    connectMessage: '请稍候，目录正在加载。',
    unavailableTitle: 'FilamentHub 暂时不可用',
    unavailableMessage: '服务可能正在维护中。您的本地 OrcaSlicer 预设不会受到影响，请稍后重试。',
    retry: '重试'
  }
};
var hostLanguage = '__HOST_UI_LANGUAGE__';
var browserLanguage = (hostLanguage || navigator.language || 'en').toLowerCase();
var statusLocale = browserLanguage.indexOf('ru') === 0
  ? 'ru'
  : browserLanguage.indexOf('zh') === 0
    ? 'zh'
    : 'en';
var statusCopy = STATUS_COPY[statusLocale];
document.documentElement.lang = statusLocale;


function showCatalogStatus(mode) {
  var unavailable = mode === 'unavailable';
  document.getElementById('service-status').style.display = 'flex';
  document.getElementById('service-spinner').style.display = unavailable ? 'none' : 'block';
  document.getElementById('service-status-title').textContent = unavailable
    ? statusCopy.unavailableTitle
    : statusCopy.connectTitle;
  document.getElementById('service-status-message').textContent = unavailable
    ? statusCopy.unavailableMessage
    : statusCopy.connectMessage;
  document.getElementById('service-retry').textContent = statusCopy.retry;
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
  brand.style.cursor = loggedIn ? 'default' : 'pointer';
  brand.title = loggedIn ? '' : 'Sign in to FilamentHub';
  // Signed out: make the label read as an actionable button (accent colour).
  brand.style.color = loggedIn ? 'var(--orca-fg,#e0e0e0)' : 'var(--orca-accent,#8b7cf8)';
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
setAuthControls(false);  // hidden until the catalog reports a signed-in state

// Catalog -> shell. auth-state updates the toolbar label; open-oauth runs the
// provider sign-in in the real browser and waits for the session over loopback;
// everything else relays to Python.
window.addEventListener('message', function (event) {
  var data = event.data;
  if (event.source !== frame.contentWindow || event.origin !== SITE_ORIGIN) return;
  if (!data || data.source !== 'filamenthub-plugin') return;
  markCatalogReady();
  if (data.type === 'auth-state') {
    // label present = signed in: show the username + a sign-out button, and the
    // auth-only controls (Profile, Sync). On a fresh sign-in, return the catalog
    // to the active tab so the user isn't dropped on the app's default page.
    var loggedIn = !!data.label;
    document.getElementById('brand').textContent = data.label || 'Sign in';
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
  if (data.type === 'profile-changed' || data.type === 'recover-import') { startSyncPolling(); }
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
  title.textContent = 'Finish signing in in your web browser';
  title.style.cssText = 'font-weight:600;margin-bottom:8px;';
  var hint = document.createElement('div');
  hint.textContent = 'Your browser should have opened. If it did not, copy this ' +
    'link and open it in your browser, then return here.';
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
  copy.textContent = 'Copy link';
  copy.style.cssText = 'padding:6px 14px;border-radius:6px;cursor:pointer;' +
    'border:1px solid var(--orca-accent,#8b7cf8);background:transparent;' +
    'color:var(--orca-accent,#8b7cf8);font:inherit;';
  copy.addEventListener('click', function () {
    input.focus();
    input.select();
    var done = function () { copy.textContent = 'Copied'; };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(input.value).then(done, function () {
          try { document.execCommand('copy'); done(); } catch (e) {}
        });
      } else { document.execCommand('copy'); done(); }
    } catch (e) {}
  });
  var close = document.createElement('button');
  close.textContent = 'Cancel';
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
function stopSyncPolling() {
  if (syncPollTimer) { clearTimeout(syncPollTimer); syncPollTimer = null; }
}
function startSyncPolling() {
  if (hostPush) return;
  stopSyncPolling();
  syncDeadline = Date.now() + 30 * 1000;
  pollSyncOnce();
}
function pollSyncOnce() {
  if (Date.now() > syncDeadline) { stopSyncPolling(); return; }
  fetch(SYNC_STATUS_PATH, { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (st) {
      if (st.text) {
        stopSyncPolling();
        try {
          frame.contentWindow.postMessage(
            { source: 'filamenthub-plugin', type: 'sync-result', text: st.text }, SITE_ORIGIN);
        } catch (e) { /* iframe not ready */ }
        return;
      }
      syncPollTimer = setTimeout(pollSyncOnce, 1000);
    })
    .catch(function () { syncPollTimer = setTimeout(pollSyncOnce, 1500); });
}
document.getElementById('sync').addEventListener('click', function () {
  try { orca.postMessage({ source: 'filamenthub-plugin', type: 'sync' }); } catch (e) { /* bridge not ready */ }
  startSyncPolling();
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

function relayNote(text) {
  try {
    frame.contentWindow.postMessage(
      { source: 'filamenthub-plugin', type: 'sync-result', text: text }, SITE_ORIGIN);
  } catch (e) { /* iframe not ready */ }
}
function copyDiagnostics(text) {
  if (!text) {
    relayNote('The plugin log is empty — run Sync once, then copy it again.');
    return;
  }
  navigator.clipboard.writeText(text).then(function () {
    relayNote('Plugin log copied. Paste it into your beta feedback.');
  }, function () {
    relayNote('Could not copy the plugin log.');
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
      relayNote(data.text || '');
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
    .catch(function () { relayNote('Could not read the plugin log.'); });
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
""".replace("__EMBED_URL__", EMBED_URL).replace("__SITE_ORIGIN__", SITE_URL).replace(
    "__OAUTH_STATUS_PATH__", SHELL_SERVER.status_path()).replace(
    "__SYNC_STATUS_PATH__", SHELL_SERVER.sync_status_path()).replace(
    "__RECOVER_STATUS_PATH__", SHELL_SERVER.recover_status_path()).replace(
    "__SLICE_PARSE_PATH__", SHELL_SERVER.slice_parse_path()).replace(
    "__SLICE_ALIVE_PATH__", SHELL_SERVER.slice_alive_path()).replace(
    "__LOG_PATH__", SHELL_SERVER.log_path()).replace(
    "__DIAG_HIDDEN__", "" if DEV_CONTOUR else "hidden")


def render_page():
    return PAGE.replace("__HOST_UI_LANGUAGE__", host_ui_language())


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
        elif "printer_model =" in s:
            identity["printer_model"] = s.split("=", 1)[1].strip().strip('"')[:200]
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
        return False, "unreadable G-code"
    token = (load_saved_auth() or {}).get("accessToken") or ""
    if not token:
        return False, "not signed in"
    identity["file_name"] = (
        os.path.basename(output_name or gcode_path) or "print.gcode"
    )[:300]
    identity["source_key"] = _remember_slice_path(gcode_path, identity["file_name"])
    if host:
        identity["target_host"] = host[:50]
    status, _ = http_post_json("/orcaslicer/slices", token, {"slices": [identity]})
    if status != 200:
        return False, "HTTP %s" % status
    return True, identity["file_name"]


# The name the host matches against a process preset's slicing_pipeline_plugin.
SLICE_CAPABILITY_NAME = "filamenthub-slice-reporter"


class _SliceReporterMixin:
    def get_name(self):
        return SLICE_CAPABILITY_NAME

    def execute(self, ctx):
        step = getattr(ctx, "step", None)
        step_enum = getattr(_SLICING, "Step", None)
        post = getattr(step_enum, "psGCodePostProcess", None)
        if post is None:
            post = getattr(_SLICING, "psGCodePostProcess", None)
        if step is not None and post is not None and step != post:
            return orca.ExecutionResult.skipped("Not the G-code post-process step")

        path = getattr(ctx, "gcode_path", "") or ""
        if not path or not os.path.exists(path):
            return orca.ExecutionResult.skipped("G-code file not ready")

        try:
            sent, reason = report_slice(
                path,
                getattr(ctx, "output_name", "") or "",
                getattr(ctx, "host", "") or "",
            )
        except Exception as exc:
            # A failed report must never spoil an export the person asked for.
            fh_log("slice report failed: %s" % exc)
            return orca.ExecutionResult.skipped("Report failed")
        if not sent:
            return orca.ExecutionResult.skipped(reason)
        return orca.ExecutionResult.success("Reported %s to FilamentHub" % reason)


if _SLICE_CAPABILITY_BASE is not None:
    class FilamentHubSliceReporter(_SliceReporterMixin, _SLICE_CAPABILITY_BASE):
        pass
else:
    FilamentHubSliceReporter = None


# --------------------------------------------------------------------------- #
# The capability
# --------------------------------------------------------------------------- #
class FilamentHubCatalog(orca.script.ScriptPluginCapabilityBase):
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

    def _auto_sync(self, announce=False):
        # Reconcile presets automatically when the tab opens (and after sign-in),
        # so the user doesn't have to press Sync. Startup/auth refresh stays
        # silent; a user-initiated profile change reports its result immediately
        # so a following manual Sync cannot hide the preceding new/removed count.
        saved = load_saved_auth() or {}
        token = saved.get("accessToken") or ""
        if not token:
            return
        known = self._known_filament_preset_names()  # host read on the UI thread
        refresh_user_preset_folder()
        observations = observe_printer_presets()  # UI thread: read printer connection data
        active_filaments = scan_active_user_filaments()  # UI thread: loaded account's user presets
        host_profiles = self._host_profiles()  # UI thread: machine/process presets
        BACKGROUND_WORKER.submit(
            self._do_sync,
            token,
            known,
            announce,
            active_filaments,
            host_profiles,
            observations,
        )

    def execute(self):
        self._open()
        return orca.ExecutionResult.success("FilamentHub catalog opened.")

    def on_close(self):
        self.win = None
        # Stop serving the token-bearing shell while no window needs it; a
        # reopen spins up a fresh server with a new secret path.
        SHELL_SERVER.stop()

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

    def _host_profiles(self):
        # Machine/process presets of the loaded account, read on the UI thread and
        # handed to the worker that reports them to FilamentHub.
        return {kind: scan_user_profiles(kind) for kind in PROFILE_KINDS}

    def _deliver(self, message_type, **data):
        payload = {"source": "filamenthub-host", "type": message_type}
        payload.update(data)
        return post_window(self.win, payload)

    def _deliver_sync_result(self, text):
        if not self._deliver("sync-result", text=text):
            SHELL_SERVER.set_sync_result(text)

    def _deliver_recovery(self, items):
        if not self._deliver("recover-list", items=items):
            SHELL_SERVER.set_recover_items(items)

    def _deliver_slice_result(self, result):
        if not self._deliver("parsed-slice", result=result):
            SHELL_SERVER.set_slice_parse(result)

    def _do_check_slices(self, wanted, hook):
        alive = [key for key in wanted if slice_path_for_key(key)]
        if not self._deliver("slices-alive", keys=alive, hook=hook):
            SHELL_SERVER.set_slice_alive(alive, hook)

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

    def on_message(self, msg):
        if not isinstance(msg, dict):
            return
        if msg.get("source") != "filamenthub-plugin":
            return
        msg_type = msg.get("type")
        if msg_type == "host-ready":
            self._deliver("transport", push=True)
            if not getattr(self, "_session_sync_started", False):
                self._session_sync_started = True
                self._auto_sync()
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
            saved = load_saved_auth() or {}
            token = saved.get("accessToken") or ""
            known = self._known_filament_preset_names()  # host read on the UI thread
            refresh_user_preset_folder()
            active_filaments = scan_active_user_filaments()  # UI thread: loaded account's user presets
            host_profiles = self._host_profiles()  # UI thread: machine/process presets
            observations = observe_printer_presets()  # UI thread: printer connection data
            BACKGROUND_WORKER.submit(
                self._do_sync,
                token,
                known,
                True,
                active_filaments,
                host_profiles,
                observations,
            )
        elif msg_type == "auth-token":
            # Login / token refresh in the catalog — persist for session restore,
            # then reconcile presets automatically (silently).
            access = msg.get("accessToken") or ""
            if isinstance(access, str) and 0 < len(access) <= MAX_TOKEN_LENGTH:
                save_auth(access)
                self._auto_sync()
        elif msg_type == "profile-changed":
            # The catalog saved/removed a preset in the user's profile — reconcile
            # into the slicer automatically and report this user-initiated delta.
            self._auto_sync(announce=True)
        elif msg_type == "open-oauth":
            self._start_external_oauth(msg.get("provider"))
        elif msg_type == "auth-logout":
            clear_auth()
        elif msg_type == "recover":
            token = (load_saved_auth() or {}).get("accessToken") or ""
            BACKGROUND_WORKER.submit(self._do_recover_scan, token)
        elif msg_type == "recover-import":
            token = (load_saved_auth() or {}).get("accessToken") or ""
            BACKGROUND_WORKER.submit(self._do_recover_import, token, msg.get("names"))

    def _do_recover_scan(self, token):
        # Disk-only scan across every account + version backup; hand the list to the
        # embed (via loopback) to show its checkbox picker. Marks already-imported.
        candidates = scan_recovery_filaments()
        imported = load_imported_draft_ids()
        self._deliver_recovery(
            [{"name": c["name"], "imported": _draft_id(c["name"]) in imported} for c in candidates])

    def _do_recover_import(self, token, names):
        # Push only the presets the user checked in the embed picker as drafts.
        if not token or not isinstance(names, list) or not names:
            self._deliver_sync_result("Recovery: nothing selected.")
            return
        wanted = {str(n) for n in names}
        candidates = [c for c in scan_recovery_filaments() if c["name"] in wanted]
        sent_ids = push_filament_drafts(token, candidates)
        if sent_ids:
            imported = load_imported_draft_ids()
            for did in sent_ids:
                imported[did] = 1
            save_imported_draft_ids(imported)
        self._deliver_sync_result("Recovered %d preset(s) as drafts." % len(sent_ids))

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
        # Mirror how OrcaSlicer itself opens URLs: wxLaunchDefaultBrowser(), which
        # on Windows is ShellExecute("open", url). os.startfile is that same call
        # and works inside Orca's embedded Python, where webbrowser.open can report
        # success without actually launching anything. Fall back to webbrowser on
        # non-Windows or if startfile is unavailable/raises.
        opened = False
        try:
            startfile = getattr(os, "startfile", None)
            if startfile is not None:
                startfile(start_url)
                opened = True
            else:
                opened = bool(webbrowser.open(start_url))
        except Exception:
            try:
                opened = bool(webbrowser.open(start_url))
            except Exception:
                opened = False
        SHELL_SERVER.arm_oauth(nonce, opened, start_url)

    def _do_import(self, preset_id, token, known_presets):
        try:
            preset_id = int(preset_id)
        except (TypeError, ValueError):
            return
        if not token:
            orca.host.ui.message(
                "Please sign in to FilamentHub in the window, then import again.",
                title="FilamentHub", icon="warning")
            return
        try:
            status, body = http_get("/presets/%d/export/orcaslicer.json" % preset_id, token=token)
            if status == 401:
                clear_auth()
                orca.host.ui.message(
                    "Your FilamentHub session expired. Sign in again in the window.",
                    title="FilamentHub", icon="warning")
                return
            if status != 200:
                orca.host.ui.message("Export failed (HTTP %s)." % status,
                                     title="FilamentHub", icon="error")
                return

            profile = validate_filament_profile(json.loads(body.decode("utf-8")))
            ensure_parent_exists(profile, known_presets)
            ensure_filament_colour(profile)
            # Namespace the preset so the slicer groups it under "FilamentHub" in
            # the filament dropdown instead of burying it in User presets. The fork
            # groups by the "<provider>:<id>" prefix of bundle_id (same convention
            # the /orca/sync export uses); a plain user preset has no bundle_id.
            profile["bundle_id"] = "filamenthub:%d" % preset_id
            name = profile.get("name") or ("FilamentHub preset %d" % preset_id)
            ensure_bundle_metadata()
            target_dir = user_filament_dir()
            profile_path = preset_file_path(target_dir, name, preset_id)
            base = profile_path[:-len(".json")]
            write_json_atomic(profile_path, profile)
            remove_stale_preset_files(target_dir, preset_id, profile_path)

            # Best-effort .info sidecar (sync metadata; not required to load).
            try:
                istatus, info = http_get("/presets/%d/export/orcaslicer.info" % preset_id, token=token)
                if istatus == 200:
                    write_bytes_atomic(base + ".info", info)
            except Exception:
                pass

            if reload_host_presets():
                orca.host.ui.message(
                    "Imported '%s' — now in the FilamentHub group of the filament dropdown." % name,
                    title="FilamentHub", icon="info")
            else:
                orca.host.ui.message(
                    "Imported '%s' into your filament presets.\n\n"
                    "Restart OrcaSlicer to see it in the filament dropdown." % name,
                    title="FilamentHub", icon="info")
        except Exception as exc:
            orca.host.ui.message("Import failed: %s" % exc, title="FilamentHub", icon="error")

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
        base = profile_path[:-len(".json")]
        try:
            write_json_atomic(profile_path, profile)
        except OSError as exc:
            fh_log("pull %d FAILED: write error at %s: %r" % (pid, profile_path, exc))
            return None
        remove_stale_preset_files(folder, pid, profile_path)
        try:
            istatus, info = http_get("/presets/%d/export/orcaslicer.info" % pid, token=token)
            if istatus == 200:
                write_bytes_atomic(base + ".info", info)
        except Exception:
            pass
        return {"updated_at": (remote or {}).get("updated_at") or "",
                "hash": preset_content_hash(profile), "name": name}

    def _push_one(self, pid, token, local_entry, remote):
        # Send a locally-edited preset back to FilamentHub. The backend updates the
        # user's own preset or forks a non-owned one into a new user preset.
        profile = local_entry["profile"]
        item = {
            "fhub_id": pid,
            "name": (profile.get("name") or ("FilamentHub preset %d" % pid))[:200],
            "orcaslicer_settings": profile,
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
                 host_profiles=None, observations=None):
        if not token:
            if announce:
                orca.host.ui.message("Sign in to FilamentHub in the window, then Sync.",
                                     title="FilamentHub", icon="warning")
            return
        ensure_bundle_metadata()
        folder = user_filament_dir()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            pass
        status, body = http_get("/auth/my-presets", token=token)
        if status == 401:
            clear_auth()
            if announce:
                orca.host.ui.message("Your FilamentHub session expired. Sign in again in the window.",
                                     title="FilamentHub", icon="warning")
            return
        if status != 200:
            if announce:
                orca.host.ui.message("Sync failed (HTTP %s)." % status, title="FilamentHub", icon="error")
            return
        try:
            remote_items = (json.loads(body.decode("utf-8")) or {}).get("items") or []
        except ValueError:
            if announce:
                orca.host.ui.message("Sync failed: unexpected response.", title="FilamentHub", icon="error")
            return

        local = scan_local_fh_presets(folder)
        state = load_sync_state()
        fh_log("sync start: plugin %s, %d remote, %d local, folder=%s"
               % (PLUGIN_VERSION, len(remote_items), len(local), folder))
        pulled = updated = pushed = skipped = failed = renamed = 0
        for rp in remote_items:
            pid = rp.get("id")
            if not isinstance(pid, int):
                continue
            rec = state.get(str(pid)) or {}
            local_entry = local.get(pid)
            remote_updated = rp.get("updated_at") or ""
            if local_entry is None:
                res = self._pull_one(pid, token, known_presets, folder, rp)
                if res:
                    state[str(pid)] = res
                    pulled += 1
                else:
                    failed += 1
                continue
            if not rec:
                # No record for an existing local file: the state cache was lost
                # (plugin update wipes the dir). Rebuild by content — never assume
                # "remote is newer" here, that path deletes the local copy.
                recovered = recover_sync_record(pid, token, known_presets, local_entry, remote_updated)
                if recovered is None:
                    skipped += 1
                    continue
                if recovered is False:
                    res = self._push_one(pid, token, local_entry, rp)
                    if res:
                        state[str(pid)] = res
                        pushed += 1
                    else:
                        failed += 1
                    continue
                rec = recovered
                state[str(pid)] = rec
            local_changed = local_entry["hash"] != (rec.get("hash") or "")
            remote_newer = remote_updated > (rec.get("updated_at") or "")
            if local_changed:
                fh_log("preset %d: local hash %s != stored %s -> push" % (pid, (local_entry["hash"] or "")[:8], (rec.get("hash") or "")[:8]))
                res = self._push_one(pid, token, local_entry, rp)
                if res:
                    state[str(pid)] = res
                    pushed += 1
                else:
                    failed += 1
            elif remote_newer:
                # Update = idiomatic delete + add: drop the old preset (host + files)
                # first so the append reload picks up the new content.
                bare = os.path.basename(local_entry["path"])[:-len(".json")]
                if not remove_host_filament(bare):
                    try:
                        os.remove(local_entry["path"])
                    except OSError:
                        pass
                res = self._pull_one(pid, token, known_presets, folder, rp)
                if res:
                    state[str(pid)] = res
                    updated += 1
                else:
                    failed += 1
            else:
                # Content is up to date, but the file may still carry the legacy
                # `__fh_<id>` stem (shown verbatim in the dropdown) — move it to
                # the clean name; the host entry under the old name is dropped and
                # the reload below picks up the renamed file.
                name = local_entry["profile"].get("name") or ("FilamentHub preset %d" % pid)
                canonical = preset_file_path(folder, name, pid)
                if os.path.normcase(os.path.abspath(canonical)) != os.path.normcase(os.path.abspath(local_entry["path"])):
                    bare = os.path.basename(local_entry["path"])[:-len(".json")]
                    try:
                        os.replace(local_entry["path"], canonical)
                        info_old = local_entry["path"][:-len(".json")] + ".info"
                        if os.path.exists(info_old):
                            os.replace(info_old, canonical[:-len(".json")] + ".info")
                    except OSError:
                        pass
                    else:
                        try:
                            remove_host_filament(bare)
                        except Exception:
                            pass
                        renamed += 1
                skipped += 1

        # Removal sync: a preset that was synced before but is no longer in the
        # FilamentHub profile (unsubscribed / deleted there) is removed from the
        # local bundle — the plugin only ever deletes its own managed files.
        remote_ids = {rp.get("id") for rp in remote_items if isinstance(rp.get("id"), int)}
        removed = 0
        for pid, entry in list(local.items()):
            if pid in remote_ids or str(pid) not in state:
                continue
            bare = os.path.basename(entry["path"])[:-len(".json")]
            if not remove_host_filament(bare):  # live delete (also removes the files)
                for path in (entry["path"], entry["path"][:-len(".json")] + ".info"):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            state.pop(str(pid), None)
            removed += 1

        profile_parts = []
        for kind in PROFILE_KINDS:
            kind_sent, kind_failed = push_user_profiles(
                kind, token, (host_profiles or {}).get(kind) or [], state)
            bits = []
            if kind_sent:
                bits.append("%d sent to FilamentHub" % kind_sent)
            if kind_failed:
                bits.append("%d failed" % kind_failed)
            if bits:
                profile_parts.append("%s profiles: %s" % (PROFILE_KINDS[kind]["label"], ", ".join(bits)))
        save_sync_state(state)
        # After the profiles, never before: FilamentHub ties an observed printer to
        # its profile by the Orca preset id, so the profile has to exist first or
        # the printer stays unlinked until the next sync.
        send_printer_observations(token, observations)

        parts = []
        if pulled:
            parts.append("%d new" % pulled)
        if updated:
            parts.append("%d updated" % updated)
        if pushed:
            parts.append("%d sent to FilamentHub" % pushed)
        if removed:
            parts.append("%d removed" % removed)
        if renamed:
            parts.append("%d renamed" % renamed)
        if skipped:
            parts.append("%d up to date" % skipped)
        if failed:
            parts.append("%d failed" % failed)
        if active_filaments and _auto_import_enabled(token):
            imported = load_imported_draft_ids()
            fresh = [c for c in active_filaments if _draft_id(c["name"]) not in imported]
            sent_ids = push_filament_drafts(token, fresh) if fresh else []
            fh_log("auto draft import: %d fresh of %d, %d sent" % (len(fresh), len(active_filaments), len(sent_ids)))
            if sent_ids:
                for did in sent_ids:
                    imported[did] = 1
                save_imported_draft_ids(imported)
                parts.append("%d imported as drafts" % len(sent_ids))
        parts.extend(profile_parts)
        summary = ", ".join(parts) or "nothing to sync"
        fh_log("sync done: %s (pull=%d upd=%d push=%d rm=%d ren=%d skip=%d fail=%d)" % (summary, pulled, updated, pushed, removed, renamed, skipped, failed))
        note = ""
        if pulled or updated or removed or renamed:
            note = ("\n\nThe filament dropdown is up to date." if reload_host_presets()
                    else "\n\nRestart OrcaSlicer to apply the changes in the filament dropdown.")
        if announce:
            self._deliver_sync_result(
                ("Sync complete: %s.%s" % (summary, note)).replace("\n\n", " ")
            )


@orca.plugin
class FilamentHubPlugin(orca.base):
    def register_capabilities(self):
        configure_plugin_storage()
        orca.register_capability(FilamentHubCatalog)
        if FilamentHubSliceReporter is not None:
            orca.register_capability(FilamentHubSliceReporter)
