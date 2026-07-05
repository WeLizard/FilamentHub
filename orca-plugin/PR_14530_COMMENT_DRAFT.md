# Draft — consolidated comment for OrcaSlicer PR #14530

> Post in the PR thread once the demo video is recorded. Attach the video inline
> (drag the .mp4/.gif into the GitHub comment) and link the reference build
> (WeLizard/OrcaSlicer prototype branch). Keep it to ONE comment; further
> exchanges are "re FH-N: …", not new prose. Tone: security-first, we ask to be
> *constrained*, the host stays in control.

---

Hi @barmanR, thanks — we've been building on `feat/plugin-feature` and it's
genuinely good to work against. Rather than pitch cold, here's what we already
have running on this branch, then a consolidated, numbered list of what would let
plugins like ours go further. Everything below is framed so the **host stays in
control** and the plugin only *declares* — we're asking to be constrained, not
handed the UI.

## What works today, unmodified branch

- **FilamentHub** — a catalog/importer plugin: a page (via `create_window`) that
  browses our brand/material catalog, signs in, and installs a chosen filament
  preset into the user preset folder. Pure `orca.script` + `orca.host.ui` +
  outbound HTTPS. No host changes.
- **Printers** — a second, unrelated plugin: a cross-vendor dashboard of the
  user's networked printers (Moonraker / OctoPrint / generic) with live status
  and each printer's web UI in an iframe.

Two unrelated plugins, one surface — which is the whole point of the requests
below: a *mechanism*, not one-off integrations.

## Prototype we're offering (reference only)

To show it's concrete, we prototyped one addition on our fork branch and would
happily turn it into a PR if useful: **`orca.host.ui.create_panel(html, title,
on_message, on_close, icon)`** — identical content/messaging contract to
`create_window`, but the page is **docked as a main-window tab** instead of a
floating window. The host renders and owns the tab; it is torn down on plugin
unload; the `icon` is a file the plugin ships in its own directory (loaded
through the existing nanosvg path — nothing baked into app resources). Both
plugins above use it and appear as native tabs with their own icons. (Video
attached.)

## Requests (numbered; each: what / why / security posture)

**FH-1 — a sanctioned preset install / reload API.** `orca.host` is read-only and
`PluginType.Importer` has no capability base, so installing a preset means
writing files into `data_dir/user/...` and asking the user to **restart**.
Proposal: `orca.host.presets.install(config, type, name, inherits="",
overwrite=False)` and/or `orca.host.presets.reload_user_presets()`.
*Security:* this **narrows** the surface — today a plugin already writes raw
files into `data_dir`; a host-mediated call can validate the config, enforce
`inherits`, and (optionally) show the user a confirmation. The status quo is the
less safe option.

**FH-2 — declarative network allow-listing in the manifest.** Outbound HTTPS is
ungated today, but `AuditMode::Enforcing` is scaffolded to block sockets, which
would kill any catalog/printer plugin. Proposal: a manifest key, shown to the
user at install time and enforced by the audit hook, e.g.
`network = ["filamenthub.ru", "*.filamenthub.ru"]`.
One concrete wrinkle from the Printers plugin: printers live on **user-chosen LAN
addresses** no static list can enumerate — so please consider a
`"local-network"` permission *class* alongside host patterns.
*Security:* this is a restriction we're asking you to place on us, not an
expansion.

**FH-3 — a typed contribution model (declare, host renders).** The drivers here
are "plugins should live in the UI, not behind Plugins → Run." Proposal: the
manifest declares typed contributions into **named host slots**; the host
renders them natively and calls back into the capability. Concretely, in order of
usefulness to us:
- `panel` — a docked page (our `create_panel` prototype).
- `action` — a button in a named slot (e.g. next to the material dropdown, or in
  the export menu) → invokes a capability with context.
- `setting-group` — a plugin-declared group of settings rendered natively in the
  filament/print settings, persisted under namespaced keys (`plugin:<id>:*`) in
  the preset and consumed by the plugin's own g-code post-processor. The core
  slicer never interprets these keys, so **profile compatibility is preserved**
  (a preset opened without the plugin just carries inert keys — and this composes
  with the existing preset→plugin auto-install).
Plus: **contributions mount on `on_load`** (incl. at startup), and every
contribution is **shown to the user at install time** with per-slot permissions.
*Security:* the plugin never draws or touches host UI — it only declares; the
host owns placement, lifecycle and rights. This is deliberately the opposite of
the "plugins run arbitrary code in the UI" model.
*Explicitly out of scope of this request:* injecting custom fill patterns or
anything into the slicing core (`libslic3r`) — that belongs in C++, not here.
Viewport overlays we note only as a future direction (read-only mesh access
already exists via `orca.host.model()`).

**FH-4 — a post-slice action hook.** Let a plugin add an action next to
"Print / Export" after slicing (our use: "send to cost calculator"). Scope = the
existing g-code capability's read-only path to the sliced file. *Security:* same
read-only surface you already expose to g-code plugins.

**FH-0 — a small bug we hit.** The host theme user-script
(`PluginWebDialog`/`host_theme_user_script`) and the `window.orca` bridge are
injected into **every frame**, including a cross-origin `<iframe>` inside a
plugin page. The unlayered theme rules then override the framed site's own CSS.
Suggestion: inject into the top frame only. (We work around it on our side by
stripping the injected `<style>` in the iframe.)

## What we are NOT asking for

No OAuth-in-host, no arbitrary filesystem write, no access to other users' data,
no way out of the sandbox, no drawing into host UI. Those are exactly the
boundaries we want the model to keep — the requests above are all "declare, and
let the host mediate."

Happy to open focused PRs for any of these (starting with `create_panel` /
`reload_user_presets`) if that's the most useful next step. Thanks again.
