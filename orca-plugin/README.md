# FilamentHub — OrcaSlicer Python plugin (iframe passthrough)

A single-file plugin for OrcaSlicer's new Python plugin system (upstream PR
**#14530**, branch `feat/plugin-feature`). It opens a **FilamentHub catalog
window** inside OrcaSlicer that **embeds our real React catalog** in an
`<iframe>`, and synchronizes the user's saved presets into OrcaSlicer.

**Active testing:** this is an alpha plugin tested against OrcaSlicer PR #14530
artifacts. The upstream plugin API is still evolving and updates may be frequent.

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
   │  save preset → profile-changed; authenticated embed → scoped auth-token
   ▼
plugin shell window  ── window.addEventListener('message') ──▶ orca.postMessage(...)
   ▼
Python on_message  ──GET /api/v1/presets/{id}/export/orcaslicer.json (Bearer token)──▶
   write <data_dir>/user/<active>/_local/filamenthub/filament/<name>__fh_<id>.json
      ──▶  native "restart required" dialog
```

### postMessage protocol

**iframe → shell → Python** (managed preset sync):

```js
{ source: 'filamenthub-plugin', type: 'profile-changed' }
```

- `source` namespaces our messages so the shell relay ignores anything else.
- Authentication is a short-lived OrcaSlicer plugin capability (`aud=orcaslicer-plugin`,
  `presets:read`/`presets:write`, 30-minute expiry). Browser access and refresh
  credentials never cross the iframe boundary.
- Python → iframe is **not used** for the MVP; confirmation is a native host
  dialog, which keeps us clear of the existing `useOrcaSlicerNotifications`
  message listener.

**shell → iframe** (toolbar navigation): the shell renders an
Orca-themed toolbar (host `--orca-*` CSS variables — same role as the native
Catalog/Profile/Wiki buttons of the C++ fork panel) and posts

```js
{ source: 'filamenthub-plugin', type: 'navigate', path: '/' | '/profile' | '/wiki' }
```

into the iframe (targetOrigin = our site). The SPA subscribes via
`subscribeToPluginNavigation()` in `utils/pluginBridge.ts` and switches routes
without reloading.

**Session persistence + toolbar status** — the iframe's storage is
partitioned (dies with the window), so the plugin plays the fork's AppConfig
role:

```js
// iframe → shell → Python: persist on login / token refresh, clear on logout
{ source, type: 'auth-token', accessToken: pluginCapability, refreshToken: '' }
{ source, type: 'auth-logout' }
// iframe → shell: toolbar label ("<username> · Presets: N (M synced)", null = guest)
{ source, type: 'auth-state', label }
// iframe → shell → back: session restore handshake on window (re)open
{ source, type: 'embed-ready' }            // SPA announces it listens
{ source, type: 'auth-restore', accessToken, refreshToken }   // shell replies
```

Python stores only the short-lived plugin capability in `.auth.json` next to the
plugin (inside `data_dir`, the allowed write root) and bakes it into the shell
page on `execute()`. Account access/refresh credentials are never stored there.
The label comes ready-made (i18n happens in the SPA) from the same
`/auth/me/presets-stats` endpoint the fork's panel used.

### Frontend embed route (in this repo)

- `App.tsx` — routes `/embed` and `/embed/catalog` render `<CatalogPage />` in a
  chrome-less `EmbedShell` (no `<Layout>` header/footer).
- `utils/pluginBridge.ts` — `isPluginEmbed()` (route-based, sticky for the iframe
  session via `sessionStorage`) and the profile/auth bridge messages.
- `CatalogPage.tsx` — the normal save action becomes **"Import into OrcaSlicer"**
  in embed mode; saving updates the managed profile and triggers auto-sync instead
  of using a second direct-import path.
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
# description = "Browse and sync community-rated filament profiles from FilamentHub, with spool inventory and print-cost tools."
# author = "FilamentHub"
# version = "0.0.5"
# network = ["filamenthub.ru", "*.filamenthub.ru"]   # proposed; ignored by current host
# ///
```

Zero dependencies (stdlib `urllib`/`json`/`ssl`/`threading`). `network` is the
forward-looking outbound-HTTPS allow-list we're proposing on PR #14530.

The shell accepts messages only from `https://filamenthub.ru` and only from its
catalog iframe. HTTP responses are bounded to 5 MiB; preset/state writes use
same-directory atomic replacement; generated filenames are Windows-safe and
include the FilamentHub preset id to avoid collisions.

---

## Build and unit tests

The Orca package is intentionally a single `.py` file. The reproducible build
validates Python syntax and PEP 723 metadata, checks that metadata/runtime
versions agree, and writes a SHA-256 checksum:

```powershell
python orca-plugin/build_package.py
python -m pytest orca-plugin/tests -q
```

Output:

```text
orca-plugin/dist/filamenthub-0.0.5/
  filamenthub_plugin.py       # install this file
  package-metadata.json       # build provenance
  SHA256SUMS                  # integrity check
```

---

## Test steps (owner)

The production embed route was verified live and framable on 2026-07-15. Recheck
it before a release:

```
curl -sI https://filamenthub.ru/embed/catalog   # 200, and NO "X-Frame-Options" header
```

Then, with an OrcaSlicer build from `feat/plugin-feature`:

1. Build the package and copy `filamenthub_plugin.py` to
   `<isolated-data-dir>/orca_plugins/filamenthub/filamenthub_plugin.py`.
2. Launch the official PR artifact with that isolated data directory.
3. Open the **Plugins** dialog → **FilamentHub Catalog** → **Run**.
4. The window opens with our catalog inside. **Sign in** (inside the iframe, our
   normal login), browse/search, and click **Import into OrcaSlicer** on a preset.
5. The preset is saved to the managed FilamentHub profile and synchronized. On the
   current host API, restart OrcaSlicer before selecting a newly created preset.

To side-load into any other build: create
`<data_dir>/orca_plugins/filamenthub/filamenthub_plugin.py` (one entry file per
folder) and restart.

---

## Plugin Hub alpha

Upload the pure-Python wheel plus the tested description/changelog. Plugin Hub
accepts release versions only in numeric `X.Y.Z` form, so alpha status belongs in
the listing text rather than a `-alpha` version suffix. Bump the numeric version
for every uploaded update.

---

## Alpha limitations

If the FilamentHub service is unreachable or under maintenance, the plugin keeps
the remote iframe hidden and shows a local, non-technical maintenance message
with a retry action. Local OrcaSlicer presets remain available.

| # | Gap | Impact | Workaround |
|---|---|---|---|
| 1 | **No preset-install / hot-reload host API.** `orca.host` is read-only; `PluginType.Importer` has no capability base. | Import needs an **app restart**. Not a publish blocker; rough UX. | Atomic file-write to `data_dir/user/<active>/_local/filamenthub/filament/` + native "restart" dialog. Ask on PR #14530 for `orca.host.presets.install(...)` / `reload_user_presets()`. |
| 2 | **A short-lived plugin capability crosses the iframe boundary** with `targetOrigin: '*'` because the `file://` parent has an opaque origin. | The shell rejects every message not originating from the exact catalog iframe and `https://filamenthub.ru`; account access/refresh credentials never cross. | Keep the origin/source regression test and rotate the capability every 30 minutes. |
| 3 | **Outbound HTTPS is ungated today** and the declared network allow-list is not enforced yet. | A future host policy may require an explicit permission contract. | Keep `network = [...]` declared and follow the host's audit-first permission design. |
| 4 | **Package updates recreate the plugin install directory.** | Sidecar auth/sync caches are not guaranteed to survive an update. | The embedded cookie session mints a fresh scoped plugin capability, and sync rebuilds identity from managed preset content; migrate durable state to the host storage API when it lands. |

These limitations are disclosed in the alpha listing. Gap #1
(restart-to-see-import on stock upstream) remains the main user-visible one.

---

## Files

- `filamenthub_plugin.py` — the plugin (PEP 723, single file, zero deps).
- `build_package.py` — deterministic package/metadata/checksum builder.
- `tests/test_filamenthub_plugin.py` — package, origin, filesystem and payload tests.
- `README.md` — this file.
- Frontend embed support: `frontend/src/utils/pluginBridge.ts`,
  `frontend/src/App.tsx`, `frontend/src/pages/CatalogPage.tsx`,
  `frontend/src/components/Layout.tsx`.
