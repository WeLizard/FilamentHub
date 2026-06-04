# FilamentHub

**Self-hosted platform for 3D-printing filaments, presets, spool inventory, and brand workflows — with deep OrcaSlicer integration.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Production](https://img.shields.io/badge/status-production-green.svg)](https://filamenthub.ru)

- 🌐 **Live:** [filamenthub.ru](https://filamenthub.ru) — browse the catalog without an account
- 🐙 **OrcaSlicer fork:** [WeLizard/OrcaSlicer](https://github.com/WeLizard/OrcaSlicer) — two-way preset sync + embedded WebView panel

---

## What it is

A platform that connects three sides of the 3D-printing workflow that normally live in separate silos:

- **Filament brands** — publish official, verified presets for their materials, with QR codes on packaging that auto-import into a user's profile.
- **Users** — keep printer / filament / process presets in one place, sync with OrcaSlicer, track physical spools, see ratings and reviews from other users on the same material.
- **Klipper / Happy Hare / MMU setups** — spools registered on FilamentHub flow into Happy Hare via Moonraker, then back into OrcaSlicer through the existing `MoonrakerPrinterAgent` path.

End-to-end: scan a QR code on a spool → official preset lands in your profile → spool registers in Happy Hare with weight/color/type → OrcaSlicer syncs HH state. No manual entry.

---

## Key features

### Filament & preset catalog
- Brand → filament line → preset hierarchy with explicit `BundleSource` and moderation pipeline
- **Star rating (1–5)** per preset with success/fail flag and per-printer-model context
- **Weighted rating algorithm** (`rating × usage × success_rate`) for ranking community presets
- **Auto-generated "average" preset** that regenerates when ≥10 community presets accumulate for a material (uses weighted average — law of large numbers + Fermi estimation)
- **UI-based preset editor** — ~150 OrcaSlicer fields with labels and validation, no raw JSON editing required
- 350+ system printers + per-vendor profiles, imported from the OrcaSlicer system bundle with content-hash dedup

### Spool inventory
- Per-user physical spool tracking with state, weight remaining, usage history
- Spoolman-compatible REST API + WebSocket layer — drop-in for existing Klipper ecosystems

### Brand workflow
- Brand reps self-register, verify, and publish official presets for their products
- QR-code generation on packaging (format: `FH-XXX` or `FH-XXX-XXX`, base36) with auto-link to preset

### OrcaSlicer integration
- Embedded FilamentHub WebView panel inside the slicer
- Two-way preset sync (printer / filament / process)
- HH snapshot upload pipeline
- Lives in the [WeLizard/OrcaSlicer fork](https://github.com/WeLizard/OrcaSlicer); proposal to become an upstream third-party cloud provider is in progress

### Cost calculator (B2B)
- G-code parser for OrcaSlicer / BambuStudio / PrusaSlicer / SuperSlicer / Cura / CrealitySlicer
- Quote generator with PDF output for commercial printing services

---

## Architecture

| Layer | Stack |
|-------|-------|
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 15 · Redis 7 · Alembic |
| Frontend | React 19 · TypeScript · Vite · TailwindCSS 4 · TanStack Query · react-i18next |
| Slicer | OrcaSlicer fork (C++17, wxWidgets) — see [WeLizard/OrcaSlicer](https://github.com/WeLizard/OrcaSlicer) |
| Infra | Docker Compose · Nginx · SSL via acme-dns (DNS-01) |

Repository layout:

```
backend/    FastAPI app — 29 endpoints, 33 models, 61 Alembic migrations
frontend/   React app — 17 pages, 68 components
submodule/  OrcaSlicer integration (git submodule)
docs/       Internal docs and roadmap
scripts/    Deploy and local utilities
```

---

## Quick start (development)

Requires Docker Desktop.

```bash
git clone --recursive https://github.com/WeLizard/FilamentHub.git
cd FilamentHub
cp .env.template .env
docker compose -f docker-compose.dev.yml up -d
```

Then:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8001
- Swagger UI: http://localhost:8001/api/v1/docs

For non-Docker setup and production deployment, see [docs/current/DEPLOY.md](docs/current/DEPLOY.md).

---

## Contributing

Issues and PRs welcome. The project is in active development; some areas are intentionally scoped down for the first release (see [`docs/current/ROADMAP.md`](docs/current/ROADMAP.md)).

If you're a **filament brand representative** interested in publishing official presets — open an issue or contact the maintainer.

If you're working on **OrcaSlicer-side integration** (third-party cloud provider, Happy Hare, Moonraker workflows) — see the [OrcaSlicer fork](https://github.com/WeLizard/OrcaSlicer) and the integration discussion linked from there.

---

## License

[GNU Affero General Public License v3.0](LICENSE)

Self-hosting and modification are permitted under AGPL-3.0 terms. If you run a modified version as a network service, you must make your modifications available to users of that service.
