"""Pack OrcaSlicer printer/preset profiles into a catalog source bundle.

Source: submodule/OrcaSlicer/resources/profiles/
Target: backend/data/catalog_sources/orca/bundle.zip

Run from the project root before deploying when the OrcaSlicer submodule
is updated and we want fresh printer/preset definitions on prod.

OrcaSlicer is just one source of catalog data. Other sources (PrusaSlicer,
Cura, Bambu Studio) will live next to it as backend/data/catalog_sources/<name>/.

The resulting zip is committed to the main repo and shipped inside the
backend container; the admin imports it via the admin panel UI.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "submodule" / "OrcaSlicer" / "resources" / "profiles"
TARGET_DIR = PROJECT_ROOT / "backend" / "data" / "catalog_sources" / "orca"
TARGET_ZIP = TARGET_DIR / "bundle.zip"


def main() -> int:
    if not SOURCE_DIR.exists():
        print(f"ERROR: source not found: {SOURCE_DIR}")
        print("Make sure the OrcaSlicer submodule is initialised:")
        print("  git submodule update --init submodule/OrcaSlicer")
        return 1

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    json_files = sorted(SOURCE_DIR.rglob("*.json"))
    if not json_files:
        print(f"ERROR: no .json files under {SOURCE_DIR}")
        return 1

    print(f"Source: {SOURCE_DIR}")
    print(f"Target: {TARGET_ZIP}")
    print(f"Files:  {len(json_files)}")

    with zipfile.ZipFile(TARGET_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in json_files:
            zf.write(f, f.relative_to(SOURCE_DIR))

    size_mb = TARGET_ZIP.stat().st_size / 1024 / 1024
    print(f"Done.   {size_mb:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
