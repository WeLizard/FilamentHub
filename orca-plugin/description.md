FilamentHub connects material discovery, native filament presets, real spools, and completed slices in one OrcaSlicer workflow. Find a material by brand, type, or printer, add its profile to OrcaSlicer's normal filament list, and keep only the profiles you choose synchronized.

![Browse and import community filament presets from inside OrcaSlicer](https://api.orcaslicer.com/api/v1/bundles/media/3bc1c768-34ae-4b04-b451-28dbff52c564/content)

## From material to finished print

- **Discover useful profiles.** Browse the catalog inside the plugin and filter it using the printer already selected in OrcaSlicer.
- **Work with native presets.** FilamentHub profiles keep their colour and inheritance and appear in a dedicated group in OrcaSlicer's normal filament selector.
- **Synchronize deliberately.** Enable synchronization per profile, pull an update, send a local edit back, or recover an existing local profile as a private draft. Local changes are never silently overwritten.
- **Connect digital profiles to real material.** Track physical spools and compare saved assignments with supported Bambu AMS and Happy Hare material systems before explicitly applying a change.
- **Track Bambu spool use over LAN.** A direct local connection can update the assigned spool balance during a print without Bambu Cloud. Calculated deductions are clearly marked as estimates.
- **Continue from slices to production.** Reuse a completed OrcaSlicer slice for cost calculations and print history, then save an estimate, prepare a customer quote, or continue accepted work as an order.

![Saved filament presets and sync status in the FilamentHub profile](https://api.orcaslicer.com/api/v1/bundles/media/3abf7f71-9324-4e66-93c2-a2afacb03519/content)

![Imported FilamentHub presets in OrcaSlicer's native filament dropdown](https://api.orcaslicer.com/api/v1/bundles/media/3d0440c2-cfd2-4286-98b6-488c5088efcd/content)

## Your local setup stays yours

- FilamentHub updates or removes only its own managed preset copies. Unmanaged OrcaSlicer profiles are left untouched.
- Printer-profile restoration and material-system changes require an explicit action.
- Printer access codes and API keys remain local to OrcaSlicer. Connection addresses can be synchronized to your FilamentHub account when you enable **Store printer addresses in FilamentHub**, and may then appear on the site.
- Slice reporting is optional. FilamentHub receives the slice details used for history and calculations; the full G-code is uploaded only when you explicitly request a calculation.
- Bambu usage calculated from G-code is identified as an estimate rather than a scale measurement.

![FilamentHub spool inventory with a Happy Hare gate assignment](https://api.orcaslicer.com/api/v1/bundles/media/30be9acd-e848-4da5-a03d-80217a49f564/content)

## Requirements and current limitation

- A free FilamentHub account for the catalog, spool inventory, and preset synchronization. Production costing, customer quotes, and order features may require Calculator Pro access.
- An OrcaSlicer build with Python plugin support.
- Local-network access to the printer for optional Bambu or Happy Hare integration.

**The plugin is in active testing while OrcaSlicer's plugin API continues to evolve.** On current builds, OrcaSlicer must be restarted before a newly imported or updated preset appears because the host cannot yet reload user presets on request.

When reporting a problem, include the OrcaSlicer build hash and FilamentHub plugin version.