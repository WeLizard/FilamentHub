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
file on the printer. Archive transfers are bounded to 64 MiB, streamed G-code
inspection to 256 MiB and metadata to 1 MiB. A large G-code entry is not
extracted when the bounded slice metadata already provides the per-filament
weights. Storage availability and LAN permissions depend on the printer firmware.

The plugin distributes each slicer-declared filament weight over the job's
actual net E advance per layer, excluding retractions, and uses the layer number
reported by the printer as the current point on that curve. A cached slice can
restore the curve when the printer no longer exposes its print file, provided
the filament weights and layer count identify exactly one file. Older files
without a usable curve fall back to an explicitly labelled progress estimate.
Changes in an identified spool's reported remaining grams or percentage can
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
      ──▶  orca.host.preset.bundles.reload_local (older hosts: "restart required" notice)

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
- File counts describe managed files on disk. A successful reload request is
  reported separately and does not prove that Orca loaded them. Host-loaded
  identity is observed on the UI thread; after a worker reload it remains
  unknown until the next host observation.

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
SHA-256 digest of the FilamentHub bridge token. A server 401 clears only the
rejected bridge token, using compare-and-swap so a delayed response cannot
invalidate a newer token. LAN credentials survive server failures and inactivity.
The local setup dialog offers **Repair FilamentHub connection** for an owned
saved connection without asking for the LAN access code again. Repair verifies
the account and uses only the saved address and serial; changing the endpoint
requires entering its access code. Unreadable or malformed local storage is
preserved and blocks mutations until recovered.

Only explicit **Remove local connection** deletes the local credential. It
attempts server revocation first, queues a retry when possible if unavailable,
and reports unconfirmed server revocation separately from local removal.
The write surface is
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
# version = "0.2.7"
# network = ["filamenthub.ru", "filamenthub.club"]
# ///
```

Zero dependencies (stdlib `urllib`/`json`/`ssl`/`threading`). The metadata
`network` list documents the two production hosts; it does not grant access.
Runtime permissions use OrcaSlicer's official declaration API below.

### Current host surfaces

The plugin feature-detects the evolving host API instead of assuming every
OrcaSlicer build exposes the same capabilities:

- `orca.pages.PagesPluginCapabilityBase` provides the native page when present;
- `orca.script.ScriptPluginCapabilityBase` remains the compatible window
  fallback;
- `orca.slicing.SlicingPipelineCapabilityBase` reports and annotates completed
  G-code at `psGCodePostProcess` when the host exposes it and reporting is
  explicitly enabled in that capability's settings;
- `on_lifecycle_event` with `orca.LifecycleEvent.PresetSaved` syncs a saved
  filament or process preset when automatic sync is on; `orca.host.ui.push_notification`
  reports automatic and Speed Dial sync results; a second script capability,
  "FilamentHub Sync", is the Speed Dial action, registered with the Pages tab;
- current capability lifecycle hooks start plugin resources from `on_load` and
  stop queued work and the local Bambu observer from
  `on_cancelled`/`on_unload`; older hosts keep the registration-time fallback;
- `orca.host.ui`, `orca.host.preset_bundle()`, optional
  `orca.host.app_info()["language"]` (UI thread only) and optional
  `orca.host.plugin.storage()` provide UI, read-only preset observations,
  locale and private plugin state.

### Host permissions

During capability registration, current hosts receive
`orca.request_permissions(network=["https://filamenthub.ru", "https://filamenthub.club"], threading=True)`.
OrcaSlicer presents the missing permissions together before it creates a
capability instance. Previously granted permissions are reused; refusing the
declaration stops the plugin from loading. The host's network grant covers
paths and ports on those exact hosts and the corresponding socket operations.
It does not grant access to other hosts or subdomains.

Both production origins are declared because the selected server is applied
later, when the capability loads. Development builds declare only their actual
`SITE_URL`; production packages remove the environment override. No printer
addresses, arbitrary filesystem trees or program-execution grants are included.

An older host without the `network` keyword still receives the supported
`threading=True` declaration. Hosts predating that declaration use their normal
runtime audit prompts. Only an unsupported argument signature triggers this
fallback: permission refusals, validation failures and internal host errors are
not retried as smaller requests. Network and file work still run in background
threads so the slicer remains responsive; an action whose runtime thread is
refused reports that it did not start.

Signing in labels the background key **OrcaSlicer** without reading the
computer's hostname. Diagnostic reports use the interpreter's existing OS and
Python-version fields and do not query a hostname either. Explicit printer
discovery, printer connections, file access and external-browser actions can
still require the host's own relevant permissions.

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

The signed-in FilamentHub page periodically requests pending entries through the
bound Pages bridge and submits them through its normal authenticated API client. The
slicing worker never pushes to the Pages window: Orca runs it off the UI thread
while the UI may be waiting for export, so a host UI call there can deadlock. Python
removes only entries acknowledged after a successful response. If the page is
signed out, closed, or temporarily offline, the queue survives and is retried
when the page becomes available. This keeps the audited report endpoint out of
plugin activation and the slicing worker, so it cannot open the native HTTP
permission dialog or block either lifecycle. The full G-code never leaves the
computer: a calculation sends only its summary (the start and end of the file
and per-part totals computed locally). Reporting failures never fail
G-code export or printer upload, and the reporter never probes the system
temporary directory.

Managed filament/machine/process files are written atomically below the
plugin-owned user preset folder. On hosts that expose
`orca.host.preset.bundles.reload_local` (OrcaSlicer 2.5.0-alpha and later; detected
by capability, not by version) the plugin asks the host to reload the
FilamentHub local bundle, so the presets become selectable at once with
selection and unsaved edits kept. Without that API, or when the host rejects the
reload, the files wait for an OrcaSlicer restart and the user is told so. The
plugin never edits an unmanaged profile.

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

## Embedded-page startup recovery

The website serves a small static recovery panel and an independent classic
script before the application bundle starts. If an application file cannot
load, initialization fails, or React has not committed a screen within 20
seconds, the embedded page shows a reload action and a fixed diagnostic code:

| Code | Startup stage |
|---|---|
| `FH-STARTUP-RESOURCE` | An application script, stylesheet or preload failed. |
| `FH-STARTUP-RUNTIME` | An application error or rejected promise occurred before the first screen. |
| `FH-STARTUP-INITIALIZATION` | Initial setup or translation initialization rejected. |
| `FH-STARTUP-TIMEOUT` | No screen was committed within 20 seconds; a later successful startup still recovers. |

The panel never displays exception messages, resource URLs or the bridge's
session fragment. Reload preserves the original page binding. A successful
React commit, including its normal error boundary screen, removes the panel
and all startup listeners. If even the recovery script cannot load, static
instructions remain visible.

This recovery UI is deployed with the frontend, independently of the plugin
package. It requires OrcaSlicer's WebView to render the document. A completely
blank native view or a WebKit process failure still needs the exact OrcaSlicer
build, operating-system version and host diagnostics to investigate.

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
   host API without `preset.bundles.reload_local`, restart OrcaSlicer before
   selecting a newly created preset; with it the preset is available at once.
6. In **Profile → Printers**, explicitly add one printer's configuration set to
   OrcaSlicer. Confirm that only FilamentHub-managed machine/process copies are
   created. They are selectable at once with `preset.bundles.reload_local`;
   otherwise restart OrcaSlicer before selecting them.

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
available. The embedded HTTPS catalog loads through OrcaSlicer's WebView;
Python synchronization, reporting and printer operations remain subject to the
host's network permissions. Refusing a required declaration prevents the plugin
from loading.

| # | Gap | Impact | Workaround |
|---|---|---|---|
| 1 | **Hot reload needs the plugin preset API (OrcaSlicer 2.5.0-alpha+).** Older hosts have no `orca.host.preset.bundles.reload_local`. | On older builds, filament, machine, and process imports need an **app restart**. | Atomic writes below `data_dir/user/<active>/_local/filamenthub/`; only FilamentHub-managed copies are updated. On hosts with the API the plugin reloads the local bundle itself. |
| 2 | **The Pages bridge is injected into the host-provided plugin page and has no public caller allow-list.** | An unbound message reaching Python would have command authority. | Bind every command to a random per-tab value generated by Python; reject missing/stale bindings and require a different binding for the host-owned credential dialog. |
| 3 | **Dynamic printer addresses are not known at plugin registration.** Current hosts support origin grants for the two known FilamentHub servers; older hosts and targetless LAN events can still need runtime prompts. | A real local-printer operation can require a separate permission; the service grant does not cover the local network. | Keep LAN access within the normal host audit flow, start discovery from an explicit user action, and handle refusal without losing data. |
| 4 | **The Python `Preset` binding omits read-only `filament_id` and `setting_id`.** | A loaded managed material cannot be mapped to Bambu's exact material command from the public object alone. | Walk only the host-selected backing-file inheritance chain and block when it cannot be resolved. Ask upstream to expose both fields as read-only properties. |

These limitations are disclosed in the alpha listing. Gap #1
(restart-to-see-import on builds without the preset API) remains the main user-visible one.

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
