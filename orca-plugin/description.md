FilamentHub connects material discovery, native filament presets, real spools, and completed slices in one OrcaSlicer workflow.

Find a material by brand, type, or printer, add its profile to OrcaSlicer's normal filament list, and keep only the profiles you choose synchronized.

![Browse and import community filament presets from inside OrcaSlicer](https://api.orcaslicer.com/api/v1/bundles/media/3e9d09ba-9208-4340-9fd9-5bb1e2a227a7/content)

## From material to finished print

- **Discover useful profiles.** Browse the catalog inside the plugin and filter it using the printer already selected in OrcaSlicer.
- **Work with native presets.** FilamentHub profiles keep their colour and inheritance and appear in a dedicated group in OrcaSlicer's normal filament selector.
- **Synchronize deliberately.** Enable synchronization per profile, pull an update, send a local edit back, or recover an existing local profile as a private draft. Local changes are never silently overwritten.
- **Connect digital profiles to real material.** Track physical spools and compare saved assignments with supported Bambu AMS and Happy Hare material systems before explicitly applying a change.
- **Reuse completed slices.** Carry stable material, printer, and print-profile identities into calculations and print history without uploading the same G-code again.

![Saved filament presets and sync status in the FilamentHub profile](https://api.orcaslicer.com/api/v1/bundles/media/331b59c4-860d-4536-aba7-a7d7d819f704/content)

![Imported FilamentHub presets in OrcaSlicer's native filament dropdown](https://api.orcaslicer.com/api/v1/bundles/media/3789ae9a-338a-4a8c-a3d8-2f14d834f157/content)

## Your local setup stays yours

- FilamentHub updates or removes only its own managed preset copies. Unmanaged OrcaSlicer profiles are left untouched.
- Printer-profile restoration and material-system changes require an explicit action.
- Printer addresses and API keys remain local to OrcaSlicer. FilamentHub receives only normalized observations needed for matching, recommendations, and spool tracking.

![FilamentHub spool inventory with a Happy Hare gate assignment](https://api.orcaslicer.com/api/v1/bundles/media/3141b362-90fc-4fec-bbb7-faea6b38f31f/content)

## Requirements and current limitation

- A free FilamentHub account for the catalog, spool inventory, and preset synchronization. Production costing and quote features may require Calculator Pro access.
- An OrcaSlicer build with Python plugin support.

The plugin is in active testing while OrcaSlicer's plugin API continues to evolve. On current builds, OrcaSlicer must be restarted before a newly imported or updated preset appears because the host cannot yet reload user presets on request.

When reporting a problem, include the OrcaSlicer build hash and FilamentHub plugin version.
