# FilamentHub

**Self-hosted platform for 3D-printing filaments, presets, spool inventory, and brand workflows — with deep OrcaSlicer integration.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Production](https://img.shields.io/badge/status-production-green.svg)](https://filamenthub.ru)

- 🌐 **Live:** [filamenthub.ru](https://filamenthub.ru) — browse the catalog without an account
- 🐙 **OrcaSlicer plugin:** install FilamentHub from the official Orca Cloud Plugin Hub for preset sync and the embedded catalog

---

## What it is

A platform that connects three sides of the 3D-printing workflow that normally live in separate silos:

- **Filament brands** — publish official, verified presets for their materials and place QR codes on packaging so users can identify the exact catalog entry.
- **Users** — keep printer / filament / process presets in one place, sync with OrcaSlicer, track physical spools, see ratings and reviews from other users on the same material.
- **Klipper / Happy Hare / MMU setups** — connect printer feed systems through the Spoolman-compatible API and keep explicit spool assignments available to the printing workflow.

Scanning a FilamentHub QR code identifies the catalog entity. Opening the material, adding a physical spool, assigning it to a feed slot, and syncing a preset remain explicit user actions.

---

## Key features

### Filament & preset catalog
- Brand → filament line → preset hierarchy with explicit `BundleSource` and moderation pipeline
- **Star rating (1–5)** per preset with success/fail flag and per-printer-model context
- **Robust weighted-median recommendations** from trusted contributions, with confidence based on sample size
- **Auto-generated aggregate preset** that recalculates when enough trusted contributions exist for a material
- **UI-based preset editor** for supported OrcaSlicer fields with labels and validation, without requiring raw JSON editing
- System printers and per-vendor profiles imported from the OrcaSlicer system bundle with content-hash deduplication

### Spool inventory
- Per-user physical spool tracking with state, weight remaining, usage history
- Spoolman-compatible REST API + WebSocket layer — drop-in for existing Klipper ecosystems

### Brand workflow
- Brand reps self-register, verify, and publish official presets for their products
- QR-code generation for catalog materials; scanning identifies the entity and presents explicit next actions

### OrcaSlicer integration
- Official Python plugin distributed through Orca Cloud Plugin Hub
- Embedded FilamentHub catalog inside the slicer
- Two-way managed preset sync (printer / filament / process)
- HH snapshot upload pipeline

### Cost calculator (B2B)
- G-code parser for OrcaSlicer / BambuStudio / PrusaSlicer / SuperSlicer / Cura / CrealitySlicer
- Quote generator with PDF output for commercial printing services

---

## Architecture

| Layer | Stack |
|-------|-------|
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 15 · Redis 7 · Alembic |
| Frontend | React 19 · TypeScript · Vite · TailwindCSS 4 · TanStack Query · react-i18next |
| Slicer | Official OrcaSlicer Python plugin |
| Infra | Docker Compose · Nginx · SSL via acme-dns (DNS-01) |

Repository layout:

```
backend/      FastAPI application and Alembic migrations
frontend/     React application and production nginx configuration
orca-plugin/  FilamentHub plugin for OrcaSlicer
scripts/      Development, verification, and owner-run deployment utilities
```

---

## Quick start (development)

Requires Docker Desktop.

```bash
git clone https://github.com/WeLizard/FilamentHub.git
cd FilamentHub
docker compose -f docker-compose.dev.yml up --build -d
```

Then:
- Frontend: http://127.0.0.1:3000
- Backend API: http://127.0.0.1:8001
- Swagger UI: http://127.0.0.1:8001/api/v1/docs

On Windows, `./scripts/start.ps1 -Command up` is a convenience wrapper around the same development Compose file.

Production deployment is owner-run through [`scripts/deploy.sh`](scripts/deploy.sh); internal deployment notes are kept outside the public repository.

---

## Contributing

Issues and PRs welcome. The project is in active development; some areas are intentionally scoped down for the first release.

If you're a **filament brand representative** interested in publishing official presets — open an issue or contact the maintainer.

If you're working on **OrcaSlicer plugin integration** (presets, Happy Hare, Moonraker workflows), start with `orca-plugin/` and the upstream OrcaSlicer plugin APIs.

---

## Acknowledgements

FilamentHub grew out of the open-source 3D-printing ecosystem. We are especially grateful to:

- [OrcaSlicer](https://github.com/OrcaSlicer/OrcaSlicer) and all of its contributors. Working with OrcaSlicer inspired the original idea behind FilamentHub: make materials, presets, printers, and everyday printing workflows easier to connect and reuse.
- [Spoolman](https://github.com/Donkie/Spoolman), Daniel Hultgren, and its contributors. Spoolman's public API and its integration with Moonraker provided a valuable interoperability reference while we built FilamentHub's independently implemented Spoolman-compatible API for Moonraker and Happy Hare.

No Spoolman source code is included in FilamentHub. These projects are independent; this acknowledgement does not imply affiliation or endorsement.

---

## License

[GNU Affero General Public License v3.0](LICENSE)

Self-hosting and modification are permitted under AGPL-3.0 terms. If you run a modified version as a network service, you must make your modifications available to users of that service.
