"""The reviewed Orca field registry follows the tracked schema baseline."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.orca_field_registry import ORCA_FIELD_REGISTRY_VERSION


def test_registry_version_matches_accepted_field_inventory() -> None:
    root = Path(__file__).resolve().parents[2]
    source_lock = json.loads(
        (
            root
            / "backend"
            / "data"
            / "catalog_sources"
            / "orca"
            / "source-lock.json"
        ).read_text(encoding="utf-8")
    )

    assert ORCA_FIELD_REGISTRY_VERSION == (
        f"field-inventory-sha256:{source_lock['field_inventory_sha256']}"
    )
