# SDCP printer fixtures

Shared by the OrcaSlicer plugin and FH Edge. Only `status_idle.json` and
`attributes.json` come from a real printer; no printer of FilamentHub's own
produced any of them. The SDCP printer known so far is the Elegoo Centauri
Carbon.

## Captured

`status_idle.json` and `attributes.json` are the status and attributes
messages that a Centauri Carbon on firmware V1.4.49 returned to a read-only
SDCP session. They were published in TigerTag-Studio-Manager issue #41
(2026-10-08). The printer's identifiers were masked there: the `MainboardID`
here is the example one from OrcaSlicer's `ElegooLink.cpp`, and the MAC address
is made up. The capture shows a quirk worth keeping: an idle printer still
carries the last job's totals and `PrintInfo.Status` 8.

## Written by hand

These follow the field names in the sources below, with made-up values.

- `status_printing.json` is the same capture with the job fields of a running print.
- `canvas_response.json` is the answer to SDCP command 324. It is shaped as
  Elegoo's own LAN library reads it: elegooofficial/elegoo-link @ ec2d2269,
  `elegoo_fdm_cc_message_adapter.cpp`, the response in `Data.Data` with `Ack`
  (l. 353-410) and `handleCanvasStatus` (l. 902-947). The tests replace
  `REQUEST_ID` with the id they sent.
- Trays are numbered from 0, as danielcherubini/elegoo-homeassistant @ ce9c1559
  reads them (`sdcp/models/ams.py`).
