# PR #14992 page fixture

Target artifact:

- PR: `OrcaSlicer/OrcaSlicer#14992`
- head: `acb0be6ed90fe7714952a1c4a8decbab4ca82510`
- Windows Actions run: `30477542847`
- artifact ID: `8737744927`
- artifact: `OrcaSlicer_Windows_PR14992_x64_portable`

The fixture checks only integration behaviour used by FilamentHub and Print
Farm:

- the page fills and tracks the main tab viewport;
- an adjacent SVG is accepted as the tab icon;
- `window.orca` messages round-trip to Python;
- a nested frame does not receive its own injected bridge;
- WebGL/WebGL2 availability is visible for later WebView diagnostics;
- capability disable, enable, reload and restart do not duplicate the page.

The current draft always presents an enabled page capability as a tab. The
desired tab/window preference is host-owned feedback, not emulated by this
fixture.
