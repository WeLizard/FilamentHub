# FilamentHub plugin — changelog

Newest first. The numbered entry matching the plugin version is used for release notes.

## 0.2.8
- Signing in and exporting a problem report no longer ask for the computer's hostname. The background key is labelled **OrcaSlicer** without reading the machine name.
- On current OrcaSlicer builds, the plugin declares access to the two FilamentHub server addresses and background threads through the standard permission dialog. Older builds keep their supported permission flow; local-printer operations can still need separate permission.
- Permission refusals and host errors are respected instead of silently falling back to a smaller request.
- The embedded website has an independent loading and recovery screen for startup failures, with a reload action and a safe diagnostic code. This part is delivered with the website update.

## 0.2.7
- QIDI printers with a QIDI Box: the plugin now reads which slots hold filament, and their material and colour, straight from the printer over your network and shows them in the printer's material system. Nothing is sent to the printer. It needs no extra setup beyond the printer connection you already use; usage is still counted by the printer's own Spoolman connection.
- When a spool or a material on your shelf runs low, OrcaSlicer now shows a notification with the amount left. Each alert appears once, and clicking it opens your Spools on the site. It needs OrcaSlicer 2.5 or later and a signed-in FilamentHub tab.
- Low-stock notifications keep arriving after the 30-minute sign-in of the FilamentHub tab has expired. The tab now issues a separate key for this computer, which can only report and read alerts, never edit your presets. Signing out of the tab revokes it, and if you revoke it on the site the plugin falls back to the tab's sign-in and gets a new key the next time you open the tab.
- A Bambu printer that is switched off is no longer mistaken for OrcaSlicer being closed: FilamentHub keeps showing that the plugin is running and that the printer is not answering.

## 0.2.6
- FilamentHub now tells OrcaSlicer up front that it needs a background thread, so the permission question appears once when the plugin loads instead of when you first open its tab. If you answer "No", OrcaSlicer does not load the plugin.
- The plugin no longer saves quotation PDFs or opens any program for them. A quotation is previewed and printed inside the FilamentHub tab: press Print and choose Save as PDF to get a file. In the workspace, Open in browser opens the quotation on the site after you sign in.
- The browser and FTP modules are no longer loaded at start-up; each is used only by the action that needs it (opening a sign-in or wiki link, reading a Bambu printer's files over your network).
- The plugin always connects to the FilamentHub server chosen in its settings (filamenthub.ru or filamenthub.club). It no longer reads a server address from the environment.

## 0.2.5
- On OrcaSlicer builds with the plugin preset API (2.5.0-alpha and later), imported and synchronized presets now appear in the preset selectors right away, with no restart. Your selection and unsaved edits are kept.
- Printer and print profiles installed or recovered from FilamentHub appear right away too, on the same builds.
- On older builds, or if OrcaSlicer rejects the reload, FilamentHub still tells you that a restart is needed.
- FilamentHub now follows OrcaSlicer's interface language in its tab, settings and messages. Before, it could not read that language, so the page followed the system default and plugin messages were in English.
- OrcaSlicer reports Catalan, Basque and Hungarian as English and Traditional Chinese as Simplified Chinese, so FilamentHub shows those languages the same way.
- Saving a filament or process preset in OrcaSlicer now syncs it to FilamentHub automatically when **Sync automatically** is on. Several saves in a row are combined, and OrcaSlicer is never held up by the upload. Machine profiles are not synced by a save.
- Sync problems and "restart needed" notices now appear as OrcaSlicer notifications, so you see them with the FilamentHub tab closed.
- New **FilamentHub Sync** action in Speed Dial: starts a full sync and reports the result as a notification.
- Problem reports now include the OrcaSlicer version.
- OrcaSlicer asks once for permission to create a background thread. FilamentHub asks when you open its tab, and if you answer "No" it says so instead of silently skipping the sync. Background features such as the Bambu observer wait until the permission exists.
- Before reloading presets, FilamentHub checks that OrcaSlicer lists the FilamentHub bundle; if not, it keeps the restart message and records why.

## 0.2.4
- Open My Spools when the FilamentHub tab starts; the catalog remains available from its own tab.
- Choose FilamentHub or OrcaSlicer appearance for the embedded page. OrcaSlicer appearance follows the host's light and dark colors.
- After a local printer connection drops, reconnecting starts with fresh printer information and resumes material-use estimates from a new observed baseline.
- Save a quotation PDF to your Downloads folder and open it in your PDF viewer straight from the embedded FilamentHub page.

## 0.2.3
- G-code made with the FilamentHub slicing plugin selected now always carries the identifiers of the FilamentHub profiles it used, even when sending slice details is off. FilamentHub can then recognise your materials when you open that file in the calculator. Nothing is sent without the existing option.
- A failure while adding these identifiers never affects the exported or uploaded file.
- New slices reach the open FilamentHub tab as soon as they are ready, and the tab checks once when it opens, when you sign in and when you return to it. It no longer asks the plugin every few seconds.
- Using a slice from OrcaSlicer in the FilamentHub calculator now works for prints of any size. Only a small summary of the slice is sent to FilamentHub, so the full G-code never leaves your computer, and each plate of a multi-plate project becomes its own calculation.
- While a long slice is being read, its entry in the list shows the progress, and reading it no longer holds up synchronization.

## 0.2.2
- Synchronized filament presets now appear for every printer. A preset created from a copy of a vendor profile (for example Bambu X1 only) is no longer hidden on other machines.
- Presets sent from OrcaSlicer to FilamentHub keep every value they print with, including the ones inherited from a vendor profile other users may not have.
- Existing FilamentHub presets are refreshed once after the update.

## 0.2.1
- Keep saved Bambu LAN credentials when the FilamentHub connection needs repair. Reconnect verified same-account bindings without re-entering the access code.
- Preserve damaged connection files and distinguish LAN access errors from FilamentHub connection errors.
- Report synchronized files separately from presets actually loaded by OrcaSlicer.

## 0.2.0
- Track estimated Bambu filament use over LAN without a Bambu Cloud account. Usage follows the completed G-code layers, updates the assigned spool automatically, and remains clearly labelled as an estimate.
- Keep partial Bambu usage when a print is cancelled, start from a spool assigned during an active print, and preserve pending accounting across restarts or temporary FilamentHub outages without charging the same material twice.
- Optionally send completed OrcaSlicer slices to FilamentHub for production calculations, quotes, and orders. Reports wait safely when signed out or offline and no longer block plugin activation, slicing, export, or sending a job to the printer.
- Explain the slice reporter before it is enabled: what stays on the computer, which slice details are sent, and that the full G-code is uploaded only after an explicit calculation request.
- Restore **Check materials** for Bambu, **Check printer** for Happy Hare, and immediate delivery of a saved slot assignment to a supported printer.
- Fix Bambu LAN setup on current OrcaSlicer builds. Connecting again needs only the printer address and LAN access code; search runs only when requested and always ends with a clear result.
- Make synchronization quieter and easier to understand: automatic sync stays silent when nothing changed, warnings identify the affected presets, and pending printer connections use a calm action instead of an error.
- Add plugin settings for server choice, automatic synchronization, success notifications, and developer mode. Problem reports can include a redacted plugin log.
- Translate Bambu setup, connection results, synchronization messages, and other native plugin screens across OrcaSlicer's supported languages.
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
