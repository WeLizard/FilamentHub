# Printers — cross-vendor printer dashboard (OrcaSlicer plugin)

A second, **independent** plugin built on OrcaSlicer's Python plugin system
(PR **#14530**) — deliberately unrelated to FilamentHub, to demonstrate that the
host's panel contribution (`orca.host.ui.create_panel`) is a **generic
mechanism**, not a one-off integration: two different plugins, two docked tabs,
one API.

It docks a **Printers** tab that shows all your networked printers as tiles —
live status, nozzle/bed temperatures and print progress — regardless of brand or
firmware, and opens any printer's web interface in place. OrcaSlicer's own
Multi-device tab is Bambu-only; this covers everyone.

## What it does (on stock PR #14530 capabilities — no new host API)

- `create_panel(...)` → a docked, host-themed tab (native `--orca-*` look, light/dark).
- Polls each printer on a worker thread and pushes status to the page:
  - **Moonraker** (Klipper): `/printer/objects/query` (temps, `print_stats`, progress).
  - **OctoPrint**: `/api/printer` + `/api/job`.
  - **Other**: a reachability ping.
- **Add / remove** printers in the page; stored in `printers.json` next to the
  plugin (inside `data_dir`, the allowed write root).
- **Open** → swaps the grid for an `<iframe>` of the printer's web UI
  (Mainsail/Fluidd/OctoPrint are framable on the LAN).

## Why it strengthens the PR ask

- **Second surface, same slot:** proves `create_panel` is reusable across
  unrelated plugins — the core "mechanism, not places" argument.
- **Plugin-supplied tab icon** (`printers.svg` shipped in the plugin dir) exercises
  the `create_panel(icon=...)` path.
- **Local-network access:** printers live on user-chosen LAN addresses no static
  manifest allow-list can enumerate — concrete motivation for a future
  `network = ["local-network"]` permission class (declared here, ignored today).

## Files

- `printers_plugin.py` — the plugin (PEP 723, single file, zero deps).
- `printers.svg` — tab icon (drop one in; absent → host default icon).
