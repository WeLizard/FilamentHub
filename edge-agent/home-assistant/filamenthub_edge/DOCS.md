# FilamentHub Edge

The target is one Edge app serving multiple printers on the local network through
supported adapters. The current app options support only one Moonraker endpoint
and one printer binding; multi-printer configuration is not implemented yet.

Create an Edge pairing code for the printer's material system in FilamentHub,
paste it here, and enter the local Moonraker address. The app keeps printer and
slot observations synchronized while storing the cloud token and cached spool
assignments only in Home Assistant's local `/data` volume.
After the first successful pairing, clear the one-time code from the app options.
Paste a newly issued code only when rotating the same binding.

Choose `happy_hare` for an MMU managed by Happy Hare or `legacy` for a direct
Klipper feed. The app can report replay-protected filament usage when Moonraker
provides an unambiguous counter and active desired spool. It remains read-only
toward printer hardware: it does not change gates, run local commands, or write
RFID/NFC tags.
