# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub"
# name = "FilamentHub"
# description = "Browse and sync community-rated filament profiles from FilamentHub, with spool inventory and print-cost tools."
# author = "FilamentHub"
# version = "0.1.0-alpha.4"
#
# # Proposed forward-looking key (see README gap / PR #14530 feedback). The current
# # host reads only name/description/author/version/dependencies and ignores unknown
# # keys, so declaring this today is harmless and documents intent.
# network = ["filamenthub.ru", "*.filamenthub.ru"]
# ///
"""FilamentHub plugin for OrcaSlicer's Python plugin system (PR #14530).

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
Python persists them in .auth.json next to the plugin — the shell restores the
session (embed-ready -> auth-restore) when the window reopens, because the
iframe's own storage is partitioned and dies with the window.

  iframe (React) --window.parent.postMessage({source:'filamenthub-plugin',...})-->
      shell window --orca.postMessage(...)--> Python on_message
          --GET /presets/{id}/export/orcaslicer.json (Bearer token from the page)-->
              write {data_dir}/user/<active>/_local/filamenthub/filament/<name>.json
                  --> host restart dialog

Runtime surface used (confirmed against upstream/feat/plugin-feature):
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
import secrets
import ssl
import threading
import urllib.error
import urllib.request

import orca

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
PLUGIN_VERSION = "0.1.0-alpha.4"
SITE_URL = "https://filamenthub.ru"
EMBED_URL = SITE_URL + "/embed/catalog"
API_BASE = SITE_URL + "/api/v1"
HTTP_TIMEOUT = 20
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_TOKEN_LENGTH = 8192
MAX_FILENAME_LENGTH = 120
_SSL_CTX = ssl.create_default_context()


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


def resolve_user_preset_folder():
    """Name of the active user's preset folder under {data_dir}/user/.

    OrcaSlicer stores user presets in user/<preset_folder>/; preset_folder is the
    signed-in account id (a GUID) or 'default' when signed out, recorded in
    OrcaSlicer.conf under "app". Writing to the wrong folder means the preset is
    never loaded — the dropdown only shows presets from the active user's folder.
    The config file has a trailing "# MD5 checksum" line, so decode just the JSON
    prefix rather than json.load the whole thing.
    """
    conf = os.path.join(DATA_DIR, "OrcaSlicer.conf")
    try:
        with open(conf, "r", encoding="utf-8-sig") as fh:
            obj, _ = json.JSONDecoder().raw_decode(fh.read().lstrip())
        folder = (obj.get("app") or {}).get("preset_folder")
        if folder:
            return folder
    except (OSError, ValueError):
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
# Tab icon. Embedded here rather than shipped as a sibling file so it survives a
# single-file install: OrcaSlicer copies only the .py, not adjacent assets. It is
# materialized next to the plugin on first use and handed to create_panel by path.
ICON_PATH = os.path.join(PLUGIN_DIR, "filamenthub.svg")
ICON_SVG = r'''<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"><path d="M8.19,2.15c-3.11.84-5.49,3.22-6.15,6.18-.7,3.16.86,5.68,1.21,6.21" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-miterlimit:10"/><line x1="8.19" y1="10" x2="1.87" y2="10" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-miterlimit:10"/><line x1="10.95" y1="2.15" x2="10.95" y2="17.85" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-miterlimit:10"/><path d="M16.91,6c.37.65,1.08,2.08,1.09,4.01.02,2.28-.94,3.92-1.35,4.54" style="fill:none;stroke:#fff;stroke-linecap:round;stroke-miterlimit:10"/><line x1="10.95" y1="10" x2="18" y2="10" style="fill:none;stroke:#fff;stroke-miterlimit:10"/></svg>'''


def ensure_icon():
    """Write the embedded tab icon next to the plugin if it's absent, and return
    its path — or "" if it can't be written, so the host uses its default icon."""
    try:
        if not os.path.exists(ICON_PATH):
            write_bytes_atomic(ICON_PATH, ICON_SVG.encode("utf-8"))
        return ICON_PATH
    except OSError:
        return ""


# Session tokens live next to the plugin (inside data_dir, the allowed write
# root) so signing in survives window/OrcaSlicer restarts — the iframe's own
# storage is partitioned and dies with the window. Same role as the fork's
# AppConfig token storage.
AUTH_FILE = os.path.join(PLUGIN_DIR, ".auth.json")


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
        self._html = b""
        self._path = ""

    def url_for(self, html):
        self._html = html.encode("utf-8")
        if self._server is None:
            self._path = "/" + secrets.token_urlsafe(32)
            owner = self

            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path != owner._path:
                        self.send_error(404)
                        return
                    body = owner._html
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args):
                    pass  # keep the secret path out of stderr

            self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return "http://127.0.0.1:%d%s" % (self._server.server_address[1], self._path)

    def stop(self):
        server, self._server = self._server, None
        if server is not None:
            threading.Thread(target=server.shutdown, daemon=True).start()


SHELL_SERVER = ShellServer()


def load_saved_auth():
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
  iframe { flex:1 1 auto; border:0; width:100%; display:block; }
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
  </div>
  <iframe id="fh" src="__EMBED_URL__" allow="clipboard-write"></iframe>
<script>
'use strict';
var SITE_ORIGIN = '__SITE_ORIGIN__';
var RESTORE_AUTH = __RESTORE_AUTH__;
var frame = document.getElementById('fh');
var wasLoggedIn = false;

// Auth-only toolbar controls: Profile and Sync only make sense when signed in.
// When signed out, the "FilamentHub" brand label doubles as a sign-in trigger.
function setAuthControls(loggedIn) {
  var profileBtn = document.querySelector('#bar button[data-path="/profile"]');
  if (profileBtn) profileBtn.style.display = loggedIn ? '' : 'none';
  document.getElementById('sync').style.display = loggedIn ? 'inline-block' : 'none';
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

// Catalog -> shell. auth-state updates the toolbar label, embed-ready answers
// with saved tokens (session restore); everything else relays to Python.
window.addEventListener('message', function (event) {
  var data = event.data;
  if (event.source !== frame.contentWindow || event.origin !== SITE_ORIGIN) return;
  if (!data || data.source !== 'filamenthub-plugin') return;
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
  if (data.type === 'embed-ready') {
    if (RESTORE_AUTH && RESTORE_AUTH.accessToken) {
      try {
        frame.contentWindow.postMessage(
          { source: 'filamenthub-plugin', type: 'auth-restore',
            accessToken: RESTORE_AUTH.accessToken, refreshToken: RESTORE_AUTH.refreshToken || '' },
          SITE_ORIGIN);
      } catch (e) { /* iframe not ready */ }
    }
    return;
  }
  try { orca.postMessage(data); } catch (e) { /* bridge not ready */ }
});

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

// Sync: reconcile FilamentHub presets with the slicer, both directions. Runs in
// Python; a summary dialog reports the result.
document.getElementById('sync').addEventListener('click', function () {
  try { orca.postMessage({ source: 'filamenthub-plugin', type: 'sync' }); } catch (e) { /* bridge not ready */ }
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
""".replace("__EMBED_URL__", EMBED_URL).replace("__SITE_ORIGIN__", SITE_URL)


# --------------------------------------------------------------------------- #
# The capability
# --------------------------------------------------------------------------- #
class FilamentHubCatalog(orca.script.ScriptPluginCapabilityBase):
    win = None

    def get_name(self):
        return "FilamentHub Catalog"

    def _supports_panel(self):
        # Docked main-window tab where the host offers it (our create_panel
        # prototype / future upstream API); floating window on stock builds.
        return getattr(orca.host.ui, "create_panel", None)

    def _open(self):
        # Idempotent: if the surface is already open, keep it (a docked tab must
        # not spawn duplicates on repeated Run / on_load).
        if self.win is not None and self.win.is_open():
            return False
        # Saved session tokens (if any) are baked into the shell page; it hands
        # them to the catalog when the SPA reports embed-ready.
        html = PAGE.replace("__RESTORE_AUTH__", json.dumps(load_saved_auth()))
        # Hop from the host's opaque-origin SetPage document onto the loopback
        # server, so the shell gains a real origin the site CSP can allow.
        shell_url = SHELL_SERVER.url_for(html)
        html = (
            "<!DOCTYPE html><html><body><script>location.replace("
            + json.dumps(shell_url)
            + ");</script></body></html>"
        )
        create_panel = self._supports_panel()
        if create_panel is not None:
            self.win = create_panel(
                title="FilamentHub",
                html=html,
                on_message=self.on_message,
                on_close=self.on_close,
                icon=ensure_icon(),
            )
        else:
            self.win = orca.host.ui.create_window(
                title="FilamentHub",
                html=html,
                width=1080,
                height=760,
                on_message=self.on_message,
                on_close=self.on_close,
            )
        return True

    def on_load(self):
        # Auto-mount the docked tab when the plugin is enabled (incl. at startup),
        # so it behaves like a native tab. Only for the docked surface — we do not
        # pop a floating window unprompted on stock builds.
        if self._supports_panel() is not None:
            try:
                self._open()
            except Exception:
                pass  # main window not ready yet; the user can still Run it
        self._auto_sync()  # pull the signed-in user's presets on open, silently

    def _auto_sync(self):
        # Reconcile presets automatically when the tab opens (and after sign-in),
        # so the user doesn't have to press Sync. Silent: no dialogs, just a live
        # reload if anything changed. The manual Sync button still reports results.
        saved = load_saved_auth() or {}
        token = saved.get("accessToken") or ""
        if not token:
            return
        known = self._known_filament_preset_names()  # host read on the UI thread
        threading.Thread(target=self._do_sync, args=(token, known, False), daemon=True).start()

    def execute(self):
        created = self._open()
        if self._supports_panel() is not None:
            return orca.ExecutionResult.success(
                "FilamentHub catalog docked." if created else "FilamentHub catalog is already open.")
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

    # on_message runs on the UI thread — offload network + disk work to a worker.
    def on_message(self, msg):
        if not isinstance(msg, dict):
            return
        if msg.get("source") != "filamenthub-plugin":
            return
        msg_type = msg.get("type")
        if msg_type == "import-preset":
            preset_id = msg.get("presetId")
            token = msg.get("token") or ""
            if not isinstance(token, str) or len(token) > MAX_TOKEN_LENGTH:
                return
            known = self._known_filament_preset_names()  # host read on the UI thread
            threading.Thread(target=self._do_import, args=(preset_id, token, known), daemon=True).start()
        elif msg_type == "sync":
            saved = load_saved_auth() or {}
            token = saved.get("accessToken") or ""
            known = self._known_filament_preset_names()  # host read on the UI thread
            threading.Thread(target=self._do_sync, args=(token, known), daemon=True).start()
        elif msg_type == "auth-token":
            # Login / token refresh in the catalog — persist for session restore,
            # then reconcile presets automatically (silently).
            access = msg.get("accessToken") or ""
            if isinstance(access, str) and 0 < len(access) <= MAX_TOKEN_LENGTH:
                save_auth(access)
                self._auto_sync()
        elif msg_type == "profile-changed":
            # The catalog saved/removed a preset in the user's profile — reconcile
            # into the slicer automatically (silently), no manual Sync needed.
            self._auto_sync()
        elif msg_type == "auth-logout":
            clear_auth()

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
            return None
        try:
            profile = validate_filament_profile(json.loads(body.decode("utf-8")))
        except (TypeError, ValueError):
            return None
        ensure_parent_exists(profile, known_presets)
        ensure_filament_colour(profile)
        profile["bundle_id"] = "%s%d" % (BUNDLE_PREFIX, pid)
        name = profile.get("name") or ("FilamentHub preset %d" % pid)
        profile_path = preset_file_path(folder, name, pid)
        base = profile_path[:-len(".json")]
        try:
            write_json_atomic(profile_path, profile)
        except OSError:
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
            return None
        return {"updated_at": (remote or {}).get("updated_at") or "",
                "hash": local_entry["hash"], "name": profile.get("name") or ""}

    def _do_sync(self, token, known_presets, announce=True):
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
        save_sync_state(state)

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
        summary = ", ".join(parts) or "nothing to sync"
        note = ""
        if pulled or updated or removed or renamed:
            note = ("\n\nThe filament dropdown is up to date." if reload_host_presets()
                    else "\n\nRestart OrcaSlicer to apply the changes in the filament dropdown.")
        if announce:
            orca.host.ui.message("Sync complete: %s.%s" % (summary, note), title="FilamentHub", icon="info")


@orca.plugin
class FilamentHubPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(FilamentHubCatalog)
