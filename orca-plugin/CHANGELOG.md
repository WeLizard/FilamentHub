# FilamentHub plugin — changelog

Newest first. The top entry is the text pasted into the Plugin Hub on release.

## Unreleased

## 0.1.6
- Local profile identity is now stable across Windows and Linux, allowing the release checks and synchronization to use the same saved OrcaSlicer profile paths on every supported platform.

## 0.1.5
- Synced material presets now retain their exact FilamentHub preset and version identity when OrcaSlicer saves them. Allowed local edits survive the following synchronization, including settings introduced by newer OrcaSlicer builds.
- **Save As** creates a separate private draft instead of modifying the managed source, and unsaved editor changes are never uploaded.
- FilamentHub version choices are synchronized exactly. Editing another author's managed preset creates a personal preset derived from that specific version rather than changing the shared source.
- The new Recovery Center restores only the managed machine and print profiles you explicitly select and can quarantine individual managed copies without touching original or user-owned presets.
- Synchronization follows OrcaSlicer's current account folder, presents material presets as `Type • Brand • Name`, and shuts down its background services cleanly with the plugin lifecycle.
- The native interface is localized for all 23 OrcaSlicer languages, while the embedded page is restricted to trusted FilamentHub navigation and browser-based sign-in.

## 0.1.4
- The new Recovery Center scans local FilamentHub-managed machine and print profiles, restores only profiles you explicitly select, and can quarantine individual managed copies without touching original, built-in, user-owned, or differently scoped OrcaSlicer presets.
- Preset sync no longer writes into a stale signed-in account folder after OrcaSlicer switches back to its default local profile.
- Synced filament presets use the recognizable `Type • Brand • Name` label in OrcaSlicer without changing their names on FilamentHub.
- Plugin-owned workers, the local Bambu observer and loopback shell now follow OrcaSlicer's capability lifecycle and stop on cancellation/unload; older OrcaSlicer builds retain the existing registration fallback.
- The embedded page can no longer navigate its iframe or open a popup to another site. Internal FilamentHub routes and external-browser OAuth remain available.
- The native FilamentHub plugin interface is now fully localized for all 23 languages available in OrcaSlicer, including navigation, synchronization, recovery, connection status, Bambu LAN controls and error messages.
- The embedded FilamentHub site now receives a supported language explicitly: Russian and Chinese follow OrcaSlicer, while other OrcaSlicer languages open the English site instead of showing a maintenance page.

## 0.1.3
- Local filament presets imported from OrcaSlicer now keep the same FilamentHub identity after a rename, while **Save As** remains a separate profile.
- Sync handles every imported preset independently: rejected items remain available for retry, and profiles that need your review are reported instead of being silently treated as complete.
- Print-profile compatibility fields from current OrcaSlicer nightlies are normalized before upload, preventing an entire profile batch from being reported as failed.
- The catalog-wide **Sync** action now reports filament presets, printer configurations and print profiles separately, follows the user's sync permissions for each direction, and keeps printer-bundle restore as an explicit action on the selected printer.
- Interrupted profile scans no longer finalize a partial snapshot, and a single rejected profile no longer prevents valid profiles in the same batch from synchronizing.
- Bambu LAN status now sends changes plus a lightweight heartbeat and respects server backoff, reducing repeated traffic without losing the live connection state.

## 0.1.2
- Presets that OrcaSlicer silently refused now load. A single value in a shape the slicer cannot read used to cost the whole preset while the file sat on disk looking synchronised; values are now sent in a shape it accepts, and settings the plugin does not recognise travel through untouched.
- The same fix applies to printer and print profiles.
- A profile is checked before it is written, so a working file is never replaced by one the slicer cannot load. A damaged local file is restored from FilamentHub instead of sending the damage back.
- The **FilamentHub** tab in the filament list now shows only what is actually synchronised. Files left behind by older plugin versions move into a private folder inside OrcaSlicer's data directory, so nothing is deleted and anything can be brought back.
- The log now separates what you asked to synchronise, what is on disk and what OrcaSlicer really loaded, including profiles waiting for a restart.

## 0.1.1
- Saved material assignments can be previewed in **My Filaments** and explicitly applied to editable Bambu AMS slots through the paired local connection; RFID trays, stale previews and assignments during active prints are left untouched.
- Bambu LAN connections now survive plugin package updates and are reported as live only after real printer data has been received.
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
