# FilamentHub plugin — changelog

Newest first. The top entry is the text pasted into the Plugin Hub on release.

## 0.0.6
- Fixed import and sync breaking after OrcaSlicer's plugin audit blocked reading the app config.
- Your printer and print profiles now reach FilamentHub during sync, so the site knows which machine a spool or material belongs to. Only your own profiles, each one again only after you change it; printer host passwords and API keys never leave your computer. Nothing is written into your slicer profiles.
- FilamentHub now knows which machine you have selected in OrcaSlicer and offers it in the catalog instead of asking you again.
- New "Recover" button finds filament presets left on this computer — including ones from earlier OrcaSlicer versions and other accounts — and lets you choose which to upload as drafts. Sync can also do this automatically, uploading each preset once.
- Sync reports its result in the window instead of a dialog, and the catalog shows a loading indicator.
- New "Log" button copies the plugin's diagnostic log so you can attach it to a beta report. The log is capped in size and your home folder is replaced with ~ before anything is written.
