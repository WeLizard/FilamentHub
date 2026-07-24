# FilamentHub plugin — changelog

Newest first. The top entry is the text pasted into the Plugin Hub on release.

## 0.0.6
- Fixed preset import/sync breaking after OrcaSlicer's plugin audit blocked reading the app config. The active preset folder is now resolved through the official preset API instead of OrcaSlicer.conf.
- Your printer and print profiles are now reported to FilamentHub during sync, so the site knows which machine a spool or material system belongs to. Only your own profiles are sent, each one is sent again only after you change it, and printer host passwords and API keys never leave your computer. Nothing is written into your slicer profiles — OrcaCloud already keeps those in step across your own installations.
- Added a "Recover" button that finds filament presets left on this computer, including ones from earlier OrcaSlicer versions and other accounts, and lets you pick which to upload as drafts.
- Added an optional setting to upload your local filament presets as drafts automatically during sync. Each preset is uploaded once, so a draft you delete on the site stays deleted.
- Sync now reports its result as a notification in the window instead of a confirmation dialog.
- Added a loading indicator while the FilamentHub catalog loads.
