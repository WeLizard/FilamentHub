"""Import OrcaSlicer system presets into the database."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.orca_bundle_importer import run_import  # noqa: E402


async def main() -> None:
    summary = await run_import()
    logging.info("Import finished: %s", summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(main())

