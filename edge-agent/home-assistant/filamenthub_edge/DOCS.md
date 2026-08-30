# FilamentHub Edge

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

Example connection (repeat with a distinct `id`, address, and pairing code):

```yaml
connections:
  - id: workshop-mmu
    name: Workshop MMU
    enabled: true
    adapter: moonraker
    material_provider: happy_hare
    moonraker_url: http://192.168.1.20:7125
    moonraker_api_key: ""
    pairing_code: FH-XXXXX-XXXXX
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
