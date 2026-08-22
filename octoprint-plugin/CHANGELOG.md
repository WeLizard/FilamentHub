# FilamentHub Bridge for OctoPrint — changelog

Newest first. The top entry is used for GitHub release notes.

## Unreleased
- Shows the Bridge's live FilamentHub slot and spool snapshot in the OctoPrint sidebar, including the active slot, material colour and remaining weight.
- Lets users choose `filamenthub.ru` or `filamenthub.club` while pairing and shows pairing failures directly in the connection form.
- Revokes the server-side Bridge credential before removing the local connection.
- Adds explicit manual and G-code tool routing modes, including arbitrary
  `Tn -> slot` mappings for virtual tools, MMU workflows, multiple extruders,
  IDEX and physical toolchanger printers.
- Preserves each tool's own absolute extrusion position and carries a standard
  tool selection made before a print into that print's usage accounting.
- Uses the intuitive `T0 -> slot #1`, `T1 -> slot #2` order by default and keeps
  arbitrary mappings behind an optional advanced control.
- Refuses to attribute an unmapped G-code tool to a fallback spool and surfaces
  the missing mapping in OctoPrint while the print is running.
- Moves connection controls into a connected-device summary and keeps empty
  slots in the full Bridge view instead of cluttering the sidebar.

## 0.1.0
- Connects OctoPrint to a FilamentHub material system without exposing OctoPrint to the public internet.
- Synchronizes assigned slots and spool identities, tracks measured extrusion and retries terminal usage reports until FilamentHub acknowledges them.
- Keeps the bridge token in OctoPrint's restricted plugin settings and supports explicit pairing and unpairing.
