FilamentHub brings community filament profiles, spool inventory, and print-cost tools into OrcaSlicer. Find a material, import its preset, and connect your slicing workflow to the filament you actually use.

The settings and Bambu usage accounting described below are for **FilamentHub 0.2.0**, currently a release candidate. The public 0.1.10 package does not include all of these changes.

![Browse and import community filament presets from inside OrcaSlicer](https://api.orcaslicer.com/api/v1/bundles/media/3bc1c768-34ae-4b04-b451-28dbff52c564/content)

## From material to finished print

- **Discover useful profiles.** Browse the catalog inside the plugin and filter it using the printer already selected in OrcaSlicer.
- **Work with native presets.** FilamentHub profiles keep their colour and inheritance and appear in a dedicated group in OrcaSlicer's normal filament selector.
- **Synchronize deliberately.** Enable synchronization per profile, pull an update, send a local edit back, or recover an existing local profile as a private draft. Local changes are never silently overwritten.
- **Connect digital profiles to real material.** Track physical spools and compare saved assignments with supported Bambu AMS and Happy Hare material systems before explicitly applying a change.
- **Calculate print costs.** Optionally keep recent sliced files locally so you can use them in FilamentHub calculations without finding and selecting the file again.

![Saved filament presets and sync status in the FilamentHub profile](https://api.orcaslicer.com/api/v1/bundles/media/3abf7f71-9324-4e66-93c2-a2afacb03519/content)

![Imported FilamentHub presets in OrcaSlicer's native filament dropdown](https://api.orcaslicer.com/api/v1/bundles/media/3d0440c2-cfd2-4286-98b6-488c5088efcd/content)

## Bambu LAN and real spool balances

Connect a Bambu printer over your local network using its address and LAN access code. This connection does not require Bambu Cloud. Available information depends on the printer and firmware; the integration is not limited to one printer model.

With a spool assigned in FilamentHub, the plugin can use the current job's sliced filament quantities and reported progress, or usable changes in the printer's reported remaining filament, to calculate consumption. **Calculated usage automatically reduces the assigned spool's balance and is clearly marked as estimated in its history.** This is a calculation, not a scale measurement. If the available data cannot be safely linked to a spool, the plugin does not invent a deduction.

A spool assigned partway through a print starts from the balance you enter and the first usable observation after assignment. Earlier consumption is not charged again. For a cancelled print, accounting uses the observed partial progress when available.

Keep OrcaSlicer running for continuous collection. Saved accounting state survives a restart, and the plugin can recover a still-identifiable job from the printer. It cannot reconstruct every print that happened while OrcaSlicer was closed.

![FilamentHub spool inventory with a Happy Hare gate assignment](https://api.orcaslicer.com/api/v1/bundles/media/30be9acd-e848-4da5-a03d-80217a49f564/content)

## Two settings panels, two purposes

**FilamentHub (Pages)** controls the embedded catalog and preset synchronization. Choose `filamenthub.ru` or `filamenthub.club` — both access the same account and data. You may need to sign in again after switching. Enable automatic synchronization or sync manually, and choose whether successful automatic syncs show a notification. Select which profiles to synchronize in your FilamentHub profile.

**filamenthub-slice-reporter (Slicing Pipeline)** is an optional connection between slicing and FilamentHub calculations. It is disabled by default. Enable **Save sliced files and send their details to FilamentHub** in this panel if you want to reuse recent slices.

## What the permission prompt is for

When sliced-file reporting is enabled:

- **File access** lets the plugin read the G-code produced by OrcaSlicer, add comments identifying FilamentHub profiles, and keep a small local cache of recent files for calculations. Print movement commands are unchanged. OrcaSlicer's permission dialog may show a temporary file path because slicing uses temporary files.
- **The signed-in FilamentHub page** sends slice details through its normal authenticated API connection: the filename, printer model, printer and print-profile names and identifiers, slicer version, export destination type, and identifiers linking the slice to this computer. The report goes to `https://filamenthub.ru/api/v1/orcaslicer/slices` or the equivalent address on `filamenthub.club`.
- **The full G-code is uploaded only when you explicitly request a calculation.** Enabling slice reports does not automatically upload the full file after each slice.

The Python slicing worker does not make the report HTTP request. It stores the metadata in a durable local queue and passes it to the signed-in FilamentHub page, which sends it through the same web API connection used by the catalog. Plugin activation and slicing therefore do not open a native HTTP permission dialog for this endpoint. If the page is signed out, closed, or temporarily offline, reports remain queued and are retried when the page is available. G-code export and printer upload continue independently. You can disable the slice reporter in its settings.

Local printer connections may separately need network permission. **Search local network** starts discovery only when you choose it. Merely opening the FilamentHub page does not scan your network.

## Your local setup stays yours

- FilamentHub updates or removes only its own managed preset copies. Unmanaged OrcaSlicer profiles are left untouched.
- Printer-profile restoration and material-system changes require an explicit action.
- Printer connection credentials are stored locally. FilamentHub receives the account, preset, slice, and material-system data used by the features you enable.

## Requirements and current limitation

- A free FilamentHub account for the catalog, spool inventory, and preset synchronization. Production costing and quote features may require Calculator Pro access.
- An OrcaSlicer build with Python plugin support.
- Internet access to FilamentHub for account and server features, even when the printer itself uses LAN mode.
- For Bambu accounting: a reachable printer with LAN access enabled, an assigned FilamentHub spool, usable job or remaining-filament data, and a FilamentHub server supporting estimated usage.

The plugin is in active testing while OrcaSlicer's plugin API continues to evolve. On current builds, OrcaSlicer must be restarted before a newly imported or updated preset appears because the host cannot yet reload user presets on request.

When reporting a problem, include the OrcaSlicer build hash and FilamentHub plugin version. Developer mode in the FilamentHub settings enables **Report a problem**, which attaches the plugin log to your report.
