# FilamentHub — OrcaSlicer Python plugin

A single-file plugin for OrcaSlicer's Python plugin system. It opens the real
FilamentHub React catalog inside OrcaSlicer and synchronizes the user's saved
presets into OrcaSlicer.

**Active testing:** this is an alpha plugin. The upstream plugin API is still
evolving and updates may be frequent.

Replaces the ~9.5K-LOC C++ WebView fork with **one `.py` file** plus a small
embed route in our existing frontend.

---

## Approach: direct embedded page with a local secret boundary

### Bambu LAN filament accounting

The LAN adapter uses the capabilities actually reported by the printer; it does
not select a supported model list or require a Bambu cloud account. While Orca
is running, a local MQTT connection retains job and AMS mapping updates.
Available current-job G-code/3MF files are read through local FTPS. The adapter
requires an unambiguous matching filename and plate; it never picks the newest
file on the printer. File transfers are bounded to 64 MiB and metadata to 1 MiB.
Storage availability and LAN permissions depend on the printer firmware.

Slicer weights scaled by reported print progress are explicitly approximate,
especially for partial or multi-material jobs. If file evidence is unavailable,
changes in an identified spool's reported remaining grams or percentage can
provide a separate estimate. Percentages use the printer's reported original
spool weight. Unknown readings, RFID reads, changed tags and increased remaining
weight do not become consumption deltas. Estimates appear separately from
confirmed consumption in FilamentHub; the label identifies their source.

The local journal saves the observed spool binding and pending reports before
upload. After restart, a still-identifiable job can continue from that baseline,
and retrying an acknowledged report cannot debit it twice. A spool assigned
during printing starts a new accounting interval. Running, cancellation and idle
transitions remain ordered until journaled; cancellation records only the
observed partial estimate. A bounded queue overflow starts a fresh baseline
instead of estimating an interval whose observations were lost. The plugin cannot reconstruct
arbitrary jobs that ran while Orca was closed and are no longer identifiable on
the printer. Continuous collection with Orca closed requires a separate local
runtime; the existing standalone Edge runtime does not yet provide Bambu support.

The matching FilamentHub backend must support estimated bridge usage before
these reports can be accepted. Older backends leave the local reports pending.

On current OrcaSlicer builds, `get_ui()` returns a small localized bootstrap that
navigates the top-level Pages WebView to
`https://filamenthub.ru/embed/catalog`. The React route renders the compact
Catalog/Profile/Wiki, Sync and Recovery toolbar and communicates through the
official injected `window.orca` bridge with a random per-tab binding. Opening the
tab never creates a Python socket or local HTTP server. If the site is
unavailable, the bootstrap keeps a localized retry state visible instead of
exposing the browser's connection-error page.

Actions that need LAN credentials open a separate host-owned window with a
second random binding. That window contains the Bambu/Moonraker address and
credential forms; the remote React page never receives those values. External
OAuth uses a short-lived server handoff completed in the system browser and
polled over normal HTTPS by the embedded React page. Older host builds use the
same direct page in their managed-window fallback.

```
React /embed/catalog  ── window.orca.postMessage(... + per-tab binding) ──▶
Python on_message  ──GET /api/v1/presets/{id}/export/orcaslicer.json (Bearer token)──▶
   write <data_dir>/user/<active>/_local/filamenthub/filament/<name>__fh_<id>.json
      ──▶  native "restart required" dialog

explicit local setup ──▶ host-owned local dialog ──▶ Python LAN adapter
external OAuth ──▶ server handoff + system browser ──▶ embedded page HTTPS poll
```

### postMessage protocol

**React page → Python** (managed preset sync):

```js
{ source: 'filamenthub-plugin', type: 'profile-changed' }
{ source: 'filamenthub-plugin', type: 'profile-sync', scope: 'all' | 'filament' | 'machine' | 'process', requestId }
```

- `source` namespaces messages, and the direct page includes its random per-tab
  binding. Python rejects an absent or stale binding.
- Authentication is a short-lived OrcaSlicer plugin capability (`aud=orcaslicer-plugin`,
  `presets:read`/`presets:write`, 30-minute expiry). Browser access and refresh
  credentials never cross the plugin bridge.
- Python returns operation results through the native Pages bridge with the matching
  `requestId`, so unrelated background notices cannot complete a manual sync or
  printer-bundle request.
- A full sync reports filament presets, printer configurations and print
  profiles as separate rows. Each direction is gated by the corresponding
  account preference. Incomplete local scans never finalize a remote snapshot,
  and one rejected profile does not prevent valid profiles in the same batch
  from synchronizing.

The direct embed renders an Orca-themed toolbar (host `--orca-*` CSS variables —
the same role as the native Catalog/Profile/Wiki buttons of the C++ fork panel).
Navigation stays inside the React application and uses

```js
{ source: 'filamenthub-plugin', type: 'navigate', path: '/' | '/profile' | '/wiki' }
```

through `subscribeToPluginNavigation()` in `utils/pluginBridge.ts`. The same
session-bound bridge carries sync/recovery results and parsed slice data.

**Session persistence** — the site reports only a short-lived plugin capability
and a presentation-only account label to Python:

```js
// React → Python: persist on login / token refresh, clear on logout
{ source, type: 'auth-token', accessToken: pluginCapability, refreshToken: '' }
{ source, type: 'auth-logout' }
// React → Python: toolbar/account status ("<username> · Presets: N (M synced)", null = guest)
{ source, type: 'auth-state', label }
```

Python stores only the short-lived plugin capability in `.auth.json` under
OrcaSlicer's private plugin storage when `orca.host.plugin.storage()` is
available, with the install directory retained as a compatibility fallback.
Account access/refresh credentials are never sent to or stored by Python. During
external OAuth the direct SPA receives a fresh account session from its one-shot
HTTPS poll and then mints the same short-lived plugin capability as password
login. The label comes
ready-made (i18n happens in the SPA) from the same `/auth/me/presets-stats`
endpoint the fork's panel used.

### Bambu LAN bridge

The Bambu adapter is a separate, narrower trust boundary from preset sync:

1. the authenticated embed requests a ten-minute, single-use pairing code;
2. the local dialog first reuses the LAN address from the exact bound Orca printer
   preset, or from the currently selected preset as a local-only fallback; the
   user can still expand the manual address field, and enters the access code
   in the host-owned form (the embedded page never receives either value);
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

- `App.tsx` — routes `/embed` and `/embed/catalog` render the catalog directly
  inside the plugin WebView.
- `utils/pluginBridge.ts` — validates the per-tab binding and communicates with
  OrcaSlicer's official injected bridge.
- `CatalogPage.tsx` — the normal save action becomes **"Import into OrcaSlicer"**
  in embed mode; saving updates the managed profile and triggers auto-sync instead
  of using a second direct-import path.
- `Layout.tsx` — hides the ordinary site header and footer and renders the
  compact plugin toolbar in a direct Orca host.
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
# version = "0.2.0"
# network = ["filamenthub.ru", "*.filamenthub.ru", "filamenthub.club", "*.filamenthub.club"]
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
  G-code at `psGCodePostProcess` when the host exposes it and reporting is
  explicitly enabled in that capability's settings;
- current capability lifecycle hooks start plugin resources from `on_load` and
  stop queued work and the local Bambu observer from
  `on_cancelled`/`on_unload`; older hosts keep the registration-time fallback;
- `orca.host.ui`, `orca.host.preset_bundle()`, optional
  `orca.host.app_language()` and optional `orca.host.plugin.storage()` provide
  UI, read-only preset observations, locale and private plugin state.

### Sliced-file reporting

Open the settings for `filamenthub-slice-reporter` in the slicing pipeline
plugin list before enabling **Save sliced files and send their details to
FilamentHub**. Reporting defaults to off, including for existing process
presets without that setting. The capability name stays unchanged because
OrcaSlicer uses it to identify plugins saved in process presets.

When enabled, the reporter reads OrcaSlicer's working G-code, adds comments
identifying managed FilamentHub profiles, and retains a limited local copy for
later calculations. It does not change print moves. The slicing worker adds the
file name, printer model, printer and print profile names and identifiers,
slicer version, export destination type, and identifiers linking the slice to
this plugin installation to a durable local queue. It never sends that queue
through Python HTTP.

The signed-in FilamentHub page requests pending entries through the bound Pages
bridge and submits them through its normal authenticated API client. Python
removes only entries acknowledged after a successful response. If the page is
signed out, closed, or temporarily offline, the queue survives and is retried
when the page becomes available. This keeps the audited report endpoint out of
plugin activation and the slicing worker, so it cannot open the native HTTP
permission dialog or block either lifecycle. The full G-code is uploaded only
when a calculation is explicitly requested. Reporting failures never fail
G-code export or printer upload, and the reporter never probes the system
temporary directory.

Preset installation is not a host capability in the reviewed API snapshot.
Managed filament/machine/process files are therefore written atomically below
the plugin-owned user preset folder and become selectable after OrcaSlicer
reload/restart. The plugin never edits an unmanaged profile.

Bridge commands require the random binding for the current Pages tab. Python
rejects remote credential submissions; those require the separate local-dialog
binding. HTTP responses are bounded to
5 MiB; preset/state writes use
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
orca-plugin/dist/release-X.Y.Z/
  filamenthub-X.Y.Z/
    filamenthub_plugin.py       # production single-file copy
    package-metadata.json       # build provenance
    SHA256SUMS                  # single-file and locale integrity
  filamenthub-X.Y.Z-dev/
    filamenthub_plugin.py       # localhost development copy
  wheels/
    filamenthub-X.Y.Z-py3-none-any.whl
  RELEASE_NOTES.md
  SHA256SUMS                    # release wheel integrity
```

The default output directory is derived from the validated plugin version, so
each local candidate is self-contained and a newer build cannot be confused
with wheels left by older versions. CI and disposable verification runs may
still pass `--output` explicitly.

The legacy `--dev-source` flag remains a compatibility alias. It still stages
both copies so a development build can never silently drift from the release
source. Add `--no-wheel` when only the two single-file artifacts are needed:

```powershell
python orca-plugin/build_package.py --dev-source --no-wheel
```

Install
`orca-plugin/dist/release-X.Y.Z/filamenthub-X.Y.Z-dev/filamenthub_plugin.py`
in the isolated OrcaSlicer data directory. It keeps the localhost default and
embeds the same locale catalogs as the release package.

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
4. The tab opens the normal plugin toolbar and embedded catalog without a local
   socket. **Sign in** using the normal login, browse/search, and click
   **Import into OrcaSlicer** on a preset.
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

If the FilamentHub service is unreachable, OrcaSlicer and its local presets remain
available. A denied socket affects only an explicit local-printer action; the
HTTPS catalog and external sign-in do not require a Python socket.

| # | Gap | Impact | Workaround |
|---|---|---|---|
| 1 | **No preset-install / hot-reload host API.** `orca.host` is read-only; `PluginType.Importer` has no capability base. | Filament, machine, and process imports need an **app restart**. Not a publish blocker; rough UX. | Atomic writes below `data_dir/user/<active>/_local/filamenthub/`; only FilamentHub-managed copies are updated. Ask upstream for `orca.host.presets.install(...)` / `reload_user_presets()`. |
| 2 | **The Pages bridge is injected into the host-provided plugin page and has no public caller allow-list.** | An unbound message reaching Python would have command authority. | Bind every command to a random per-tab value generated by Python; reject missing/stale bindings and require a different binding for the host-owned credential dialog. |
| 3 | **The Plugin API cannot declare socket permissions**, and the audit prompt for `socket.__new__` has no target that can be persisted. | A real local-printer connection can ask again after OrcaSlicer restarts; denying the prompt blocks that local operation. | Start LAN work only from an explicit user path, handle denial without losing data, and ask upstream to audit address-bearing operations or expose a network permission declaration. |
| 4 | **The Python `Preset` binding omits read-only `filament_id` and `setting_id`.** | A loaded managed material cannot be mapped to Bambu's exact material command from the public object alone. | Walk only the host-selected backing-file inheritance chain and block when it cannot be resolved. Ask upstream to expose both fields as read-only properties. |

These limitations are disclosed in the alpha listing. Gap #1
(restart-to-see-import on stock upstream) remains the main user-visible one.

---

## Files

- `filamenthub_plugin.py` — the dependency-free plugin runtime.
- `filamenthub_locales/` — bundled bootstrap and local-dialog translations with English fallback.
- `build_package.py` — deterministic package/metadata/checksum builder.
- `validate_locales.py` / `TRANSLATING.md` — catalog validation and community workflow.
- `tests/test_filamenthub_plugin.py` — package, origin, filesystem and payload tests.
- `README.md` — this file.
- Frontend embed support: `frontend/src/utils/pluginBridge.ts`,
  `frontend/src/App.tsx`, `frontend/src/pages/CatalogPage.tsx`,
  `frontend/src/components/Layout.tsx`.
