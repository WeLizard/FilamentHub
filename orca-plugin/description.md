FilamentHub brings filament discovery, native OrcaSlicer presets, physical spool inventory, printer material systems, and production costing into one connected workflow. Find a material, prepare it for printing, follow the spool in use, and continue from a completed slice to a calculation, quote, or order.

![Browse and import community filament presets from inside OrcaSlicer](https://api.orcaslicer.com/api/v1/bundles/media/3bc1c768-34ae-4b04-b451-28dbff52c564/content)

## From material to finished print

- **Discover useful profiles.** Browse the FilamentHub catalog inside OrcaSlicer by brand, material type, or the printer already selected in the slicer.
- **Use native OrcaSlicer presets.** Imported profiles keep their colour and inheritance and appear in a dedicated FilamentHub group in the normal filament selector.
- **Keep selected profiles synchronized.** Receive catalog updates, save your own changes, and recover existing local work as a private profile.
- **Connect profiles to physical spools.** See the material you own, its remaining weight, and its assignment to a printer or material-system slot.
- **Work with Bambu AMS and Happy Hare.** Compare FilamentHub assignments with supported printer material systems and apply prepared slot changes.
- **Track Bambu spool use over LAN.** Connect compatible Bambu printers directly and update assigned spool balances during a print, with calculated usage identified as an estimate.
- **Continue into calculations and orders.** Reuse a completed OrcaSlicer slice to calculate production cost, save an estimate, prepare a customer quote, and continue accepted work as an order.

![Saved filament presets and sync status in the FilamentHub profile](https://api.orcaslicer.com/api/v1/bundles/media/3abf7f71-9324-4e66-93c2-a2afacb03519/content)

![Imported FilamentHub presets in OrcaSlicer's native filament dropdown](https://api.orcaslicer.com/api/v1/bundles/media/3d0440c2-cfd2-4286-98b6-488c5088efcd/content)

## Built around the way you print

Use the catalog and preset library on their own, or connect them to spool inventory, printer material systems, slice history, and production costing. The optional Slicing Pipeline reporter brings completed slices into FilamentHub ready for cost calculations, saved estimates, customer quotes, and production orders.

Printer connections run from OrcaSlicer on your computer, while your FilamentHub account keeps profiles, spool history, calculations, and production records together.

![FilamentHub spool inventory with a Happy Hare gate assignment](https://api.orcaslicer.com/api/v1/bundles/media/30be9acd-e848-4da5-a03d-80217a49f564/content)

## Your local setup stays yours

- FilamentHub manages only the preset copies it creates. System, project, third-party, and other user presets are left untouched.
- Printer access codes and API keys stay on your computer. Connection addresses can be synchronized to your FilamentHub account when you enable **Store printer addresses in FilamentHub**, and may then appear on the site.
- Slice reporting is optional. FilamentHub receives the slice details needed for history and calculations; the full G-code is uploaded only when you request a calculation.
- Network discovery, profile recovery, and changes to printer material systems start only from an explicit action.
- Bambu usage calculated from G-code is marked as an estimate, so it is never presented as a scale measurement.

## Requirements

- A FilamentHub account for the catalog, preset synchronization, spool inventory, and slice history.
- An OrcaSlicer build with Python plugin support.
- Local-network access to the printer for optional Bambu or Happy Hare integration.

On current OrcaSlicer builds, a restart is required before a newly imported or updated preset appears in the slicer's preset selectors.
