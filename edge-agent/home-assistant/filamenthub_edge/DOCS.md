# FilamentHub Edge

## Install

Requires Home Assistant OS with the Apps store and network access to your
printers. Home Assistant Container users can run the same Edge image as a
separate Docker container; HACS is not the installation path for this app.

1. Open **Settings → Apps → Install app → menu → Repositories**.
2. Add `https://github.com/WeLizard/FilamentHub`, then open **FilamentHub Edge**
   in the store and select **Install**. The matching public image must have been
   released; a repository checkout is not a published release.
3. Open **Configuration**, keep the HTTPS FilamentHub address, and add the
   printer entries below. Use HA's **Edit in YAML** option if its form does not
   expose the connection list. Save, then select **Start** on the information tab.
4. Keep **Start on boot** enabled. Check **Log**, then refresh the printer card
   in FilamentHub and verify actual slots/observations, not just a paired label.

No SSH, HACS, inbound ports, Supervisor API permission or disabled protection
mode is needed. Edge starts with a brief local storage bootstrap, then runs as
an unprivileged user; Moonraker credentials stay on this host.

## Add printers

One Edge app serves multiple printers on the local network. Add one item to
`connections` for each printer, without installing a separate app. The current
Moonraker adapter supports Happy Hare and direct Klipper feed. This runtime bounds
the configuration to 32 connections; usable capacity depends on the host.

Create an Edge pairing code for the printer's material system in FilamentHub,
paste it into that connection, and enter its local Moonraker address. The app keeps printer and
slot observations synchronized while storing the cloud token and cached spool
assignments only in Home Assistant's local `/data` volume.
After the first successful pairing, clear the one-time code from the app options.
Paste a newly issued code only when rotating the same binding.

Example configuration (add entries with distinct IDs, addresses and pairing codes):

```yaml
filamenthub_url: https://filamenthub.ru
sync_interval: 30
allow_insecure_cloud: false
connections:
  - id: workshop-mmu
    name: Workshop MMU
    enabled: true
    adapter: moonraker
    material_provider: happy_hare
    moonraker_url: http://192.168.1.20:7125
    moonraker_api_key: ""
    pairing_code: FH-XXXXX-XXXXX
  - id: office-printer
    name: Office printer
    enabled: true
    adapter: moonraker
    material_provider: legacy
    moonraker_url: http://192.168.1.21:7125
    moonraker_api_key: ""
    pairing_code: FH-YYYYY-YYYYY
```

Save the app options and restart after adding or changing entries. Keep each
connection's `id` stable: it selects its private state and retry queue. Set
`enabled: false` to pause one connection. Removing an item does not delete its
credentials or queued events; restore the same ID to resume. One offline printer
does not block the others. Preserve the app's `/data` volume across restarts.

Choose `happy_hare` for an MMU managed by Happy Hare or `legacy` for a direct
Klipper feed. The app can report replay-protected filament usage when Moonraker
provides an unambiguous counter and active desired spool. It remains read-only
toward printer hardware: it does not change gates, run local commands, or write
RFID/NFC tags.

Happy Hare inventory and assignments use Moonraker's native Spoolman integration.
Follow the [printer setup guide](https://github.com/WeLizard/FilamentHub/tree/main/edge-agent#installation)
before relying on spool identity. When native Spoolman is configured or unknown,
Edge does not submit a second usage stream. Empty/unknown observations never
erase your desired spool assignments.

## Update and recovery

Use the app's **Update** action when HA offers a new version; read the changelog
and include this app in a backup first. Schedule updates/backups while printers
are idle: a cold backup briefly stops Edge so the node and connection states are
captured together. HA allows up to 210 seconds for a graceful stop. Normal
restarts and container replacement preserve the local node ID, individual
credentials and pending events in `/data`. No new pairing is needed for an update.

Do not uninstall/reinstall to update, rename connection IDs or copy a backup to
a second concurrently running Edge. A restore is recovery of this node, not
provisioning another node. Protect HA backups: they include local credentials.
After restoring, verify each binding and pending queue before resuming prints.

- **Image cannot be downloaded:** check the exact app version was published as
  a public GHCR image for your architecture. Do not enter your FilamentHub login
  as registry credentials or use an unverified replacement image.
- **App starts but no printer appears:** an empty `connections` list is valid
  but connects nothing. Add an entry, save and restart; use the printer's LAN
  address, not `localhost` or the HA address.
- **PairingRequired / AuthenticationError:** generate a new code for that same
  printer in FilamentHub, replace only its code, save and restart. Preserve the ID.
- **ProviderUnavailable:** check the local endpoint and Moonraker authentication.
  Other connections continue; do not disable authentication to resolve the error.
- **ConfigurationError / StateError:** correct the reported configuration or
  restore a known-good app backup. Do not delete state files to force startup.

The app currently has no separate ingress dashboard or HA entities. Printer and
spool state is viewed in FilamentHub; app settings and logs are managed here.
