# FilamentHub Bridge for OctoPrint — changelog

Newest first. The top entry is used for GitHub release notes.

## Unreleased
- Shows the Bridge's live FilamentHub slot and spool snapshot in the OctoPrint sidebar, including the active slot, material colour and remaining weight.

## 0.1.0
- Connects OctoPrint to a FilamentHub material system without exposing OctoPrint to the public internet.
- Synchronizes assigned slots and spool identities, tracks measured extrusion and retries terminal usage reports until FilamentHub acknowledges them.
- Keeps the bridge token in OctoPrint's restricted plugin settings and supports explicit pairing and unpairing.
