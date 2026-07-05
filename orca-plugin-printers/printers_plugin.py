# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "printers"
# name = "Printers"
# description = "Cross-vendor dashboard of your networked 3D printers: live status, temperatures and print progress, with one click to each printer's web interface."
# author = "FilamentHub"
# version = "0.1.0"
#
# # Forward-looking: printers live on user-chosen LAN addresses that no static
# # manifest allow-list can enumerate, so this declares intent for a future
# # "local-network" permission class (see PR #14530 feedback). Ignored today.
# network = ["local-network"]
# ///
"""Printers — a cross-vendor printer dashboard plugin for OrcaSlicer (PR #14530).

A second, independent plugin built on the SAME extension surface as the
FilamentHub catalog (orca.host.ui.create_panel): it docks as its own main-window
tab. Different domain, same generic mechanism — the point being that the host's
panel contribution works for any plugin, not one bespoke integration.

What it does today, on stock plugin-runtime capabilities (no new host API):
  * create_panel(...) -> a docked tab with a self-contained, host-themed page.
  * The page lists the user's printers as tiles; the plugin polls each over HTTP
    (Moonraker / OctoPrint / a generic reachability ping) on a worker thread and
    pushes status + temperatures + print progress back to the page.
  * "Open" swaps the tile view for an <iframe> of that printer's web UI
    (Mainsail/Fluidd/OctoPrint are framable on the LAN), so the user reaches any
    printer without leaving OrcaSlicer.
  * Printers are added/removed in the page and stored in printers.json next to
    the plugin (inside data_dir, the allowed write root).

Unlike the FilamentHub catalog (which embeds our own themed site), this page is
native HTML and deliberately uses the host --orca-* theme variables so it looks
like part of OrcaSlicer in both light and dark mode.
"""

import json
import os
import ssl
import threading
import urllib.error
import urllib.request

import orca

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PRINTERS_FILE = os.path.join(PLUGIN_DIR, "printers.json")
ICON_PATH = os.path.join(PLUGIN_DIR, "printers.svg")
HTTP_TIMEOUT = 6
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE  # LAN printers routinely use self-signed / plain HTTP


# --------------------------------------------------------------------------- #
# Printer store (printers.json next to the plugin)
# --------------------------------------------------------------------------- #
def load_printers():
    try:
        with open(PRINTERS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_printers(printers):
    try:
        with open(PRINTERS_FILE, "w", encoding="utf-8") as fh:
            json.dump(printers, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def normalize_url(url):
    url = (url or "").strip().rstrip("/")
    if url and not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url
    return url


# --------------------------------------------------------------------------- #
# HTTP polling (stdlib only). Each backend maps its native status onto a common
# shape: {online, state, nozzle, bed, target_nozzle, target_bed, progress}.
# --------------------------------------------------------------------------- #
def _get_json(url, timeout=HTTP_TIMEOUT):
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def poll_moonraker(base):
    query = "/printer/objects/query?extruder&heater_bed&print_stats&display_status"
    data = _get_json(base + query)
    result = data.get("result", {}).get("status", {})
    extruder = result.get("extruder", {})
    bed = result.get("heater_bed", {})
    print_stats = result.get("print_stats", {})
    display = result.get("display_status", {})
    return {
        "online": True,
        "state": print_stats.get("state", "standby"),
        "nozzle": extruder.get("temperature"),
        "target_nozzle": extruder.get("target"),
        "bed": bed.get("temperature"),
        "target_bed": bed.get("target"),
        "progress": round((display.get("progress") or 0.0) * 100),
    }


def poll_octoprint(base):
    printer = _get_json(base + "/api/printer")
    temps = printer.get("temperature", {})
    tool0 = temps.get("tool0", {})
    bed = temps.get("bed", {})
    state = printer.get("state", {}).get("text", "Operational")
    progress = 0
    try:
        job = _get_json(base + "/api/job")
        progress = round(job.get("progress", {}).get("completion") or 0)
    except Exception:
        pass
    return {
        "online": True,
        "state": state,
        "nozzle": tool0.get("actual"),
        "target_nozzle": tool0.get("target"),
        "bed": bed.get("actual"),
        "target_bed": bed.get("target"),
        "progress": progress,
    }


def poll_generic(base):
    # No known API: just confirm the host answers, so the tile shows reachable.
    req = urllib.request.Request(base, method="GET")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=_SSL_CTX):
        return {"online": True, "state": "reachable", "nozzle": None, "target_nozzle": None,
                "bed": None, "target_bed": None, "progress": None}


def poll_printer(printer):
    base = normalize_url(printer.get("url"))
    kind = (printer.get("type") or "moonraker").lower()
    try:
        if kind == "moonraker":
            return poll_moonraker(base)
        if kind == "octoprint":
            return poll_octoprint(base)
        return poll_generic(base)
    except Exception as exc:
        return {"online": False, "state": "offline", "error": str(exc),
                "nozzle": None, "target_nozzle": None, "bed": None, "target_bed": None,
                "progress": None}


# --------------------------------------------------------------------------- #
# The page — native, host-themed. Renders tiles from data the plugin pushes and
# lets the user add/remove printers and open a printer's web UI in an iframe.
# --------------------------------------------------------------------------- #
PAGE = r"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  html, body { margin:0; height:100%; }
  body { display:flex; flex-direction:column; background:var(--orca-bg,#1e1e2e);
         color:var(--orca-fg,#e0e0e0); font-family:var(--orca-font,sans-serif); }
  #bar { flex:0 0 auto; display:flex; align-items:center; gap:8px; padding:8px 12px;
         border-bottom:1px solid var(--orca-border,#3c3c4c); }
  #bar h1 { margin:0; margin-right:auto; font-size:14px; font-weight:600; }
  #bar input { font:inherit; font-size:12px; padding:4px 8px;
               background:var(--orca-bg,#1e1e2e); color:var(--orca-fg,#e0e0e0);
               border:1px solid var(--orca-border,#3c3c4c); border-radius:4px; }
  #bar select { font:inherit; font-size:12px; padding:4px 6px;
                background:var(--orca-bg,#1e1e2e); color:var(--orca-fg,#e0e0e0);
                border:1px solid var(--orca-border,#3c3c4c); border-radius:4px; }
  button { font:inherit; font-size:12px; cursor:pointer; padding:4px 12px; border-radius:4px;
           background:var(--orca-accent,#009688); color:var(--orca-accent-fg,#fff);
           border:1px solid var(--orca-accent,#009688); }
  button.ghost { background:transparent; color:var(--orca-fg,#e0e0e0);
                 border-color:var(--orca-border,#3c3c4c); }
  #grid { flex:1 1 auto; overflow:auto; padding:12px;
          display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:12px;
          align-content:start; }
  .tile { border:1px solid var(--orca-border,#3c3c4c); border-radius:8px; padding:12px;
          display:flex; flex-direction:column; gap:8px; }
  .tile .top { display:flex; align-items:center; gap:8px; }
  .dot { width:9px; height:9px; border-radius:50%; background:#888; flex:0 0 auto; }
  .dot.on { background:#3fbf6f; } .dot.off { background:#c0504d; }
  .tile .name { font-weight:600; margin-right:auto; }
  .tile .state { font-size:11px; color:var(--orca-muted,#a0a0a0); text-transform:capitalize; }
  .temps { display:flex; gap:14px; font-size:12px; }
  .temps b { font-weight:600; }
  .bar { height:6px; border-radius:3px; background:var(--orca-border,#3c3c4c); overflow:hidden; }
  .bar > i { display:block; height:100%; background:var(--orca-accent,#009688); }
  .row { display:flex; gap:6px; }
  .empty { color:var(--orca-muted,#a0a0a0); padding:24px; text-align:center; }
  #viewer { flex:1 1 auto; display:none; flex-direction:column; }
  #viewer .vbar { display:flex; align-items:center; gap:8px; padding:6px 12px;
                  border-bottom:1px solid var(--orca-border,#3c3c4c); }
  #viewer iframe { flex:1 1 auto; border:0; width:100%; }
</style></head>
<body>
  <div id="bar">
    <h1>Printers</h1>
    <input id="f-name" placeholder="Name" size="10">
    <input id="f-url" placeholder="192.168.0.42" size="16">
    <select id="f-type">
      <option value="moonraker">Moonraker</option>
      <option value="octoprint">OctoPrint</option>
      <option value="generic">Other</option>
    </select>
    <button id="add">Add</button>
    <button id="refresh" class="ghost">Refresh</button>
  </div>
  <div id="grid"><div class="empty">Loading…</div></div>
  <div id="viewer">
    <div class="vbar"><button id="back" class="ghost">&larr; Back</button><span id="vtitle"></span></div>
    <iframe id="vframe"></iframe>
  </div>
<script>
'use strict';
var grid = document.getElementById('grid');
var viewer = document.getElementById('viewer');

function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function temp(v){ return v == null ? '—' : Math.round(v) + '°'; }

function render(printers){
  grid.innerHTML = '';
  if (!printers.length){ grid.innerHTML = '<div class="empty">No printers yet. Add one above.</div>'; return; }
  printers.forEach(function(p){
    var s = p.status || {};
    var tile = document.createElement('div'); tile.className = 'tile';
    var prog = (s.progress == null) ? '' :
      '<div class="bar"><i style="width:' + s.progress + '%"></i></div>';
    tile.innerHTML =
      '<div class="top"><span class="dot ' + (s.online ? 'on' : 'off') + '"></span>' +
      '<span class="name">' + esc(p.name || p.url) + '</span>' +
      '<span class="state">' + esc(s.state || (s.online ? 'online' : 'offline')) + '</span></div>' +
      '<div class="temps"><span>Nozzle <b>' + temp(s.nozzle) + '</b>' +
      (s.target_nozzle ? '/' + temp(s.target_nozzle) : '') + '</span>' +
      '<span>Bed <b>' + temp(s.bed) + '</b>' +
      (s.target_bed ? '/' + temp(s.target_bed) : '') + '</span></div>' + prog +
      '<div class="row"><button class="open ghost">Open</button>' +
      '<button class="remove ghost">Remove</button></div>';
    tile.querySelector('.open').addEventListener('click', function(){ openPrinter(p); });
    tile.querySelector('.remove').addEventListener('click', function(){
      orca.postMessage({ type:'remove', id:p.id }); });
    grid.appendChild(tile);
  });
}

function openPrinter(p){
  document.getElementById('vtitle').textContent = p.name || p.url;
  document.getElementById('vframe').src = p.url;
  viewer.style.display = 'flex';
}
document.getElementById('back').addEventListener('click', function(){
  viewer.style.display = 'none'; document.getElementById('vframe').src = 'about:blank'; });

document.getElementById('add').addEventListener('click', function(){
  var name = document.getElementById('f-name').value.trim();
  var url = document.getElementById('f-url').value.trim();
  var type = document.getElementById('f-type').value;
  if (!url) return;
  orca.postMessage({ type:'add', name:name, url:url, kind:type });
  document.getElementById('f-name').value = ''; document.getElementById('f-url').value = '';
});
document.getElementById('refresh').addEventListener('click', function(){
  orca.postMessage({ type:'refresh' }); });

// Plugin -> page: full printer list with fresh status.
orca.onMessage(function(data){ if (data && data.printers) render(data.printers); });
orca.postMessage({ type:'ready' });
</script>
</body>
</html>
"""


class PrintersDashboard(orca.script.ScriptPluginCapabilityBase):
    win = None

    def get_name(self):
        return "Printers"

    def _supports_panel(self):
        return getattr(orca.host.ui, "create_panel", None)

    def _open(self):
        if self.win is not None and self.win.is_open():
            return False
        create_panel = self._supports_panel()
        if create_panel is not None:
            self.win = create_panel(
                title="Printers", html=PAGE,
                on_message=self.on_message, on_close=self.on_close,
                icon=ICON_PATH if os.path.exists(ICON_PATH) else "",
            )
        else:
            self.win = orca.host.ui.create_window(
                title="Printers", html=PAGE, width=980, height=680,
                on_message=self.on_message, on_close=self.on_close,
            )
        return True

    def on_load(self):
        if self._supports_panel() is not None:
            try:
                self._open()
            except Exception:
                pass

    def execute(self):
        self._open()
        return orca.ExecutionResult.success("Printers dashboard opened.")

    def on_close(self):
        self.win = None

    # on_message runs on the UI thread — push work to a worker and post results back.
    def on_message(self, msg):
        msg = msg or {}
        kind = msg.get("type")
        if kind == "ready" or kind == "refresh":
            threading.Thread(target=self._push_status, daemon=True).start()
        elif kind == "add":
            printers = load_printers()
            new_id = (max([p.get("id", 0) for p in printers], default=0) + 1)
            printers.append({
                "id": new_id,
                "name": msg.get("name") or msg.get("url"),
                "url": normalize_url(msg.get("url")),
                "type": msg.get("kind") or "moonraker",
            })
            save_printers(printers)
            threading.Thread(target=self._push_status, daemon=True).start()
        elif kind == "remove":
            printers = [p for p in load_printers() if p.get("id") != msg.get("id")]
            save_printers(printers)
            threading.Thread(target=self._push_status, daemon=True).start()

    def _push_status(self):
        printers = load_printers()
        for p in printers:
            p["status"] = poll_printer(p)
        if self.win is not None and self.win.is_open():
            self.win.post({"printers": printers})


@orca.plugin
class PrintersPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(PrintersDashboard)
