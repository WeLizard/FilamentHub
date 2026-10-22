FilamentHub connects materials, print settings, your spools and printers. Find a filament and a suitable profile, bring the settings into OrcaSlicer, keep track of your stock and calculate what a print costs.

> **OrcaSlicer will ask for permission.** When you install or update the plugin, OrcaSlicer asks whether it may run work in the background. Please allow it: syncing with your account and loading presets run in the background, so the slicer does not freeze while it waits for the network.

![Find the right settings for your filament: the FilamentHub catalogue](https://api.orcaslicer.com/api/v1/bundles/media/36cc1c18-b99c-4acd-b19c-c9beeb77bef4/content)

## Why it is useful

**If you print**

- **Find the right settings.** Search the catalogue by brand, type, colour, property or your printer. Presets are official, published by the community, or your own, and a generative preset combines the community's presets for a filament into one, with the temperature people actually print at.
- **Know your spools.** Remaining weight, price, batch and usage history, and which printer or material-system slot a spool sits in. Bring your stock over from a spreadsheet or an OctoPrint SpoolManager export.
- **Your own QR labels.** Scan the maker's QR code on a spool, or give the spool its own QR and print a label for it. A phone scan opens the spool.
- **Usage tracked automatically.** Bambu spool use over LAN, plus Moonraker and Happy Hare. FilamentHub can serve as the spool manager for Happy Hare in place of Spoolman. Usage calculated from G-code is marked as an estimate.
- **From G-code to a quotation.** Reuse a completed OrcaSlicer slice to calculate production cost per filament, see whether each spool has enough left, save the calculation, prepare a customer quotation and continue accepted work as an order.

**If you make filament**

- A brand page with your materials, official presets for them, and QR codes on spools that lead to the material and its profile.

![Your spools, in the FilamentHub look and matching OrcaSlicer](https://api.orcaslicer.com/api/v1/bundles/media/3b89760e-c9f7-4575-901a-a8e2bd3dc066/content)

## What the plugin does inside OrcaSlicer

The plugin adds a **FilamentHub** tab to OrcaSlicer and keeps the slicer and your FilamentHub account in step.

- **Presets in the normal filament list.** Imported and synchronized presets keep their colour and inheritance. On OrcaSlicer 2.5.0-alpha and later a new or updated preset shows up in the list at once, with no restart.
- **Edit presets the way Orca groups them.** Familiar tabs and Simple, Advanced or Expert detail level.
- **Automatic sync.** Saving a filament or process preset in OrcaSlicer syncs it to FilamentHub when **Sync automatically** is on. Several saves in a row are combined and OrcaSlicer is never held up by the upload. A **FilamentHub Sync** action in Speed Dial starts a full sync, and problems or "restart needed" notices appear as OrcaSlicer notifications.
- **Your look.** Choose the FilamentHub appearance, or match OrcaSlicer's light or dark colours.

![A FilamentHub preset in OrcaSlicer's filament list, before and after the sync](https://api.orcaslicer.com/api/v1/bundles/media/3823bfcd-fbd7-4c27-9945-94f7fc9fac2a/content)

![Edit presets the way Orca groups them](https://api.orcaslicer.com/api/v1/bundles/media/3064ff05-e5c0-4f7c-ab58-5528e95a34cd/content)

### The plugin toolbar

- **My Spools**: your spools and their slots.
- **Catalog**: the FilamentHub catalogue of materials and presets.
- **Profile**: your presets, printers, filaments, calculations, quotations and orders.
- **Wiki**: short guides, right inside OrcaSlicer.
- **Sync**: a manual sync of the presets you selected.
- **Recover**: scans this computer for your existing OrcaSlicer presets, across all Orca accounts and version backups, and shows a checklist. Only what you tick is imported into FilamentHub. Filaments become drafts, and nothing in OrcaSlicer is overwritten.

![Usage tracked automatically: AMS slots and the spools in them](https://api.orcaslicer.com/api/v1/bundles/media/3f5d7ba8-d90f-48b0-b5aa-b212a2f99203/content)

![From G-code to a quotation](https://api.orcaslicer.com/api/v1/bundles/media/3266072f-2d25-4ef9-a03d-a16629f58f5d/content)

![For manufacturers: a brand page with its materials](https://api.orcaslicer.com/api/v1/bundles/media/31beaab3-a3a6-463c-ac73-58b5c9663e45/content)

![Plugin settings in OrcaSlicer](https://api.orcaslicer.com/api/v1/bundles/media/3c3709cf-bbf0-404a-b8b0-6277e7b5cf15/content)

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

![What is coming](https://api.orcaslicer.com/api/v1/bundles/media/3cdd9b2d-5bec-4b37-88f6-fccaed071894/content)

## Your local setup stays yours

- FilamentHub manages only the preset copies it creates. System, project, third-party and other user presets are left untouched.
- Printer access codes and API keys stay on your computer. Connection addresses can be synchronized to your FilamentHub account when you enable **Store printer addresses in FilamentHub**, and may then appear on the site.
- Slice reporting is optional. FilamentHub receives the slice details needed for history and calculations. The full G-code never leaves your computer; a calculation sends only its summary (the start and end of the file and per-part totals computed locally).
- Network discovery, profile recovery and changes to printer material systems start only from an explicit action.
- Bambu usage calculated from G-code is marked as an estimate, so it is never presented as a scale measurement.
- When the plugin loads, OrcaSlicer 2.5 shows its own window asking to let the plugin create a background thread. This is an OrcaSlicer security check for every plugin: FilamentHub runs network and file work in the background so OrcaSlicer never freezes. Answer "Yes" once and OrcaSlicer remembers it. If you answer "No", OrcaSlicer does not load the plugin. On OrcaSlicer builds before 2.5.0-alpha the question comes later, when you first open the FilamentHub tab.

## What the plugin does on your computer

- **Who it talks to.** The FilamentHub site and API (filamenthub.ru, or filamenthub.club if you choose that server in the plugin settings), and the printers you have configured. No other services.
- **Printers, only after you set them up.** A Bambu Lab printer is read over your local network: status through MQTT and, to read the file being printed, through FTPS, read-only. A Klipper printer with Moonraker is reached over HTTP at the address in your printer profile; for Happy Hare, FilamentHub sends one command to refresh its spool list, and only when you ask for it. Searching for printers (a multicast query and a listen for Bambu announcements) runs only when you press the search or start printer setup.
- **When it loads.** At start-up the plugin reads its own settings, checks the preset files in its own FilamentHub folder, and, if you have already connected a Bambu printer, reconnects to it in the background and sends its usage readings to FilamentHub. It does not open a browser or scan the network, and nothing is loaded from the site until you open the FilamentHub tab.
- **When it opens something.** The browser opens only when you click: signing in, a link to a FilamentHub page such as the wiki. The plugin never opens any other program: a quotation is previewed and printed inside the FilamentHub tab (use Print and choose Save as PDF to get a file), or opened on the site in your browser when you click Open in browser.
- **Where it writes.** Its own storage folder (settings, sign-in, state, log), either in OrcaSlicer's plugin storage or in a `.filamenthub` folder inside the OrcaSlicer data folder; and the FilamentHub preset folder under your OrcaSlicer user presets. It writes no PDF files. "Recover" and slice reading only read.
- **Permissions.** The plugin declares the permission it needs to OrcaSlicer when it loads, so you answer once in one window rather than being asked in the middle of your work. Other requests, for example a network address, are still asked by OrcaSlicer when they first happen.

## Requirements

- A FilamentHub account for the catalogue, preset synchronization, spool inventory and slice history.
- An OrcaSlicer build with Python plugin support.
- Local-network access to the printer for optional Bambu or Happy Hare integration.

On OrcaSlicer builds with the plugin preset API (2.5.0-alpha and later), a newly imported or updated preset appears in the slicer's preset selectors immediately. Older builds need a restart first.
