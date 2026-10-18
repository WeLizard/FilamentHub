FilamentHub connects materials, print settings, your spools and printers. Find a filament and a suitable profile, bring the settings into OrcaSlicer, keep track of your stock and calculate what a print costs.

![Find the right settings for your filament: the FilamentHub catalogue](<HOSTED-URL-01-find-the-right-settings>)

## Why it is useful

**If you print**

- **Find the right settings.** Search the catalogue by brand, type, colour, property or your printer. Presets are official, published by the community, or your own, and a generative preset combines the community's presets for a filament into one, with the temperature people actually print at.
- **Know your spools.** Remaining weight, price, batch and usage history, and which printer or material-system slot a spool sits in. Bring your stock over from a spreadsheet or an OctoPrint SpoolManager export.
- **Your own QR labels.** Scan the maker's QR code on a spool, or give the spool its own QR and print a label for it. A phone scan opens the spool.
- **Usage tracked automatically.** Bambu spool use over LAN, plus Moonraker and Happy Hare. FilamentHub can serve as the spool manager for Happy Hare in place of Spoolman. Usage calculated from G-code is marked as an estimate.
- **From G-code to a quotation.** Reuse a completed OrcaSlicer slice to calculate production cost per filament, see whether each spool has enough left, save the calculation, prepare a customer quotation and continue accepted work as an order.

**If you make filament**

- A brand page with your materials, official presets for them, and QR codes on spools that lead to the material and its profile.

![Your spools, in the FilamentHub look and matching OrcaSlicer](<HOSTED-URL-04-your-spools>)

## What the plugin does inside OrcaSlicer

The plugin adds a **FilamentHub** tab to OrcaSlicer and keeps the slicer and your FilamentHub account in step.

- **Presets in the normal filament list.** Imported and synchronized presets keep their colour and inheritance. On OrcaSlicer 2.5.0-alpha and later a new or updated preset shows up in the list at once, with no restart.
- **Edit presets the way Orca groups them.** Familiar tabs and Simple, Advanced or Expert detail level.
- **Automatic sync.** Saving a filament or process preset in OrcaSlicer syncs it to FilamentHub when **Sync automatically** is on. Several saves in a row are combined and OrcaSlicer is never held up by the upload. A **FilamentHub Sync** action in Speed Dial starts a full sync, and problems or "restart needed" notices appear as OrcaSlicer notifications.
- **Your look.** Choose the FilamentHub appearance, or match OrcaSlicer's light or dark colours.

![A FilamentHub preset in OrcaSlicer's filament list, before and after the sync](<HOSTED-URL-02-right-inside-orcaslicer>)

![Edit presets the way Orca groups them](<HOSTED-URL-03-edit-presets-the-orca-way>)

### The plugin toolbar

- **My Spools**: your spools and their slots.
- **Catalog**: the FilamentHub catalogue of materials and presets.
- **Profile**: your presets, printers, filaments, calculations, quotations and orders.
- **Wiki**: short guides, right inside OrcaSlicer.
- **Sync**: a manual sync of the presets you selected.
- **Recover**: scans this computer for your existing OrcaSlicer presets, across all Orca accounts and version backups, and shows a checklist. Only what you tick is imported into FilamentHub. Filaments become drafts, and nothing in OrcaSlicer is overwritten.

![Usage tracked automatically: Bambu and Happy Hare slots](<HOSTED-URL-05-usage-tracked-automatically>)

![From G-code to a quotation](<HOSTED-URL-06-costing-quotation-order>)

![For manufacturers: a brand page with its materials](<HOSTED-URL-07-for-manufacturers>)

![Plugin settings in OrcaSlicer](<HOSTED-URL-08-plugin-settings>)

Plugin settings live in OrcaSlicer's plugin manager: server, appearance, automatic sync, notifications and developer mode. The optional Slicing Pipeline reporter brings completed slices into FilamentHub ready for cost calculations, saved calculations, customer quotations and orders.

## What is coming

FilamentHub is in beta and keeps evolving. These items are not available to every user yet; no dates are promised.

**In development**

- A direct printer-to-FilamentHub link through our own Edge bridge: no open OrcaSlicer and no manufacturer cloud, including Bambu Lab without Bambu Cloud.
- Filament tracking by weight, not only by estimate: weigh-ins and empty-spool weight.
- Happy Hare and OctoPrint connection in a few steps.
- Android app.

**Next**

- Troubleshooting failed prints: your slice and a photo point to the settings worth suspecting and what to try first.
- Preset suggestions for your printer that explain why they fit.
- RFID and NFC tags on spools.
- Hints right inside OrcaSlicer: "not enough filament on this spool" and a spool panel next to filament selection.
- Analytics for manufacturers.
- Workshops with several people.

The catalogue, presets and basic tracking of your own spools are free, and they will stay free.

![What is coming](<HOSTED-URL-09-what-is-coming>)

## Your local setup stays yours

- FilamentHub manages only the preset copies it creates. System, project, third-party and other user presets are left untouched.
- Printer access codes and API keys stay on your computer. Connection addresses can be synchronized to your FilamentHub account when you enable **Store printer addresses in FilamentHub**, and may then appear on the site.
- Slice reporting is optional. FilamentHub receives the slice details needed for history and calculations. The full G-code never leaves your computer; a calculation sends only its summary (the start and end of the file and per-part totals computed locally).
- Network discovery, profile recovery and changes to printer material systems start only from an explicit action.
- Bambu usage calculated from G-code is marked as an estimate, so it is never presented as a scale measurement.
- OrcaSlicer asks once for permission to create a background thread: network and file work run in the background so OrcaSlicer does not freeze. Answer "Yes" once; the choice is remembered.

## Requirements

- A FilamentHub account for the catalogue, preset synchronization, spool inventory and slice history.
- An OrcaSlicer build with Python plugin support.
- Local-network access to the printer for optional Bambu or Happy Hare integration.

On OrcaSlicer builds with the plugin preset API (2.5.0-alpha and later), a newly imported or updated preset appears in the slicer's preset selectors immediately. Older builds need a restart first.
