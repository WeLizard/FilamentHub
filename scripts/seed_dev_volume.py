#!/usr/bin/env python3
"""Fill the development database with enough invented rows to be worth measuring.

A load rehearsal on fifty rows proves nothing about indexes: any scan over a
short table is instant. This makes the tables long enough for a missing index
to show up, using invented data rather than a copy of production — real people's
addresses have no business on a workstation.

Development only. The script refuses any database but a local one.

The development stack publishes its database on another port, so point the
connection at it:

    POSTGRES_PORT=5433 POSTGRES_DB=filamenthub_dev POSTGRES_PASSWORD=devpass123         python scripts/seed_dev_volume.py --filaments 5000 --presets-per-filament 6
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from pathlib import Path

# Settings read the backend's own .env; the repository root has a different one.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")

LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres-dev"}
MATERIALS = ["PLA", "PETG", "ABS", "ASA", "TPU", "PA", "PC", "PLA-CF", "PETG-CF"]
COLOURS = ["Red", "Black", "White", "Blue", "Green", "Grey", "Orange", "Purple", "Yellow"]


async def seed(filaments: int, presets_per_filament: int, brands: int) -> int:
    from app.core.config import settings
    from app.db.session import AsyncSessionLocal
    from app.models.brand import Brand
    from app.models.filament import Filament
    from app.models.preset import Preset, PresetModerationStatus

    if settings.POSTGRES_HOST.casefold() not in LOCAL_DB_HOSTS:
        print(
            f"Отказ: база на {settings.POSTGRES_HOST} — не локальная.\n"
            "Скрипт пишет тысячи строк; боевой базе это ни к чему.",
            file=sys.stderr,
        )
        return 2

    async with AsyncSessionLocal() as db:
        made_brands = []
        for index in range(brands):
            brand = Brand(
                name=f"SeedBrand {index:04d}",
                slug=f"seed-brand-{index:04d}",
                verified=index % 3 == 0,
            )
            db.add(brand)
            made_brands.append(brand)
        await db.flush()
        print(f"брендов: {len(made_brands)}")

        created_presets = 0
        for index in range(filaments):
            brand = random.choice(made_brands)
            material = random.choice(MATERIALS)
            colour = random.choice(COLOURS)
            filament = Filament(
                brand_id=brand.id,
                name=f"{material} {colour} {index:05d}",
                slug=f"seed-{index:05d}-{material.lower()}-{colour.lower()}",
                material_type=material,
                diameter=1.75,
                density=round(random.uniform(1.0, 1.4), 2),
                color_name=colour,
                active=True,
            )
            db.add(filament)
            await db.flush()

            base_temp = {"PLA": 210, "PETG": 235, "ABS": 245, "ASA": 250, "TPU": 225}.get(
                material, 240
            )
            for _ in range(presets_per_filament):
                db.add(
                    Preset(
                        name=f"{filament.name} profile",
                        filament_id=filament.id,
                        user_id=None,
                        extruder_temp=base_temp + random.randint(-8, 8),
                        bed_temp=random.choice([55, 60, 70, 80, 100]),
                        flow_rate=random.choice([95, 98, 100, 102]),
                        active=True,
                        is_weighted=False,
                        moderation_status=PresetModerationStatus.APPROVED,
                    )
                )
                created_presets += 1

            if index % 250 == 0 and index:
                await db.commit()
                print(f"филаментов: {index}, пресетов: {created_presets}")

        await db.commit()
        print(f"готово: филаментов {filaments}, пресетов {created_presets}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filaments", type=int, default=5000)
    parser.add_argument("--presets-per-filament", type=int, default=6)
    parser.add_argument("--brands", type=int, default=40)
    args = parser.parse_args()
    return asyncio.run(seed(args.filaments, args.presets_per_filament, args.brands))


if __name__ == "__main__":
    raise SystemExit(main())
