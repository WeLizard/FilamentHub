# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub"
# name = "FilamentHub"
# description = "Browse the FilamentHub brand/material catalog and import community-rated filament presets."
# author = "FilamentHub"
# version = "0.2.0"
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
# The shell page — a full-window iframe plus a relay that forwards the catalog's
# postMessage up through window.orca to Python. Self-contained; the iframe carries
# our own site styling, so no host theme is needed here.
# --------------------------------------------------------------------------- #
PAGE = r"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  html, body { margin:0; height:100%; background:var(--orca-bg,#1e1e2e); }
  iframe { border:0; width:100%; height:100vh; display:block; }
</style></head>
<body>
  <iframe id="fh" src="__EMBED_URL__" allow="clipboard-write"></iframe>
<script>
'use strict';
// Relay catalog -> plugin. Only our namespaced messages are forwarded.
window.addEventListener('message', function (event) {
  var data = event.data;
  if (!data || data.source !== 'filamenthub-plugin') return;
  try { orca.postMessage(data); } catch (e) { /* bridge not ready */ }
});
</script>
</body>
</html>
""".replace("__EMBED_URL__", EMBED_URL)


# --------------------------------------------------------------------------- #
# The capability
# --------------------------------------------------------------------------- #
class FilamentHubCatalog(orca.script.ScriptPluginCapabilityBase):
    win = None

    def get_name(self):
        return "FilamentHub Catalog"

    def execute(self):
        # A second Run lands on the same instance: close any stale window first.
        if self.win is not None and self.win.is_open():
            self.win.close()
        self.win = orca.host.ui.create_window(
            title="FilamentHub",
            html=PAGE,
            width=1080,
            height=760,
            on_message=self.on_message,
            on_close=self.on_close,
        )
        return orca.ExecutionResult.success("FilamentHub catalog opened.")

    def on_close(self):
        self.win = None

    # on_message runs on the UI thread — offload network + disk work to a worker.
    def on_message(self, msg):
        msg = msg or {}
        if msg.get("source") != "filamenthub-plugin":
            return
        if msg.get("type") == "import-preset":
            preset_id = msg.get("presetId")
            token = msg.get("token") or ""
            threading.Thread(target=self._do_import, args=(preset_id, token), daemon=True).start()

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
