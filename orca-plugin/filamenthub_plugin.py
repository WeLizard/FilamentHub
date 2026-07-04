# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub"
# name = "FilamentHub"
# description = "Browse the FilamentHub brand/material catalog and import community-rated filament presets."
# author = "FilamentHub"
# version = "0.1.0"
#
# # Proposed forward-looking key (see README gap #4 / PR #14530 feedback). The
# # current host reads only name/description/author/version/dependencies and
# # ignores unknown keys, so declaring this today is harmless and documents intent.
# network = ["filamenthub.ru", "*.filamenthub.ru"]
# ///
"""FilamentHub plugin for OrcaSlicer's Python plugin system (PR #14530).

A self-contained catalog window: it fetches the PUBLIC FilamentHub API over
HTTPS (no iframe — see README for why), lets the user browse/search filament
presets, log in, and import ONE selected preset into the user preset folder.

Runtime surface used (all confirmed against upstream/feat/plugin-feature):
  * orca.script.ScriptPluginCapabilityBase.execute()  — entry point
  * orca.host.ui.create_window(html, on_message, on_close) + UiWindow.post()
  * orca.host.ui.message(...)                          — restart-required notice
  * orca.host.preset_bundle().current_printer_preset() — show detected printer
  * the injected window.orca bridge (postMessage / onMessage)

The page runs on the UI thread when it posts, so every network call is offloaded
to a worker thread and results are pushed back with win.post() (thread-safe).
"""

import json
import os
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request

import orca

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_URL = "https://filamenthub.ru/api/v1"
HTTP_TIMEOUT = 20
_SSL_CTX = ssl.create_default_context()


# --------------------------------------------------------------------------- #
# Filesystem helpers — resolve OrcaSlicer's data_dir from this file's location.
# Writes land under data_dir(), the one globally-allowed root during plugin
# execution (PluginAuditManager.cpp:install_hook).
# --------------------------------------------------------------------------- #
def resolve_data_dir():
    here = os.path.abspath(__file__).replace("\\", "/")
    parts = here.split("/")
    if "orca_plugins" in parts:
        return "/".join(parts[: parts.index("orca_plugins")])
    # Fallback: plugin_dir -> (its parent) -> assume data_dir two levels up.
    return os.path.dirname(os.path.dirname(here))


DATA_DIR = resolve_data_dir()
STORAGE_DIR = os.path.join(DATA_DIR, "filamenthub-plugin")
TOKEN_FILE = os.path.join(STORAGE_DIR, "auth.json")
# OrcaSlicer user filament preset folder: {data_dir}/user/default/filament/
USER_FILAMENT_DIR = os.path.join(DATA_DIR, "user", "default", "filament")


def safe_filename(name):
    out = []
    for ch in (name or "preset"):
        out.append("_" if ch in '<>:"/\\|?*' else ch)
    cleaned = "".join(out).strip(" _")
    return cleaned or "preset"


def load_token():
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save_token(payload):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def clear_token():
    try:
        os.remove(TOKEN_FILE)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# HTTP — plain stdlib (no third-party deps). Returns (status, parsed_or_text).
# --------------------------------------------------------------------------- #
def _request(method, path, token=None, body=None, accept_json=True):
    url = BASE_URL + path
    data = None
    headers = {"Accept": "application/json", "User-Agent": "FilamentHub-OrcaPlugin/0.1"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=_SSL_CTX) as resp:
            raw = resp.read()
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    if accept_json:
        try:
            return status, json.loads(raw.decode("utf-8"))
        except ValueError:
            return status, raw.decode("utf-8", "replace")
    return status, raw


def api_get(path, token=None):
    return _request("GET", path, token=token)


def api_post(path, body, token=None):
    return _request("POST", path, token=token, body=body)


# --------------------------------------------------------------------------- #
# The catalog page — self-contained, themed only via injected --orca-* vars
# (PluginWebDialog.cpp:host_theme_style). Talks to Python through window.orca.
# --------------------------------------------------------------------------- #
PAGE = r"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  body { margin:0; height:100vh; display:flex; flex-direction:column; overflow:hidden;
         font-family:var(--orca-font); }
  header { flex:none; display:flex; align-items:center; gap:8px; padding:10px 14px;
           border-bottom:1px solid var(--orca-border); }
  header h1 { font-size:15px; margin:0; }
  #printer { color:var(--orca-muted); font-size:12px; }
  #auth { margin-left:auto; font-size:12px; color:var(--orca-muted);
          display:flex; align-items:center; gap:6px; }
  .bar { flex:none; display:flex; gap:8px; padding:10px 14px;
         border-bottom:1px solid var(--orca-border); }
  .bar input { flex:1; }
  main { flex:1; overflow:auto; padding:12px 14px 28px; }
  .msg { color:var(--orca-muted); padding:14px 2px; }
  .card { border:1px solid var(--orca-border); border-radius:8px; padding:10px 12px;
          margin-bottom:9px; }
  .card .top { display:flex; align-items:center; gap:8px; }
  .card .name { font-weight:600; }
  .card .meta { color:var(--orca-muted); font-size:12px; margin-top:2px; }
  .card .actions { margin-left:auto; display:flex; gap:6px; }
  .badge { display:inline-block; border:1px solid var(--orca-border); color:var(--orca-muted);
           border-radius:999px; padding:1px 8px; font-size:11px; white-space:nowrap; }
  .swatch { display:inline-block; width:12px; height:12px; border-radius:3px;
            border:1px solid var(--orca-border); vertical-align:-2px; }
  button.small { padding:3px 10px; font-size:12px; }
  button.secondary { background:transparent; color:var(--orca-fg); border-color:var(--orca-border); }
  .overlay { position:fixed; inset:0; display:none; align-items:center; justify-content:center;
             background:rgba(0,0,0,.35); }
  .overlay.on { display:flex; }
  .modal { background:var(--orca-bg); border:1px solid var(--orca-border); border-radius:10px;
           padding:18px; width:320px; }
  .modal h3 { margin:0 0 10px; }
  .modal label { display:block; font-size:12px; color:var(--orca-muted); margin:8px 0 3px; }
  .modal input { width:100%; }
  .modal .row { display:flex; gap:8px; justify-content:flex-end; margin-top:14px; }
  .err { color:#e05656; font-size:12px; min-height:16px; margin-top:8px; }
  .detail { border-top:1px dashed var(--orca-border); margin-top:8px; padding-top:8px;
            font-size:12px; }
  .detail table { width:100%; }
  .detail td { padding:2px 8px 2px 0; vertical-align:top; }
  .detail td:first-child { color:var(--orca-muted); white-space:nowrap; }
</style></head>
<body>
  <header>
    <h1>FilamentHub</h1>
    <span id="printer"></span>
    <span id="auth"></span>
  </header>
  <div class="bar">
    <input id="q" placeholder="Search presets by name, brand, material…"
           onkeydown="if(event.key==='Enter')doSearch()">
    <button class="small" onclick="doSearch()">Search</button>
  </div>
  <main id="main"><div class="msg">Loading catalog…</div></main>

  <div class="overlay" id="login">
    <div class="modal">
      <h3>Sign in to FilamentHub</h3>
      <p style="font-size:12px;color:var(--orca-muted);margin:0">
        Login is only needed to import presets. Browsing is public.</p>
      <label>Email or username</label><input id="li-email" autocomplete="username">
      <label>Password</label><input id="li-pass" type="password" autocomplete="current-password">
      <div class="err" id="li-err"></div>
      <div class="row">
        <button class="small secondary" onclick="closeLogin()">Cancel</button>
        <button class="small" id="li-go" onclick="submitLogin()">Sign in</button>
      </div>
    </div>
  </div>

<script>
'use strict';
var $ = function (id) { return document.getElementById(id); };
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); }

var STATE = { auth:false, email:'', pendingImport:null };

function renderAuth(){
  var el = $('auth');
  if (STATE.auth) {
    el.innerHTML = 'Signed in as <b>'+esc(STATE.email)+'</b> '+
      '<button class="small secondary" onclick="logout()">Sign out</button>';
  } else {
    el.innerHTML = '<button class="small secondary" onclick="openLogin()">Sign in</button>';
  }
}
function openLogin(){ $('li-err').textContent=''; $('login').classList.add('on'); $('li-email').focus(); }
function closeLogin(){ $('login').classList.remove('on'); }
function submitLogin(){
  $('li-go').disabled = true; $('li-err').textContent = 'Signing in…';
  orca.postMessage({command:'login', email:$('li-email').value, password:$('li-pass').value});
}
function logout(){ orca.postMessage({command:'logout'}); }

function doSearch(){
  $('main').innerHTML = '<div class="msg">Searching…</div>';
  orca.postMessage({command:'search', q:$('q').value});
}

function presetCard(p){
  var brand = (p.filament && p.filament.brand && p.filament.brand.name) || p.brand_name || '';
  var mat = (p.filament && p.filament.material_type) || p.material_type || '';
  var color = (p.filament && p.filament.color_hex) || p.color_hex || '';
  var rating = (p.rating!=null) ? Number(p.rating).toFixed(1)+'★' : '';
  var meta = [brand, mat].filter(Boolean).join(' · ');
  return '<div class="card" id="card-'+p.id+'">'+
    '<div class="top">'+
      (color?'<span class="swatch" style="background:'+esc(color)+'"></span>':'')+
      '<div><div class="name">'+esc(p.name||('Preset #'+p.id))+'</div>'+
      (meta?'<div class="meta">'+esc(meta)+'</div>':'')+'</div>'+
      (rating?'<span class="badge">'+esc(rating)+'</span>':'')+
      (p.is_official?'<span class="badge">official</span>':'')+
      '<div class="actions">'+
        '<button class="small secondary" onclick="viewPreset('+p.id+')">Details</button>'+
        '<button class="small" onclick="doImport('+p.id+',this)">Import</button>'+
      '</div>'+
    '</div><div id="detail-'+p.id+'"></div></div>';
}

function renderResults(items){
  if (!items || !items.length){ $('main').innerHTML='<div class="msg">No presets found.</div>'; return; }
  $('main').innerHTML = items.map(presetCard).join('');
}
function viewPreset(id){ orca.postMessage({command:'preset', id:id}); }

function renderDetail(id, p){
  var box = $('detail-'+id); if(!box) return;
  var rows = [];
  function add(k,v){ if(v!=null && v!=='') rows.push('<tr><td>'+esc(k)+'</td><td>'+esc(v)+'</td></tr>'); }
  add('Nozzle temp', p.extruder_temp!=null ? p.extruder_temp+' °C' : null);
  add('Bed temp', p.bed_temp!=null ? p.bed_temp+' °C' : null);
  add('Flow ratio', p.flow_ratio);
  add('Success rate', p.success_rate!=null ? Math.round(p.success_rate*100)+' %' : null);
  add('Uses', p.usage_count);
  add('Description', p.description);
  box.innerHTML = '<div class="detail"><table>'+(rows.join('')||
    '<tr><td>No extra detail</td></tr>')+'</table></div>';
}

function doImport(id, btn){
  if (!STATE.auth){ STATE.pendingImport = id; openLogin(); return; }
  if (btn){ btn.disabled = true; btn.textContent = 'Importing…'; }
  orca.postMessage({command:'import', id:id});
}

orca.onMessage(function(m){
  if (!m || !m.command) return;
  if (m.command === 'init'){
    STATE.auth = !!m.auth; STATE.email = m.email || '';
    $('printer').textContent = m.printer ? ('Printer: '+m.printer) : '';
    renderAuth(); doSearch();
  } else if (m.command === 'results'){
    renderResults(m.items);
  } else if (m.command === 'preset'){
    if (m.ok) renderDetail(m.id, m.data);
  } else if (m.command === 'login_result'){
    $('li-go').disabled = false;
    if (m.ok){
      STATE.auth = true; STATE.email = m.email || ''; renderAuth(); closeLogin();
      if (STATE.pendingImport){ var id = STATE.pendingImport; STATE.pendingImport = null; doImport(id); }
    } else { $('li-err').textContent = m.error || 'Login failed'; }
  } else if (m.command === 'logout_result'){
    STATE.auth = false; STATE.email = ''; renderAuth();
  } else if (m.command === 'import_result'){
    var card = $('card-'+m.id);
    if (card){ var b = card.querySelector('.actions .small:last-child');
      if (b){ b.disabled = false; b.textContent = 'Import'; } }
    // The host also shows a native dialog with the restart notice.
  }
});

orca.postMessage({command:'init'});
</script>
</body></html>
"""


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
            width=920,
            height=680,
            on_message=self.on_message,
            on_close=self.on_close,
        )
        return orca.ExecutionResult.success("FilamentHub catalog opened.")

    def on_close(self):
        self.win = None

    # on_message runs on the UI thread — offload every network call to a worker.
    def on_message(self, msg):
        msg = msg or {}
        command = msg.get("command")
        if command == "init":
            # No network: read the cached token and the printer name (host access
            # is safe here — on_message runs on the UI thread) and reply inline.
            self._do_init()
        elif command == "search":
            threading.Thread(target=self._do_search, args=(msg.get("q", ""),), daemon=True).start()
        elif command == "preset":
            threading.Thread(target=self._do_preset, args=(msg.get("id"),), daemon=True).start()
        elif command == "login":
            threading.Thread(target=self._do_login,
                             args=(msg.get("email", ""), msg.get("password", "")), daemon=True).start()
        elif command == "logout":
            clear_token()
            self._post({"command": "logout_result"})
        elif command == "import":
            threading.Thread(target=self._do_import, args=(msg.get("id"),), daemon=True).start()

    # -- helpers ------------------------------------------------------------- #
    def _post(self, payload):
        if self.win is not None and self.win.is_open():
            self.win.post(payload)

    def _detected_printer(self):
        try:
            return orca.host.preset_bundle().current_printer_preset().name
        except Exception:
            return ""

    # -- command handlers (worker threads) ----------------------------------- #
    def _do_init(self):
        tok = load_token()
        self._post({
            "command": "init",
            "auth": bool(tok),
            "email": (tok or {}).get("email", ""),
            "printer": self._detected_printer(),
        })

    def _do_search(self, query):
        path = "/presets/?size=50"
        if query.strip():
            path += "&search=" + urllib.parse.quote(query.strip())
        try:
            status, data = api_get(path)
            items = data.get("items", []) if isinstance(data, dict) else []
            self._post({"command": "results", "items": items})
        except Exception as exc:
            self._post({"command": "results", "items": [], "error": str(exc)})

    def _do_preset(self, preset_id):
        try:
            status, data = api_get("/presets/%s" % int(preset_id))
            self._post({"command": "preset", "id": preset_id,
                        "ok": status == 200, "data": data if status == 200 else {}})
        except Exception as exc:
            self._post({"command": "preset", "id": preset_id, "ok": False, "error": str(exc)})

    def _do_login(self, email, password):
        try:
            status, data = api_post("/auth/login", {"email": email, "password": password})
            if status == 200 and isinstance(data, dict) and data.get("access_token"):
                save_token({"email": email,
                            "access_token": data["access_token"],
                            "refresh_token": data.get("refresh_token", "")})
                self._post({"command": "login_result", "ok": True, "email": email})
            else:
                err = "Wrong email or password" if status == 401 else ("Login failed (%s)" % status)
                if isinstance(data, dict) and data.get("detail"):
                    err = str(data["detail"])
                self._post({"command": "login_result", "ok": False, "error": err})
        except Exception as exc:
            self._post({"command": "login_result", "ok": False, "error": str(exc)})

    def _do_import(self, preset_id):
        tok = load_token()
        if not tok or not tok.get("access_token"):
            self._post({"command": "import_result", "id": preset_id, "ok": False})
            orca.host.ui.message("Please sign in before importing.", title="FilamentHub", icon="warning")
            return
        token = tok["access_token"]
        try:
            status, profile = api_get("/presets/%s/export/orcaslicer.json" % int(preset_id), token=token)
            if status == 401:
                clear_token()
                self._post({"command": "logout_result"})
                self._post({"command": "import_result", "id": preset_id, "ok": False})
                orca.host.ui.message("Your session expired. Please sign in again.",
                                     title="FilamentHub", icon="warning")
                return
            if status != 200 or not isinstance(profile, dict):
                self._post({"command": "import_result", "id": preset_id, "ok": False})
                orca.host.ui.message("Export failed (HTTP %s)." % status,
                                     title="FilamentHub", icon="error")
                return

            name = profile.get("name") or ("FilamentHub preset %s" % preset_id)
            os.makedirs(USER_FILAMENT_DIR, exist_ok=True)
            base = os.path.join(USER_FILAMENT_DIR, safe_filename(name))
            with open(base + ".json", "w", encoding="utf-8") as fh:
                json.dump(profile, fh, ensure_ascii=False, indent=2)

            # The .info sidecar is best-effort (sync metadata; not required to load).
            try:
                istatus, info = _request("GET", "/presets/%s/export/orcaslicer.info" % int(preset_id),
                                         token=token, accept_json=False)
                if istatus == 200:
                    with open(base + ".info", "wb") as fh:
                        fh.write(info)
            except Exception:
                pass

            self._post({"command": "import_result", "id": preset_id, "ok": True, "name": name})
            orca.host.ui.message(
                "Imported '%s' into your filament presets.\n\n"
                "Restart OrcaSlicer to see it in the filament dropdown." % name,
                title="FilamentHub", icon="info")
        except Exception as exc:
            self._post({"command": "import_result", "id": preset_id, "ok": False})
            orca.host.ui.message("Import failed: %s" % exc, title="FilamentHub", icon="error")


@orca.plugin
class FilamentHubPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(FilamentHubCatalog)
