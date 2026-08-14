FilamentHub brings community filament presets, physical spool inventory, and print-cost tools directly into OrcaSlicer.

Find a filament by brand, material, or printer, import its preset into OrcaSlicer's native filament list, and keep the presets you choose synchronized with your FilamentHub account.

![Browse and import community filament presets from inside OrcaSlicer](https://api.orcaslicer.com/api/v1/bundles/media/3e9d09ba-9208-4340-9fd9-5bb1e2a227a7/content)

## What you can do

- **Find and import filament presets.** Browse the FilamentHub catalog without leaving OrcaSlicer. Imported presets appear in a dedicated "FilamentHub" group in the native filament dropdown with their color and settings intact.
- **Keep selected presets synchronized.** Choose exactly which saved presets connect to OrcaSlicer. Pull updates from FilamentHub or send changes made in OrcaSlicer back to your account.
- **Recover presets already on your computer.** Find filament presets left by earlier OrcaSlicer versions or another local account, then choose which ones to upload to FilamentHub as drafts.
- **Use the printer you already selected.** FilamentHub carries the active OrcaSlicer printer into the catalog, so you do not have to select the same machine again.
- **Work with real spools and print costs.** Open your FilamentHub spool inventory and use a completed slice in the print-cost calculator without uploading the same G-code manually.
- **Restore managed printer profiles when you need them.** A printer card can restore its FilamentHub-managed machine and process profiles through an explicit action.
- **Reconcile Happy Hare locally.** Check the real gate map through OrcaSlicer, compare it with FilamentHub, and explicitly choose whether to accept the printer assignments or apply the saved map. Unknown and conflicting spools are left untouched.

![Saved filament presets and sync status in the FilamentHub profile](https://api.orcaslicer.com/api/v1/bundles/media/331b59c4-860d-4536-aba7-a7d7d819f704/content)

![Choose which presets synchronize with OrcaSlicer](https://api.orcaslicer.com/api/v1/bundles/media/3061ab2b-06d0-461c-b14a-9e668d0221e8/content)

![Imported FilamentHub presets in OrcaSlicer's native filament dropdown](https://api.orcaslicer.com/api/v1/bundles/media/3789ae9a-338a-4a8c-a3d8-2f14d834f157/content)

## Your local setup stays under your control

- Only the presets you explicitly enable are synchronized.
- Local edits take priority over remote updates and are never silently overwritten.
- FilamentHub only removes local preset copies that it manages after you unsubscribe; unmanaged OrcaSlicer profiles are left untouched.
- Automatic printer and process-profile reporting is one-way. Managed profile restoration and Happy Hare assignment changes happen only after an explicit action.
- Happy Hare is reached by the plugin on your local network; the FilamentHub website never opens a connection into your LAN.
- Printer host passwords and API keys never leave your computer.

Your FilamentHub sign-in survives OrcaSlicer restarts, and the plugin toolbar shows the current preset and synchronization status.

![FilamentHub spool inventory with a Happy Hare gate assignment](https://api.orcaslicer.com/api/v1/bundles/media/3141b362-90fc-4fec-bbb7-faea6b38f31f/content)

## Requirements and alpha status

- A free FilamentHub account for the catalog, spool inventory, and preset synchronization. Print-cost and quote features may require Calculator Pro access.
- An OrcaSlicer build with Python plugin support.

The plugin is in active testing while OrcaSlicer's plugin API continues to evolve. Updates may be frequent.

On current official artifacts, OrcaSlicer must be restarted before a newly imported or updated preset becomes available in the filament list because the host cannot yet reload presets on request.

When reporting a problem, please include your OrcaSlicer build hash and FilamentHub plugin version.

## One connected workflow

FilamentHub connects the parts of a print that are usually scattered between a catalog, the slicer, a spool tracker, and a calculator:

1. **Start with the printer already selected in OrcaSlicer.** Open FilamentHub from the plugin and the catalog carries that printer into the search and recommendation flow.
2. **Choose the material and preset.** Find an official or community preset for the filament you want to use, save it to your FilamentHub profile, and enable OrcaSlicer synchronization when you want a local copy.
3. **Use it as a native OrcaSlicer preset.** After the required restart on current builds, select the imported preset from the normal filament dropdown and keep working in the familiar OrcaSlicer interface.
4. **Connect the preset to a real spool.** Register the physical spool in FilamentHub by QR code or manual entry, record its remaining material, and, when applicable, assign it to a Happy Hare or other supported material slot.
5. **Slice the model.** Enable FilamentHub once in the process preset's "Slicing Pipeline Plugin" field. Future slices can then be offered to FilamentHub without sending printer credentials or treating the slice as confirmed material consumption.
6. **Calculate the job without uploading the same file again.** Open the print-cost tools, choose the captured slice, and calculate it using the G-code evidence together with your saved printer, material, and economic settings.
7. **Turn the calculation into reusable work.** Save the result in calculation history and, when needed, prepare a customer quote or PDF from the same data instead of rebuilding the job in another tool.
8. **Keep the setup recoverable.** Preset changes can return to your FilamentHub profile, selected presets stay synchronized, and local presets can be recovered as drafts after an OrcaSlicer update, reinstall, or account change.

The result is one continuous path from choosing a filament to a native OrcaSlicer preset, a known physical spool, a sliced job, and an explainable cost calculation—while every synchronization and restoration step remains under your control.
