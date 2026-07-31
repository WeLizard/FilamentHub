# FilamentHub Bridge for OctoPrint

FilamentHub Bridge is the native outbound connector between a local OctoPrint
instance and a FilamentHub material system. It synchronizes the slots and spool
assignments the user selected in FilamentHub, reports the locally selected slot,
and sends measured extrusion after a terminal print event with durable retry
identifiers.

The Bridge does not expose OctoPrint to the public internet. It initiates HTTPS
requests to the FilamentHub instance configured by the user. It does not require
Spoolman or SpoolManager and does not copy their local databases.

## Pairing

1. Add an OctoPrint material system to an existing printer in FilamentHub.
2. Ask FilamentHub for a short-lived pairing code.
3. Open the **FilamentHub** tab in OctoPrint, enter the FilamentHub address and
   the pairing code, then select **Connect**.
4. The assigned slots appear in OctoPrint. For a single-tool machine, slot 1 is
   selected automatically. Multi-slot systems use explicit manual selection by
   default; tool-to-slot mapping can be enabled when tools really are slots.

The bridge token is stored in OctoPrint's local plugin settings and is filtered
from OctoPrint's settings API. Terminal print events are kept in a local outbox
until FilamentHub acknowledges them.
