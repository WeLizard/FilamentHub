is a filament catalog with community-rated print profiles and spool tracking. The plugin opens FilamentHub (filamenthub.ru) inside OrcaSlicer:

![Browse and import community filament profiles from inside OrcaSlicer](https://api.orcaslicer.com/api/v1/bundles/media/3e9d09ba-9208-4340-9fd9-5bb1e2a227a7/content)

- Browse filament profiles by brand, material and printer. Imported profiles land in a "FilamentHub" group in the native filament dropdown with the right color and inheritance.
- Keep saved presets in sync: pull updates from your FilamentHub profile, send presets edited in OrcaSlicer back, and remove managed local copies after you unsubscribe. Local edits take priority over remote updates and are never silently overwritten.
- Choose which saved presets sync with OrcaSlicer using an explicit per-preset toggle.
- Recover filament presets left on this computer, including ones from earlier OrcaSlicer versions or another account, and pick which of them to upload as drafts.
- Your printer and print profiles are reported to FilamentHub so recommendations and spool tracking know which machine they are about. This direction is one-way: nothing is written into your slicer profiles, and printer host passwords and API keys never leave your computer.
- The machine you have selected in OrcaSlicer is offered in the catalog, so you are not asked to pick it twice.
- Sign-in survives OrcaSlicer restarts; a toolbar shows your preset counts.

![Saved filament profiles and sync status in the FilamentHub profile](https://api.orcaslicer.com/api/v1/bundles/media/331b59c4-860d-4536-aba7-a7d7d819f704/content)

![Per-preset control for enabling or disabling OrcaSlicer sync](https://api.orcaslicer.com/api/v1/bundles/media/3061ab2b-06d0-461c-b14a-9e668d0221e8/content)

![Imported FilamentHub presets in OrcaSlicer's native filament dropdown](https://api.orcaslicer.com/api/v1/bundles/media/3789ae9a-338a-4a8c-a3d8-2f14d834f157/content)

The same window also gives you access to your FilamentHub spool inventory and print-cost tools.

![FilamentHub spool inventory with a Happy Hare gate assignment](https://api.orcaslicer.com/api/v1/bundles/media/3141b362-90fc-4fec-bbb7-faea6b38f31f/content)

**Requirements:** Requires a free FilamentHub account and an OrcaSlicer build with Python plugin support.

**Active Testing & Known Limitations (Alpha):**
This plugin is in active testing. The upstream plugin API is still evolving, so updates may be frequent.
- **Preset Loading:** On current official artifacts, imported or updated presets require an OrcaSlicer restart to appear, because the host cannot yet reload filament presets on request.
- **Reporting:** Please include your OrcaSlicer build hash and plugin version when reporting a problem.
