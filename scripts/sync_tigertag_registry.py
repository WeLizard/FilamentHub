"""Refresh the TigerTag id registry the backend ships with.

A TigerTag chip stores ids, not names: which material, brand, diameter, unit
and aspect an id means is published as reference tables in
https://github.com/TigerTag-Project/TigerTag-RFID-Guide (`database/*.json`,
CC0-1.0). The backend decodes tags offline, so it carries a reduced copy with
only the fields it reads.

Usage:
    python scripts/sync_tigertag_registry.py            # fetch the current tables
    python scripts/sync_tigertag_registry.py <folder>   # read already downloaded tables

Review the diff of backend/app/data/tigertag_registry.json before committing.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

SOURCE = "https://raw.githubusercontent.com/TigerTag-Project/TigerTag-RFID-Guide/main/database/"
TARGET = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "tigertag_registry.json"
TABLES = ("id_material", "id_brand", "id_diameter", "id_measure_unit", "id_aspect", "last_update")


def _table(name: str, folder: Path | None) -> Any:
    if folder is not None:
        return json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
    with urllib.request.urlopen(SOURCE + f"{name}.json", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def build(folder: Path | None) -> dict:
    tables = {
        name: _table(name, folder)
        for name in TABLES
        if folder is None or (folder / f"{name}.json").exists()
    }
    materials = {}
    for item in tables["id_material"]:
        density = item.get("density")
        materials[str(item["id"])] = {
            "label": item["label"],
            "material": item.get("material_type") or item["label"],
            "type": item.get("product_type_id"),
            **({"density": density} if isinstance(density, (int, float)) and density > 0 else {}),
        }
    return {
        "source": "TigerTag-Project/TigerTag-RFID-Guide database/*.json (CC0-1.0)",
        "last_update": tables.get("last_update"),
        "materials": materials,
        "brands": {str(item["id"]): item["name"] for item in tables["id_brand"]},
        "diameters": {str(item["id"]): float(item["label"]) for item in tables["id_diameter"]},
        "units": {str(item["id"]): item["label"] for item in tables["id_measure_unit"]},
        "aspects": {str(item["id"]): item["label"] for item in tables["id_aspect"]},
    }


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    registry = build(folder)
    TARGET.write_text(
        json.dumps(registry, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(
        f"{TARGET}: {len(registry['materials'])} materials, {len(registry['brands'])} brands, "
        f"{len(registry['aspects'])} aspects"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
