# FilamentHub — OrcaSlicer Python plugin (iframe passthrough)

A single-file plugin for OrcaSlicer's Python plugin system. It opens a
**FilamentHub catalog window** inside OrcaSlicer that **embeds our real React
catalog** in an
`<iframe>`, and synchronizes the user's saved presets into OrcaSlicer.

**Active testing:** this is an alpha plugin. The upstream plugin API is still
evolving and updates may be frequent.

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
{ source: 'filamenthub-plugin', type: 'profile-sync', scope: 'all' | 'filament' | 'machine' | 'process', requestId }
```

- `source` namespaces our messages so the shell relay ignores anything else.
- Authentication is a short-lived OrcaSlicer plugin capability (`aud=orcaslicer-plugin`,
  `presets:read`/`presets:write`, 30-minute expiry). Browser access and refresh
  credentials never cross the iframe boundary.
- Python returns operation results through the shell with the matching
  `requestId`, so unrelated background notices cannot complete a manual sync or
  printer-bundle request.
- A full sync reports filament presets, printer configurations and print
  profiles as separate rows. Each direction is gated by the corresponding
  account preference. Incomplete local scans never finalize a remote snapshot,
  and one rejected profile does not prevent valid profiles in the same batch
  from synchronizing.

**shell → iframe** (toolbar navigation, session restore and operation results):
the shell renders an
Orca-themed toolbar (host `--orca-*` CSS variables — same role as the native
Catalog/Profile/Wiki buttons of the C++ fork panel) and posts

```js
{ source: 'filamenthub-plugin', type: 'navigate', path: '/' | '/profile' | '/wiki' }
```

into the iframe (targetOrigin = our site). The SPA subscribes via
`subscribeToPluginNavigation()` in `utils/pluginBridge.ts` and switches routes
without reloading. The same origin/source-checked direction carries
`auth-restore`, sync/recovery results and parsed slice data. It is therefore a
deliberately bounded two-way bridge, not the old one-way MVP.

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

Python stores only the short-lived plugin capability in `.auth.json` under
OrcaSlicer's private plugin storage when `orca.host.plugin.storage()` is
available, with the install directory retained as a compatibility fallback.
Account access/refresh credentials are never stored there. The label comes
ready-made (i18n happens in the SPA) from the same `/auth/me/presets-stats`
endpoint the fork's panel used.

### Bambu LAN bridge

The Bambu adapter is a separate, narrower trust boundary from preset sync:

1. the authenticated embed requests a ten-minute, single-use pairing code;
2. the shell opens the plugin-owned local form, where the user enters the LAN
   address and access code (the iframe never receives either value);
3. Python verifies that the address resolves only to a private/link-local host
   and confirms MQTT-over-TLS access to the printer on port 8883;
4. after the printer answers, the pairing code is exchanged for a revocable
   `fhpb_...` bridge token bound to that physical printer, material system and
   plugin instance;
5. while OrcaSlicer is running, the plugin posts normalized print/AMS
   observations using that bridge token. It does not depend on the 30-minute
   account plugin capability remaining alive;
6. from **My Filaments** the user may explicitly preview and apply the saved
   material assignments. Python re-reads the owned server state, rejects stale
   previews, RFID-managed trays and a busy printer, sends only Bambu's
   `ams_filament_setting` command over the paired LAN connection, then proves
   the result with a fresh printer snapshot.

The LAN address, Bambu serial and access code stay in `.fh_bambu.json` in the
private plugin storage. The server receives none of them and stores only a
SHA-256 digest of the FilamentHub bridge token. Removing the connection revokes
the server token before the local secret is deleted. The write surface is
deliberately limited to user-confirmed third-party material metadata; it does
not expose pause, temperature, motion, AMS movement or arbitrary printer
commands. Exact FilamentHub spool identity remains in FilamentHub and is never
written into Bambu firmware.

### Frontend embed route (in this repo)

- `App.tsx` — routes `/embed` and `/embed/catalog` render the ordinary catalog
  inside `Layout`; embed detection makes that shared layout chrome-less rather
  than maintaining a second `EmbedShell`.
- `utils/pluginBridge.ts` — `isPluginEmbed()` (route-based, sticky for the iframe
  session via `sessionStorage`) and the profile/auth bridge messages.
- `CatalogPage.tsx` — the normal save action becomes **"Import into OrcaSlicer"**
  in embed mode; saving updates the managed profile and triggers auto-sync instead
  of using a second direct-import path.
- `Layout.tsx` — also hides header/footer in embed mode, so navigating to a
  material detail page inside the iframe stays chrome-less.
- The legacy-compatible browser bridge (`window.filamenthub` / `window.wx`,
  `Export*Button`, `useOrcaSlicerNotifications`) remains for rolling
  compatibility. It does not revive or authorize the retired C++ fork.

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
# version = "0.1.3"
# network = ["filamenthub.ru", "*.filamenthub.ru"]   # proposed; ignored by current host
# ///
```

Zero dependencies (stdlib `urllib`/`json`/`ssl`/`threading`). `network` is the
forward-looking outbound-HTTPS allow-list we're proposing upstream.

### Current host surfaces

The plugin feature-detects the evolving host API instead of assuming every
OrcaSlicer build exposes the same capabilities:

- `orca.pages.PagesPluginCapabilityBase` provides the native page when present;
- `orca.script.ScriptPluginCapabilityBase` remains the compatible window
  fallback;
- `orca.slicing.SlicingPipelineCapabilityBase` reports and annotates completed
  G-code at `psGCodePostProcess` when the host exposes it;
- `orca.host.ui`, `orca.host.preset_bundle()`, optional
  `orca.host.app_language()` and optional `orca.host.plugin.storage()` provide
  UI, read-only preset observations, locale and private plugin state.

Preset installation is not a host capability in the reviewed API snapshot.
Managed filament/machine/process files are therefore written atomically below
the plugin-owned user preset folder and become selectable after OrcaSlicer
reload/restart. The plugin never edits an unmanaged profile.

The shell accepts messages only from `https://filamenthub.ru` and only from its
catalog iframe. HTTP responses are bounded to 5 MiB; preset/state writes use
same-directory atomic replacement; generated filenames are Windows-safe and
include the FilamentHub preset id to avoid collisions.

---

## Build and unit tests

The Orca package is intentionally a single `.py` file. The reproducible build
validates Python syntax and PEP 723 metadata, checks that metadata/runtime
versions agree, stages matching production and localhost-development copies,
and writes a SHA-256 checksum:

```powershell
python orca-plugin/build_package.py
python -m pytest orca-plugin/tests -q
```

Output:

```text
orca-plugin/dist/filamenthub-0.1.3/
  filamenthub_plugin.py       # install this file
  package-metadata.json       # build provenance
  SHA256SUMS                  # integrity check
orca-plugin/dist/filamenthub-0.1.3-dev/
  filamenthub_plugin.py       # localhost development copy
orca-plugin/dist/wheels/
  filamenthub-0.1.3-py3-none-any.whl
```

The legacy `--dev-source` flag remains a compatibility alias. It still stages
both copies so a development build can never silently drift from the release
source. Add `--no-wheel` when only the two single-file artifacts are needed:

```powershell
python orca-plugin/build_package.py --dev-source --no-wheel
```

Install `orca-plugin/dist/filamenthub-0.1.3-dev/filamenthub_plugin.py` in the
isolated OrcaSlicer data directory. It keeps the localhost default and embeds
the same locale catalogs as the release package.

---

## Test steps (owner)

The production embed route was verified live and framable on 2026-07-15. Recheck
it before a release:

```
curl -sI https://filamenthub.ru/embed/catalog   # 200, and NO "X-Frame-Options" header
```

Then, with the exact OrcaSlicer build or pull-request artifact being tested:

1. Build the package and copy `filamenthub_plugin.py` to
   `<isolated-data-dir>/orca_plugins/filamenthub/filamenthub_plugin.py`.
2. Launch the official PR artifact with that isolated data directory.
3. Open the **Plugins** dialog → **FilamentHub Catalog** → **Run**.
4. The window opens with our catalog inside. **Sign in** (inside the iframe, our
   normal login), browse/search, and click **Import into OrcaSlicer** on a preset.
5. The preset is saved to the managed FilamentHub profile and synchronized. On the
   current host API, restart OrcaSlicer before selecting a newly created preset.
6. In **Profile → Printers**, explicitly add one printer's configuration set to
   OrcaSlicer. Confirm that only FilamentHub-managed machine/process copies are
   created, then restart OrcaSlicer before selecting them.

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
| 1 | **No preset-install / hot-reload host API.** `orca.host` is read-only; `PluginType.Importer` has no capability base. | Filament, machine, and process imports need an **app restart**. Not a publish blocker; rough UX. | Atomic writes below `data_dir/user/<active>/_local/filamenthub/`; only FilamentHub-managed copies are updated. Ask upstream for `orca.host.presets.install(...)` / `reload_user_presets()`. |
| 2 | **A short-lived plugin capability crosses the iframe boundary** with `targetOrigin: '*'` because the `file://` parent has an opaque origin. | The shell rejects every message not originating from the exact catalog iframe and `https://filamenthub.ru`; account access/refresh credentials never cross. | Keep the origin/source regression test and rotate the capability every 30 minutes. |
| 3 | **Outbound HTTPS is ungated today** and the declared network allow-list is not enforced yet. | A future host policy may require an explicit permission contract. | Keep `network = [...]` declared and follow the host's audit-first permission design. |
| 4 | **The Python `Preset` binding omits read-only `filament_id` and `setting_id`.** | A loaded managed material cannot be mapped to Bambu's exact material command from the public object alone. | Walk only the host-selected backing-file inheritance chain and block when it cannot be resolved. Ask upstream to expose both fields as read-only properties. |

These limitations are disclosed in the alpha listing. Gap #1
(restart-to-see-import on stock upstream) remains the main user-visible one.

---

## Files

- `filamenthub_plugin.py` — the dependency-free plugin runtime.
- `filamenthub_locales/` — bundled native-shell translations with English fallback.
- `build_package.py` — deterministic package/metadata/checksum builder.
- `validate_locales.py` / `TRANSLATING.md` — catalog validation and community workflow.
- `tests/test_filamenthub_plugin.py` — package, origin, filesystem and payload tests.
- `README.md` — this file.
- Frontend embed support: `frontend/src/utils/pluginBridge.ts`,
  `frontend/src/App.tsx`, `frontend/src/pages/CatalogPage.tsx`,
  `frontend/src/components/Layout.tsx`.
