# PrusaLink answers

Built by hand from the code that writes each answer; not captured from a printer.
No Prusa printer was on hand when they were made.

- `buddy_*.json` — Prusa-Firmware-Buddy b1043d68 (`lib/WUI/link_content/basic_gets.cpp`,
  `lib/WUI/nhttp/status_renderer.cpp`): an MK4S printing, no MMU.
- `buddy_info_mmu.json` — the same printer with an MMU3 switched on.
- `prusalink_*.json` — Prusa-Link 601c81a6 (`prusa/link/web/main.py`): an MK3S idle.
- `octoprint_version.json` — a real OctoPrint behind a profile of type PrusaLink.

Shared by the OrcaSlicer plugin and FH Edge, so both read the same answers.
