# FilamentHub Edge

Create an Edge pairing code for the printer's material system in FilamentHub,
paste it here, and enter the local Moonraker address. The app keeps printer and
slot observations synchronized while storing the cloud token and cached spool
assignments only in Home Assistant's local `/data` volume.

Choose `happy_hare` for an MMU managed by Happy Hare or `legacy` for a direct
Klipper feed. This release is read-only toward printer hardware: it does not
change gates, consume spool weight, or write RFID/NFC tags.
