# FilamentHub plugin — changelog

Newest first. The top entry is the text pasted into the Plugin Hub on release.

## 0.1.1
- Saved material assignments can be previewed in **My Filaments** and explicitly applied to editable Bambu AMS slots over the paired local connection; RFID trays, stale previews and active prints are left untouched.
- Bambu LAN connections now survive plugin package updates, and the site reports a connection as live only after real printer data has arrived.
- Physical printers, their OrcaSlicer machine configurations and compatible print profiles now stay connected without collapsing different network printers or filling FilamentHub with duplicate factory profiles.
- Happy Hare v4 assignments can be checked from **My Filaments**. The plugin compares the real local gate map with FilamentHub and lets you explicitly choose the direction; unknown or conflicting spools are never changed automatically.
- Completed slices now carry stable FilamentHub material, print-profile and printer-profile identities into calculations and print history without relying on OrcaSlicer profile names.
- Printer addresses and API keys remain local to OrcaSlicer. FilamentHub receives only the normalized observations needed for matching, recommendations and spool tracking.

## 0.1.0
- A printer card can now explicitly restore its FilamentHub-managed OrcaSlicer machine and print profiles. Existing unmanaged profiles are never overwritten.
- Automatic machine and print profile reporting remains one-way; restoration happens only when you request it and requires an OrcaSlicer restart.
- Native plugin messages now include English, Russian, Simplified Chinese and Traditional Chinese, with per-message English fallback for other OrcaSlicer languages.
- OrcaSlicer builds with Plugin Pages support open FilamentHub as a native tab with its own icon; existing builds keep the separate catalog window.

## 0.0.9
- Follows OrcaSlicer's interface language for connection and error messages, with a fallback for older builds.
- Uses OrcaSlicer's private plugin storage and preset APIs when available instead of reopening host files.
- Reuses background workers and shuts down its local bridge cleanly, reducing permission prompts and exit hangs on current plugin-system builds.

## 0.0.8
- Fixed the plugin connecting to the wrong address, which left it unable to reach FilamentHub. If 0.0.7 did nothing for you, this is why.

## 0.0.7
- The print calculator on FilamentHub now picks up what you slice in OrcaSlicer: choose a slice and it is counted as if you had uploaded the file yourself. Switch it on once by choosing FilamentHub in the process settings, in the "Slicing Pipeline Plugin" field.

## 0.0.6
- Fixed import and sync breaking after OrcaSlicer's plugin audit blocked reading the app config.
- Your printer and print profiles now reach FilamentHub during sync, so the site knows which machine a spool or material belongs to. Only your own profiles, each one again only after you change it; printer host passwords and API keys never leave your computer. Nothing is written into your slicer profiles.
- FilamentHub now knows which machine you have selected in OrcaSlicer and offers it in the catalog instead of asking you again.
- New "Recover" button finds filament presets left on this computer — including ones from earlier OrcaSlicer versions and other accounts — and lets you choose which to upload as drafts. Sync can also do this automatically, uploading each preset once.
- Sync reports its result in the window instead of a dialog, and the catalog shows a loading indicator.
- New "Log" button copies the plugin's diagnostic log so you can attach it to a beta report. The log is capped in size and your home folder is replaced with ~ before anything is written.
