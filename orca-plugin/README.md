# FilamentHub — OrcaSlicer Python plugin (iframe passthrough)

A single-file plugin for OrcaSlicer's new Python plugin system (upstream PR
**#14530**, branch `feat/plugin-feature`). It opens a **FilamentHub catalog
window** inside OrcaSlicer that **embeds our real React catalog** in an
`<iframe>`, and imports a selected filament preset into your user preset folder.

Replaces the ~9.5K-LOC C++ WebView fork with **one `.py` file** plus a small
embed route in our existing frontend.

---

## Approach: iframe passthrough (confirmed by spike)

The plugin's WebView2 renders an external-HTTPS `<iframe>` from its `file://`
shell page (`PluginWebDialog` loads HTML via `SetPage` with **no** CSP and no
navigation veto). Our own `X-Frame-Options: SAMEORIGIN` was the only blocker, so
the owner added a framable `/embed/` nginx location that serves the SPA without
`X-Frame-Options` / `frame-ancestors`.

So the plugin is a **thin shell** that embeds `https://filamenthub.ru/embed/catalog`
and relays the catalog's actions to Python. We reuse the entire React frontend —
no hand-written catalog UI.

```
iframe (React /embed/catalog)
   │  window.parent.postMessage({ source:'filamenthub-plugin', type:'import-preset', presetId, token })
   ▼
plugin shell window  ── window.addEventListener('message') ──▶ orca.postMessage(...)
   ▼
Python on_message  ──GET /api/v1/presets/{id}/export/orcaslicer.json (Bearer token)──▶
   write <data_dir>/user/default/filament/<name>.json  ──▶  native "restart required" dialog
```

### postMessage protocol

**iframe → shell → Python** (the only message today):

```js
{ source: 'filamenthub-plugin', type: 'import-preset', presetId: <number>, token: '<jwt|"">' }
```

- `source` namespaces our messages so the shell relay ignores anything else.
- `token` is the logged-in user's access token, read via the canonical
  `getToken()` in `utils/auth.ts`. The export endpoint requires auth, and Python
  (outside the iframe) has no session, so the page hands it the token.
- Python → iframe is **not used** for the MVP; confirmation is a native host
  dialog, which keeps us clear of the existing `useOrcaSlicerNotifications`
  message listener.

**shell → iframe** (toolbar navigation, v0.3.0): the shell renders an
Orca-themed toolbar (host `--orca-*` CSS variables — same role as the native
Catalog/Profile/Wiki buttons of the C++ fork panel) and posts

```js
{ source: 'filamenthub-plugin', type: 'navigate', path: '/' | '/profile' | '/calculator' | '/wiki' }
```

into the iframe (targetOrigin = our site). The SPA subscribes via
`subscribeToPluginNavigation()` in `utils/pluginBridge.ts` and switches routes
without reloading.

**Session persistence + toolbar status (v0.4.0)** — the iframe's storage is
partitioned (dies with the window), so the plugin plays the fork's AppConfig
role:

```js
// iframe → shell → Python: persist on login / token refresh, clear on logout
{ source, type: 'auth-token', accessToken, refreshToken }
{ source, type: 'auth-logout' }
// iframe → shell: toolbar label ("<username> · Presets: N (M synced)", null = guest)
{ source, type: 'auth-state', label }
// iframe → shell → back: session restore handshake on window (re)open
{ source, type: 'embed-ready' }            // SPA announces it listens
{ source, type: 'auth-restore', accessToken, refreshToken }   // shell replies
```

Python stores tokens in `.auth.json` next to the plugin (inside `data_dir`,
the allowed write root) and bakes them into the shell page on `execute()`.
The label comes ready-made (i18n happens in the SPA) from the same
`/auth/me/presets-stats` endpoint the fork's panel used.

### Frontend embed route (in this repo)

- `App.tsx` — routes `/embed` and `/embed/catalog` render `<CatalogPage />` in a
  chrome-less `EmbedShell` (no `<Layout>` header/footer).
- `utils/pluginBridge.ts` — `isPluginEmbed()` (route-based, sticky for the iframe
  session via `sessionStorage`) and `importPresetToPlugin(presetId)`.
- `CatalogPage.tsx` — each preset shows an **"Import into OrcaSlicer"** button in
  embed mode only; it calls `importPresetToPlugin(...)`.
- `Layout.tsx` — also hides header/footer in embed mode, so navigating to a
  material detail page inside the iframe stays chrome-less.
- The existing fork bridge (`window.filamenthub` / `window.wx`,
  `Export*Button`, `useOrcaSlicerNotifications`) is **untouched** — this is a
  parallel path.

---

## PEP 723 metadata (top of `filamenthub_plugin.py`)

```python
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
# network = ["filamenthub.ru", "*.filamenthub.ru"]   # proposed; ignored by current host
# ///
```

Zero dependencies (stdlib `urllib`/`json`/`ssl`/`threading`). `network` is the
forward-looking outbound-HTTPS allow-list we're proposing on PR #14530.

---

## Test steps (owner)

**Prerequisite — deploy the `/embed/` nginx location** (already added to
`frontend/nginx.conf`). Until `https://filamenthub.ru/embed/catalog` is live and
framable, the iframe shows blank. Verify:

```
curl -sI https://filamenthub.ru/embed/catalog   # 200, and NO "X-Frame-Options" header
```

Then, with an OrcaSlicer build from `feat/plugin-feature`:

1. The test plugin is already staged at
   `F:\FilamentHub\OrcaPR14530\data\orca_plugins\filamenthub\filamenthub_plugin.py`.
   Launch OrcaSlicer with that data_dir (`OrcaPR14530\run-isolated.bat`).
2. Open the **Plugins** dialog → **FilamentHub Catalog** → **Run**.
3. The window opens with our catalog inside. **Sign in** (inside the iframe, our
   normal login), browse/search, and click **Import into OrcaSlicer** on a preset.
4. A native dialog confirms the import and asks you to restart. **Restart**, then
   pick the filament from the dropdown.

To side-load into any other build: create
`<data_dir>/orca_plugins/filamenthub/filamenthub_plugin.py` (one entry file per
folder) and restart.

---

## Publish to the Orca Plugin Hub BETA

The Hub install/update path is `CloudPluginService` + `PluginManager`. Submit the
single `.py` through Orca's plugin-developer / Plugin Hub BETA portal with the
`id`, `name`, `version`, author, description, and the `network` allow-list. Bump
`version` on every release (compared against `.install_state.json`). Bonus: a
FilamentHub preset can carry a `plugins` `"name;uuid;capability"` reference, and
Orca will auto-offer to install our Hub plugin for anyone who receives it
(`PluginResolver::resolve_missing_plugins`).

---

## Gaps and what blocks "publishable to beta"

| # | Gap | Impact | Workaround |
|---|---|---|---|
| A | **`/embed/` must be deployed** (owner). | Without it the iframe is blank. | Owner deploys `frontend/nginx.conf`; verify no `X-Frame-Options` on `/embed/`. **This is the one hard prerequisite before testing.** |
| 1 | **No preset-install / hot-reload host API.** `orca.host` is read-only; `PluginType.Importer` has no capability base. | Import needs an **app restart**. Not a publish blocker; rough UX. | File-write to `data_dir/user/default/filament/` + native "restart" dialog. Ask on PR #14530 for `orca.host.presets.install(...)` / `reload_user_presets()`. |
| 2 | **Token crosses the postMessage boundary** (iframe → `file://` shell) with `targetOrigin: '*'`. | Acceptable — the only listener is our trusted shell — but not ideal. | Restrict once a stable shell origin exists. In cookie-only auth mode with no local token, `getToken()` may be empty and import is blocked with a "sign in" dialog. |
| 3 | **Outbound HTTPS ungated today** but `AuditMode::Enforcing` is scaffolded to block sockets. | A future OrcaSlicer could break the export fetch. | Declare `network = [...]`; push for manifest allow-listing. |

None block publishing to the BETA today, **once the `/embed/` route is
deployed**. Gap #1 (restart-to-see-import) is the only thing users feel.

---

## Files

- `filamenthub_plugin.py` — the plugin (PEP 723, single file, zero deps).
- `README.md` — this file.
- Frontend embed support: `frontend/src/utils/pluginBridge.ts`,
  `frontend/src/App.tsx`, `frontend/src/pages/CatalogPage.tsx`,
  `frontend/src/components/Layout.tsx`.
