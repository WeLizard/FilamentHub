"""Lifecycle checks for the official Orca catalog-source builder."""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "build_catalog_source_orca.py"
)
SPEC = importlib.util.spec_from_file_location("build_catalog_source_orca", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_field_inventory_tracks_scopes_and_serialized_shapes(tmp_path: Path) -> None:
    source = tmp_path / "profiles"
    filament = source / "Vendor" / "filament" / "PLA.json"
    process = source / "Vendor" / "process" / "Quality.json"
    machine = source / "Vendor" / "machine" / "Printer.json"
    for path in (filament, process, machine):
        path.parent.mkdir(parents=True, exist_ok=True)
    filament.write_text(
        json.dumps({"vector": ["1"], "nullable": None}), encoding="utf-8"
    )
    process.write_text(json.dumps({"flag": True}), encoding="utf-8")
    machine.write_text(
        json.dumps({"object": {"mode": "safe"}}), encoding="utf-8"
    )

    files = sorted(source.rglob("*.json"))
    inventory = builder._field_inventory_from_files(source, files)

    assert inventory == {
        "filament": {"nullable": ["null"], "vector": ["array:string"]},
        "process": {"flag": ["boolean"]},
        "machine": {"object": ["object"]},
    }


def test_v1_bundle_inventory_is_derived_before_lifecycle_comparison(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(
            builder.MANIFEST_NAME,
            json.dumps({"format": builder.MANIFEST_FORMAT, "version": 1}),
        )
        archive.writestr(
            "Vendor/filament/PLA.json",
            json.dumps({"legacy_field": ["kept"]}),
        )

    previous = builder._field_inventory_from_bundle(bundle)
    current = {
        "filament": {"new_field": ["number"]},
        "process": {},
        "machine": {},
    }

    assert builder._field_delta(previous, current) == {
        "filament": {
            "added": ["new_field"],
            "removed": ["legacy_field"],
            "shape_changed": {},
        }
    }


def test_shape_changes_are_reported_without_treating_fields_as_invalid() -> None:
    previous = {
        "filament": {"flexible_field": ["array:string"]},
        "process": {},
        "machine": {},
    }
    current = {
        "filament": {"flexible_field": ["number"]},
        "process": {},
        "machine": {},
    }

    assert builder._field_delta(previous, current)["filament"]["shape_changed"] == {
        "flexible_field": {
            "before": ["array:string"],
            "after": ["number"],
        }
    }
