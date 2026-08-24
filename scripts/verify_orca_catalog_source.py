"""Verify an accepted Orca catalog bundle against its tracked source lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = (
    PROJECT_ROOT / "backend" / "data" / "catalog_sources" / "orca" / "bundle.zip"
)
DEFAULT_SOURCE_LOCK = DEFAULT_BUNDLE.with_name("source-lock.json")
MANIFEST_NAME = "filamenthub-source.json"
MANIFEST_FORMAT = "filamenthub.catalog-source"
SOURCE_LOCK_FORMAT = "filamenthub.catalog-source-lock"
PRESET_SCOPES = ("filament", "process", "machine")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--source-lock", type=Path, default=DEFAULT_SOURCE_LOCK)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def _normalise_inventory(value: Any) -> dict[str, dict[str, list[str]]]:
    if not isinstance(value, dict):
        raise ValueError("preset_field_inventory is missing")
    try:
        return {
            scope: {
                str(field_name): sorted({str(shape) for shape in shapes})
                for field_name, shapes in sorted((value.get(scope) or {}).items())
            }
            for scope in PRESET_SCOPES
        }
    except (AttributeError, TypeError) as exc:
        raise ValueError("preset_field_inventory is invalid") from exc


def _inventory_sha256(inventory: dict[str, dict[str, list[str]]]) -> str:
    payload = json.dumps(
        inventory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _content_sha256(archive: zipfile.ZipFile, names: list[str]) -> str:
    digest = hashlib.sha256()
    for name in names:
        encoded_name = name.encode("utf-8")
        payload = archive.read(name)
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def verify(bundle: Path, source_lock: Path) -> dict[str, Any]:
    if not bundle.is_file():
        raise ValueError(f"bundle not found: {bundle}")
    if not source_lock.is_file():
        raise ValueError(f"source lock not found: {source_lock}")

    lock = json.loads(source_lock.read_text(encoding="utf-8"))
    if not isinstance(lock, dict) or lock.get("format") != SOURCE_LOCK_FORMAT:
        raise ValueError("invalid Orca catalog source lock format")

    bundle_sha256 = hashlib.sha256(bundle.read_bytes()).hexdigest()
    if bundle_sha256 != lock.get("bundle_sha256"):
        raise ValueError("bundle SHA-256 does not match source lock")

    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        if MANIFEST_NAME not in names:
            raise ValueError(f"bundle is missing {MANIFEST_NAME}")
        payload_names = sorted(
            name for name in names if name != MANIFEST_NAME and not name.endswith("/")
        )
        if any(not name.endswith(".json") for name in payload_names):
            raise ValueError("bundle contains an unexpected non-JSON payload")
        manifest = json.loads(archive.read(MANIFEST_NAME))
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != MANIFEST_FORMAT
            or manifest.get("source") != "orca"
            or manifest.get("dirty") is True
        ):
            raise ValueError("invalid Orca catalog source manifest")

        content_sha256 = _content_sha256(archive, payload_names)
        if content_sha256 != manifest.get("content_sha256"):
            raise ValueError("bundle content SHA-256 does not match its manifest")

        vendor_count = 0
        for name in payload_names:
            if "/" in name:
                continue
            value = json.loads(archive.read(name))
            if isinstance(value, dict) and value.get("name") and value.get("version"):
                vendor_count += 1

    comparable_fields = (
        "source",
        "repository",
        "ref",
        "commit",
        "commit_date",
        "profiles_tree",
        "content_sha256",
        "file_count",
        "vendor_count",
    )
    for field in comparable_fields:
        if lock.get(field) != manifest.get(field):
            raise ValueError(f"source lock does not match bundle manifest field: {field}")
    if manifest.get("file_count") != len(payload_names):
        raise ValueError("bundle file_count does not match archive contents")
    if manifest.get("vendor_count") != vendor_count:
        raise ValueError("bundle vendor_count does not match archive contents")

    manifest_inventory = _normalise_inventory(manifest.get("preset_field_inventory"))
    lock_inventory = _normalise_inventory(lock.get("preset_field_inventory"))
    if manifest_inventory != lock_inventory:
        raise ValueError("source lock field inventory does not match bundle manifest")
    inventory_sha256 = _inventory_sha256(manifest_inventory)
    if inventory_sha256 != lock.get("field_inventory_sha256"):
        raise ValueError("field inventory SHA-256 does not match source lock")

    return {
        "valid": True,
        "commit": manifest["commit"],
        "profiles_tree": manifest["profiles_tree"],
        "bundle_sha256": bundle_sha256,
        "content_sha256": content_sha256,
        "field_inventory_sha256": inventory_sha256,
        "file_count": len(payload_names),
        "vendor_count": vendor_count,
    }


def main() -> int:
    args = _parse_args()
    try:
        result = verify(args.bundle.resolve(), args.source_lock.resolve())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        if args.as_json:
            print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "Orca catalog source verified: "
            f"commit={result['commit']} bundle_sha256={result['bundle_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
