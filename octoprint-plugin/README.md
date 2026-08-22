# FilamentHub Bridge for OctoPrint

FilamentHub Bridge is the native outbound connector between a local OctoPrint
instance and a FilamentHub material system. It synchronizes the slots and spool
assignments the user selected in FilamentHub, reports the locally selected slot,
and sends measured extrusion after a terminal print event with durable retry
identifiers. Assigned spools are also shown in OctoPrint's sidebar, where a
manual setup can switch the currently loaded spool without opening the main
Bridge tab.

The Bridge does not expose OctoPrint to the public internet. It initiates HTTPS
requests to the FilamentHub instance configured by the user. It does not require
Spoolman or SpoolManager and does not copy their local databases.

## Pairing

1. Add an OctoPrint material system to an existing printer in FilamentHub.
2. Ask FilamentHub for a short-lived pairing code.
3. Open the **FilamentHub** tab in OctoPrint, select `filamenthub.ru` or
   `filamenthub.club`, enter the pairing code, then select **Connect**.
4. The assigned slots appear in OctoPrint. Choose the routing mode that matches
   the printer:
   - **Manual spool switching** attributes extrusion to the slot selected in the
     main tab or sidebar. G-code `Tn` commands do not change that selection.
   - **Follow G-code tools** uses an explicit `Tn -> FilamentHub slot` table. It
     supports virtual tools, MMU workflows, multiple physical extruders, IDEX
     and toolchanger printers without assuming that a tool number equals a slot
     number. By default, tools follow the visible slot order (`T0 -> #1`,
     `T1 -> #2`, ...); an optional custom table handles non-standard layouts.
     Extrusion position is tracked separately for every tool.

If a print selects an unmapped `Tn`, the Bridge leaves that extrusion
unassigned and displays a warning instead of charging it to an unrelated spool.
Only standard `Tn` commands handled by OctoPrint are interpreted as tool
selections; printer-specific macros are not guessed.

The bridge token is stored in OctoPrint's local plugin settings and is filtered
from OctoPrint's settings API. Terminal print events are kept in a local outbox
until FilamentHub acknowledges them.
