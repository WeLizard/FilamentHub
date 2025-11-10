"""Export OrcaSlicer bundled printer/process presets into a portable directory.

Usage:
    python scripts/export_orca_presets.py

Result:
    Creates/refreshes `docs/orca_bundles/system_presets/` with JSON files
    grouped by vendor (`<vendor>/machine/*.json`, `<vendor>/process/*.json`).

Only JSON files are copied (images/STL are skipped) to minimise repository size.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "docs" / "OrcaSlicer" / "resources" / "profiles"
DST_DIR = ROOT / "docs" / "orca_bundles" / "system_presets"

EXTRA_VENDOR_DIRS = {"OrcaFilamentLibrary"}  # skip filament library


def copy_json_tree(src: Path, dst: Path) -> None:
    """Copy only JSON files from src tree into dst."""
    if not src.exists():
        return

    for json_path in src.rglob("*.json"):
        rel = json_path.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(json_path, target)


def main() -> None:
    if not SRC_DIR.exists():
        raise SystemExit(f"Source directory not found: {SRC_DIR}")

    if DST_DIR.exists():
        shutil.rmtree(DST_DIR)
    DST_DIR.mkdir(parents=True, exist_ok=True)

    # Copy aggregated vendor JSON descriptors (Afinia.json, etc.)
    for vendor_file in SRC_DIR.glob("*.json"):
        if vendor_file.stem in EXTRA_VENDOR_DIRS or vendor_file.name == "blacklist.json":
            continue
        shutil.copy2(vendor_file, DST_DIR / vendor_file.name)

    # Copy per-vendor machine/process JSON files
    for folder in SRC_DIR.iterdir():
        if not folder.is_dir():
            continue
        if folder.name in EXTRA_VENDOR_DIRS:
            continue

        machine_dir = folder / "machine"
        process_dir = folder / "process"

        # Each vendor gets its own directory even if some subfolders are missing.
        dst_vendor_dir = DST_DIR / folder.name
        dst_vendor_dir.mkdir(parents=True, exist_ok=True)

        copy_json_tree(machine_dir, dst_vendor_dir / "machine")
        copy_json_tree(process_dir, dst_vendor_dir / "process")


if __name__ == "__main__":
    main()

