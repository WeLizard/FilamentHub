# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub"
# name = "FilamentHub"
# description = "Browse the FilamentHub brand/material catalog and import community-rated filament presets."
# author = "FilamentHub"
# version = "0.5.0"
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
              write {data_dir}/user/default/filament/<name>.json --> host restart dialog

Runtime surface used (confirmed against upstream/feat/plugin-feature):
  * orca.script.ScriptPluginCapabilityBase.execute()       — entry point
  * orca.host.ui.create_window(html, on_message, on_close)  — the shell window
  * orca.host.ui.message(...)                               — restart notice
  * the injected window.orca bridge (PluginWebDialog.cpp:ORCA_BRIDGE_JS)

Login/token: the user signs in inside the iframe on our own site (normal flow).
The page includes its access token in the import message, and Python uses it as a
Bearer credential for the export — the plugin keeps no credentials of its own.
"""

import json
import os
import ssl
import threading
import urllib.error
import urllib.request

import orca

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
SITE_URL = "https://filamenthub.ru"
EMBED_URL = SITE_URL + "/embed/catalog"
API_BASE = SITE_URL + "/api/v1"
HTTP_TIMEOUT = 20
_SSL_CTX = ssl.create_default_context()


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
# OrcaSlicer user filament preset folder: {data_dir}/user/default/filament/
USER_FILAMENT_DIR = os.path.join(DATA_DIR, "user", "default", "filament")
# Session tokens live next to the plugin (inside data_dir, the allowed write
# root) so signing in survives window/OrcaSlicer restarts — the iframe's own
# storage is partitioned and dies with the window. Same role as the fork's
# AppConfig token storage.
AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".auth.json")


def load_saved_auth():
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get("accessToken"):
            return {"accessToken": data["accessToken"], "refreshToken": data.get("refreshToken", "")}
    except (OSError, ValueError):
        pass
    return None


def save_auth(access_token, refresh_token):
    try:
        with open(AUTH_FILE, "w", encoding="utf-8") as fh:
            json.dump({"accessToken": access_token, "refreshToken": refresh_token or ""}, fh)
    except OSError:
        pass


def clear_auth():
    try:
        os.remove(AUTH_FILE)
    except OSError:
        pass


def safe_filename(name):
    cleaned = "".join("_" if ch in '<>:"/\\|?*' else ch for ch in (name or "preset")).strip(" _")
    return cleaned or "preset"


# --------------------------------------------------------------------------- #
# HTTP (stdlib only). Returns (status, bytes).
# --------------------------------------------------------------------------- #
def http_get(path, token=None):
    headers = {"Accept": "application/json", "User-Agent": "FilamentHub-OrcaPlugin/0.2"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API_BASE + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=_SSL_CTX) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


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
      <span id="brand">FilamentHub</span>
      <button id="logout" title="Sign out">Sign out</button>
    </span>
    <button data-path="/" class="active">Catalog</button>
    <button data-path="/profile">Profile</button>
    <button data-path="/wiki">Wiki</button>
  </div>
  <iframe id="fh" src="__EMBED_URL__" allow="clipboard-write"></iframe>
<script>
'use strict';
var SITE_ORIGIN = '__SITE_ORIGIN__';
var RESTORE_AUTH = __RESTORE_AUTH__;
var frame = document.getElementById('fh');

// Catalog -> shell. auth-state updates the toolbar label, embed-ready answers
// with saved tokens (session restore); everything else relays to Python.
window.addEventListener('message', function (event) {
  var data = event.data;
  if (!data || data.source !== 'filamenthub-plugin') return;
  if (data.type === 'auth-state') {
    // label present = signed in: show the username + a sign-out button.
    document.getElementById('brand').textContent = data.label || 'FilamentHub';
    document.getElementById('logout').style.display = data.label ? 'inline-block' : 'none';
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
        create_panel = self._supports_panel()
        if create_panel is not None:
            self.win = create_panel(
                title="FilamentHub",
                html=html,
                on_message=self.on_message,
                on_close=self.on_close,
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

    def execute(self):
        created = self._open()
        if self._supports_panel() is not None:
            return orca.ExecutionResult.success(
                "FilamentHub catalog docked." if created else "FilamentHub catalog is already open.")
        return orca.ExecutionResult.success("FilamentHub catalog opened.")

    def on_close(self):
        self.win = None

    # on_message runs on the UI thread — offload network + disk work to a worker.
    def on_message(self, msg):
        msg = msg or {}
        if msg.get("source") != "filamenthub-plugin":
            return
        msg_type = msg.get("type")
        if msg_type == "import-preset":
            preset_id = msg.get("presetId")
            token = msg.get("token") or ""
            threading.Thread(target=self._do_import, args=(preset_id, token), daemon=True).start()
        elif msg_type == "auth-token":
            # Login / token refresh in the catalog — persist for session restore.
            access = msg.get("accessToken") or ""
            if access:
                save_auth(access, msg.get("refreshToken") or "")
        elif msg_type == "auth-logout":
            clear_auth()

    def _do_import(self, preset_id, token):
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
                orca.host.ui.message(
                    "Your FilamentHub session expired. Sign in again in the window.",
                    title="FilamentHub", icon="warning")
                return
            if status != 200:
                orca.host.ui.message("Export failed (HTTP %s)." % status,
                                     title="FilamentHub", icon="error")
                return

            profile = json.loads(body.decode("utf-8"))
            name = profile.get("name") or ("FilamentHub preset %d" % preset_id)
            os.makedirs(USER_FILAMENT_DIR, exist_ok=True)
            base = os.path.join(USER_FILAMENT_DIR, safe_filename(name))
            with open(base + ".json", "w", encoding="utf-8") as fh:
                json.dump(profile, fh, ensure_ascii=False, indent=2)

            # Best-effort .info sidecar (sync metadata; not required to load).
            try:
                istatus, info = http_get("/presets/%d/export/orcaslicer.info" % preset_id, token=token)
                if istatus == 200:
                    with open(base + ".info", "wb") as fh:
                        fh.write(info)
            except Exception:
                pass

            orca.host.ui.message(
                "Imported '%s' into your filament presets.\n\n"
                "Restart OrcaSlicer to see it in the filament dropdown." % name,
                title="FilamentHub", icon="info")
        except Exception as exc:
            orca.host.ui.message("Import failed: %s" % exc, title="FilamentHub", icon="error")


@orca.plugin
class FilamentHubPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(FilamentHubCatalog)
