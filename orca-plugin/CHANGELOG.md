# FilamentHub plugin — changelog

Newest first. The top entry is the text pasted into the Plugin Hub on release.

## Unreleased

## 0.2.0
- Bambu LAN consumption now follows the actual per-layer extrusion curve from the print G-code instead of assuming that every percent of progress uses the same amount of filament. The total remains the slicer's declared weight, and older files fall back to an explicitly labelled progress estimate.
- A temporary FilamentHub snapshot outage no longer drops a Bambu observation or resets its durable accounting baseline. The observation stays queued and is checked against the current spool assignment when the connection recovers.
- Slice reports now use the signed-in FilamentHub page's normal authenticated API connection. The slicing worker only saves metadata to a durable local queue and never calls the host UI; the page polls that queue later on its own UI callback. Activation, slicing, export and printer upload therefore cannot be blocked by the report transport or its audited HTTP permission dialog. Failed and signed-out deliveries remain queued for retry.
- Bambu cancellation keeps the estimated material used before stopping. Rapid transitions to idle remain in order until saved, so the end of a job is not lost between updates.
- Bambu LAN connections can record estimated filament consumption without a Bambu cloud account. Available print files and identified spool balance changes feed the same print history, with explicit estimate labels. A local journal preserves pending reports and observed spool bindings across restarts; repeated delivery does not debit a spool twice.
- Bambu 3MF jobs now use their small slice metadata even when the compressed archive contains G-code larger than the fallback extraction limit. Large normal prints no longer remain at zero consumption when the metadata already contains a safe per-filament weight.
- Consumption starts from the observed spool assignment, including a spool added during a print. File-based progress estimates remain separate from measured consumption, and unavailable evidence is not reported as zero usage.
- Saving sliced files and reporting their details now requires explicit opt-in in the slicing plugin's settings. The settings explain local G-code comments and caching, exactly which details go to the selected server, and that uploading the full G-code requires a calculation request.
- Export no longer probes the system's temporary directory, avoiding a permission request for an unrelated random file. The plugin keeps its own limited copy of enabled slice reports so a calculation remains possible after OrcaSlicer removes its working file.
- **Check materials** for Bambu and **Check printer** for Happy Hare work again in the current OrcaSlicer, and a saved slot assignment is sent to the printer right away again. The plugin used to drop these commands before contacting the printer, so the page waited and then reported a printer timeout.
- Opening OrcaSlicer after a break no longer shows a red "sync settings temporarily unavailable" message. The plugin waits for the sign-in the page renews and then runs the start-up sync that used to be skipped.
- Sync results are worded plainly and colored by meaning: green when done, yellow only when something did not sync, red when something failed. Failed presets are named instead of counted, and technical codes stay in the log.
- Automatic syncs stay quiet when nothing changed and do not repeat a warning already shown. **Sync** always reports the full result.
- Printer connections waiting for confirmation are a calm note with an **Open My Printers** button instead of a warning.
- Recovery reports how many selected items actually reached FilamentHub.
- Plugin settings in OrcaSlicer's Plugins dialog: choose the server (filamenthub.ru or filamenthub.club, applied after a restart), turn automatic sync off, keep successful automatic syncs silent, and turn on developer mode.
- In developer mode, a bug button in the toolbar and the icon on error messages open a problem report with the plugin log attached. Passwords, access codes and tokens are removed from the log first, and the report can be sent without it.
- Removed the unused single-preset import with its native dialogs and the developer-only log button.
- The Bambu network setup window and the printer profile install message are translated into every OrcaSlicer language instead of falling back to English.
- Connecting a Bambu printer over the local network again needs only its address and LAN access code. The serial number is read from the printer's own reply, so setup never asks for it and never scans the network to obtain it.
- The Bambu setup window reacts to **Search local network** and **Connect** again. Since 0.1.10 its script stopped at the first message it tried to show in the window, so neither button ever reached the plugin.
- Search and Connect now end in a clear result instead of staying busy indefinitely, and a setup request that cannot be paired reports the pairing failure instead of being ignored without an answer.
- Explicit Bambu LAN search no longer depends on a FilamentHub pairing code.
- Bambu setup accepts both native object payloads and JSON-string messages from host windows, and binds them through the setup window's own callback, so Search and Connect keep working on older compatible OrcaSlicer builds.
- Bambu LAN discovery accepts compatible printer announcement versions, and the plugin log records only safe message-boundary diagnostics, never credentials.

## 0.1.10
- Opening the FilamentHub tab no longer creates a local Python socket. The familiar plugin toolbar and embedded catalog remain intact, including navigation, sign-in, sync and recovery. An unavailable site gets a localized retry screen instead of a raw browser error. Local printer credentials use a separate host-owned dialog, while external sign-in uses a short-lived server handoff; neither path starts a local HTTP server.
- Opening Bambu setup no longer searches the local network automatically. Saved and current-profile addresses remain available, while network discovery starts only when you choose **Search local network**.
- If OrcaSlicer denies a socket requested by an explicit local action, the remote catalog remains usable and explains that no printer or account data changed.

## 0.1.9
- Saving a supported material assignment can immediately deliver that exact committed slot to Bambu LAN or Happy Hare. The material check now only reads and uploads current printer observations, and offline or uncertain delivery remains explicit.
- Checking and applying Bambu materials now finds the saved LAN connection using the same local source as its telemetry, without pairing the printer again.
- Local connection dialogs follow the FilamentHub style and temporarily hide the embedded setup wizard, so only one setup window is visible.
- Bambu LAN readings now preserve received printer status when waiting for a later report times out. Missing AMS information is kept separate from an explicitly empty feed system.
- Printer setup now searches the local IPv4 network for Bambu LAN, Moonraker and OctoPrint announcements. Saved connections and OrcaSlicer profiles remain available as clearly identified hints.
- A discovered printer can be added or attached to an existing card. Bambu setup fills its local address and serial number, then asks for the LAN code; Moonraker asks for a local API key when required. Addresses and credentials stay on the computer.
- Going back, selecting another printer or retrying a connection preserves the selected device and saved printer settings. Interrupted searches offer a calm retry and manual setup.

## 0.1.8
- Printers can now be connected or reattached through one verified setup flow without requiring a saved OrcaSlicer printer preset, while unlinking preserves the physical printer and its assignments.
- Happy Hare reports exact observed spools separately from saved assignments and shares one printer map with connections running without OrcaSlicer. Applying a map requires the printer's matching FilamentHub inventory.
- Happy Hare and Bambu LAN can now report read-only NFC/RFID tag evidence through a provider-neutral identifier without changing assignments or creating inventory.
- Bambu LAN observations are now pinned to the responding printer with an account-scoped identity token, preventing an address change or duplicate local binding from updating the wrong printer without uploading its serial number.
- Plugin storage is now initialized from OrcaSlicer's native load callback, and unload fully retires the background worker, Bambu observer and loopback server without sending a delayed Bambu update afterward.
- Every server upload, printer command and persistent-state write is now tied to the plugin lifecycle that authorized it. Unload retires fan-out printer probes and in-flight Bambu observations before they can begin another operation. An interrupted fresh Bambu pair removes the invalidated local binding and durably schedules revocation of its exact new token after a temporary network failure.
- Large device-status reports are now delivered in retry-safe bounded chunks, and an interrupted report is shown as a warning instead of being mistaken for a completed sync.

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
