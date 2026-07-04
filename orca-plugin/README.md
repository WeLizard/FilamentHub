# FilamentHub — OrcaSlicer Python plugin (prototype)

A single-file plugin for OrcaSlicer's new Python plugin system (upstream PR
**#14530**, branch `feat/plugin-feature`). It opens a **FilamentHub catalog
window** inside OrcaSlicer, browses/searches our public catalog over HTTPS, and
imports one selected filament preset into your user preset folder.

This is the runnable prototype from `docs/current/orca-plugin-blueprint.md`.
It replaces the ~9.5K-LOC C++ WebView fork with **one `.py` file**.

---

## What it does today

| Feature | Status | How |
|---|---|---|
| Register a Script capability, open a window | ✅ | `orca.script.ScriptPluginCapabilityBase` + `orca.host.ui.create_window` |
| Two-way JS ↔ Python bridge | ✅ | injected `window.orca` (`postMessage`/`onMessage`) ↔ `on_message` / `UiWindow.post` |
| Live catalog browse + search | ✅ | public `GET /api/v1/presets/?search=…` |
| Preset detail preview | ✅ | `GET /api/v1/presets/{id}` |
| Show detected printer | ✅ | `orca.host.preset_bundle().current_printer_preset().name` |
| Sign in (persistent token) | ✅ | `POST /api/v1/auth/login` → token cached under `data_dir` |
| **Import one preset into config** | ✅ (with restart) | `GET /presets/{id}/export/orcaslicer.json` → write `{data_dir}/user/default/filament/<name>.json` |

**No `<iframe>` passthrough.** The runtime imposes no CSP and would technically
allow an external-HTTPS iframe (`PluginWebDialog` loads HTML via `SetPage` with a
`file://` base, no `Content-Security-Policy`, no navigation veto). We did **not**
use it because the injected `window.orca` bridge lives in the top `file://` frame
and a cross-origin `https://filamenthub.ru` iframe cannot reach it — it would
require a `window.parent.postMessage` bridge added to our React app plus prod
`frame-ancestors` that allows a `file://` embedder. The native-API shell is
self-contained, verifiable, and publishable today; iframe passthrough is a
possible future enhancement once the frontend ships a bridge.

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
# version = "0.1.0"
# network = ["filamenthub.ru", "*.filamenthub.ru"]   # proposed; ignored by current host
# ///
```

- **Zero dependencies** — stdlib only (`urllib`, `json`, `ssl`, `threading`), so
  there is no `uv`/pip install step and nothing to break on the bundled
  interpreter.
- `network = [...]` is a **forward-looking** key for the outbound-HTTPS
  allow-list we're proposing on PR #14530 (blueprint gap #4). The current host
  parses only `name/description/author/version/dependencies` and ignores unknown
  keys, so declaring it now is harmless and documents intent.

---

## Side-load it into the PR #14530 artifact build (for testing)

You need an OrcaSlicer build **from the `feat/plugin-feature` branch** (a local
build of the submodule at `upstream/feat/plugin-feature`, or a CI artifact from
that PR). The stock release does not have the plugin runtime.

1. Launch that OrcaSlicer once so it creates its `data_dir`:
   - **Windows:** `%APPDATA%\OrcaSlicer`
   - **macOS:** `~/Library/Application Support/OrcaSlicer`
   - **Linux:** `~/.config/OrcaSlicer`
2. Create the local plugin folder and drop the file in:
   ```
   <data_dir>/orca_plugins/filamenthub/filamenthub_plugin.py
   ```
   (One entry file per folder — `find_installed_plugin_entry` rejects a folder
   with zero or multiple `.py`/`.whl` candidates.)
3. Restart OrcaSlicer. Open the **Plugins** dialog — "FilamentHub" appears.
   Select the **FilamentHub Catalog** capability and click **Run**.
4. The catalog window opens. Browse/search works immediately (public API). Click
   **Sign in** to enable **Import**.

> The plugin resolves `data_dir` from its own path (it looks for the
> `orca_plugins` component). If you place it elsewhere, import still targets
> `<data_dir>/user/default/filament/` as long as it lives under `orca_plugins`.

### Importing a preset
Import writes `<name>.json` (+ best-effort `<name>.info`) into
`<data_dir>/user/default/filament/`. OrcaSlicer only scans that folder **at
startup** (`PresetBundle::load_user_presets`), so the plugin shows a native
"Restart OrcaSlicer to see it" dialog. **Restart, then pick the filament from the
dropdown.** (Removing the restart requires a host API — see the gap below.)

---

## Publish to the Orca Plugin Hub BETA

The Hub install/update path is `CloudPluginService` + `PluginManager`
(`subscribe_and_install_cloud_plugin`, `download_and_install_cloud_plugin`,
`update_cloud_plugin`). Publishing is done through Orca's plugin-developer flow,
not from this repo:

1. Package the single file as the plugin entry (a `.py` is a valid entry;
   `.whl` is only needed for multi-file plugins later).
2. Bump `version` in the PEP 723 block for every release (the Hub compares it
   against the installed `installed_version` in `.install_state.json` to offer
   updates).
3. Submit through the OrcaSlicer plugin-developer / Plugin Hub BETA portal with
   the `id`, `name`, `version`, author, description, and the `network` allow-list.
   Once live, users install in one click; updates and changelog flow through the
   Hub.
4. Bonus distribution: any FilamentHub preset can carry a `plugins`
   `"name;uuid;capability"` reference, and Orca will **auto-offer to install our
   Hub plugin** for anyone who receives that preset
   (`PluginResolver::resolve_missing_plugins`).

---

## Gaps that block "publishable to beta" (and workarounds)

| # | Gap | Impact on beta | Prototype workaround |
|---|---|---|---|
| 1 | **No preset-install / hot-reload host API.** `orca.host` is entirely read-only; `PluginType.Importer` has no capability base. | Import needs an **app restart** to take effect. Not a publish-blocker, but a rough UX. | Write the `.json` to `data_dir/user/default/filament/` and show a native "restart required" dialog. Ask on PR #14530 for `orca.host.presets.install(...)` or `reload_user_presets()`. |
| 2 | **No `open_browser` / in-page external navigation.** | Google/OAuth sign-in can't run in the window. | Prototype uses **email + password** `POST /auth/login` (works today). OAuth deferred until `orca.host.ui.open_browser(url)` lands. |
| 3 | **No first-class per-plugin storage API.** | Token persistence relies on `data_dir` being the allowed write root — fine now, but fragile once `AuditMode::Enforcing` turns on (sockets/writes gated). | Store the token under `<data_dir>/filamenthub-plugin/auth.json` (currently an allowed root). Ask for `orca.host.storage_dir()`. |
| 4 | **Outbound HTTPS is ungated today** (audit hook handles only `open`), but `Enforcing` mode is already scaffolded to block sockets. | A future OrcaSlicer could break the catalog fetch. | Declare `network = ["filamenthub.ru", …]` in the manifest now; push for manifest-level allow-listing on the PR. |

**None of these block publishing to the BETA today** — the prototype is a
complete, runnable, self-contained plugin. Gap #1 is the only one users will
feel (restart-to-see-import); the rest are hardening for when the sandbox
tightens.

---

## Files

- `filamenthub_plugin.py` — the plugin (PEP 723, single file, zero deps).
- `README.md` — this file.
