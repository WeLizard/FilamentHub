"""Fetch current OrcaSlicer profiles, build a catalog source bundle, and report
what it would change in the printer catalog.

The printer catalog mirrors whatever bundle was imported last, so new printer
models can only appear through a newer bundle. This command does the whole
errand in one step: pull the upstream profiles, build the archive, and say which
vendors and printer models the import would add, update or retire.

Nothing is overwritten without --write: by default the report is printed and the
built archive is left in a temporary directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER = PROJECT_ROOT / "scripts" / "build_catalog_source_orca.py"
DEFAULT_TARGET = (
    PROJECT_ROOT / "backend" / "data" / "catalog_sources" / "orca" / "bundle.zip"
)
FIELD_REGISTRY = (
    PROJECT_ROOT / "backend" / "app" / "services" / "orca_field_registry.py"
)
DEFAULT_REPOSITORY = "https://github.com/OrcaSlicer/OrcaSlicer"
MANIFEST_NAME = "filamenthub-source.json"
SOURCE_LOCK_NAME = "source-lock.json"
SOURCE_LOCK_FORMAT = "filamenthub.catalog-source-lock"
PROFILES_PATH = "resources/profiles"


class CommandFailed(RuntimeError):
    def __init__(self, command: list[str], returncode: int) -> None:
        super().__init__(f"command failed ({returncode}): {' '.join(command)}")
        self.returncode = returncode


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--source-lock",
        type=Path,
        default=None,
        help="Tracked metadata file; defaults to source-lock.json beside --output.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Replace --output with the freshly built archive.",
    )
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref", default="main")
    parser.add_argument(
        "--accept-field-delta",
        action="store_true",
        help="Passed through to the builder when new preset fields were reviewed.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Keep the checkout and the built archive for inspection.",
    )
    return parser.parse_args()


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise CommandFailed(command, result.returncode)


def _checkout_profiles(repository: str, ref: str, work_dir: Path) -> Path:
    """Clone only resources/profiles: the full repository is gigabytes of C++."""
    checkout = work_dir / "orca"
    _run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            "--branch",
            ref,
            repository,
            str(checkout),
        ]
    )
    _run(["git", "-C", str(checkout), "sparse-checkout", "set", PROFILES_PATH])
    profiles = checkout / PROFILES_PATH
    if not profiles.is_dir():
        raise SystemExit(f"{PROFILES_PATH} is missing from the checkout")
    return profiles


def _build(
    profiles: Path,
    target: Path,
    args: argparse.Namespace,
    source_lock: Path,
) -> None:
    command = [
        sys.executable,
        str(BUILDER),
        str(profiles),
        "--output",
        str(target),
        # The tracked lock is the accepted schema baseline and remains available
        # in a clean clone, unlike the deliberately unversioned bundle.zip.
        "--compare-with",
        str(source_lock),
        "--repository",
        args.repository,
        "--ref",
        args.ref,
    ]
    if args.accept_field_delta:
        command.append("--accept-field-delta")
    _run(command)


def _read_bundle(path: Path) -> tuple[dict, dict[str, set[str]], dict[str, str]]:
    """Return the manifest, printer models per vendor, and a digest per file."""
    models: dict[str, set[str]] = {}
    digests: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read(MANIFEST_NAME))
        for name in archive.namelist():
            if name == MANIFEST_NAME or name.endswith("/"):
                continue
            payload = archive.read(name)
            digests[name] = hashlib.sha256(payload).hexdigest()
            if "/" in name or not name.endswith(".json"):
                continue
            try:
                vendor = json.loads(payload)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(vendor, dict) or not vendor.get("name"):
                continue
            entries = vendor.get("machine_model_list") or []
            models[str(vendor["name"])] = {
                str(entry["name"])
                for entry in entries
                if isinstance(entry, dict) and entry.get("name")
            }
    return manifest, models, digests


def _normalise_field_inventory(value: Any) -> dict[str, dict[str, list[str]]]:
    if not isinstance(value, dict):
        raise ValueError("bundle manifest is missing preset_field_inventory")
    try:
        return {
            scope: {
                str(field_name): sorted({str(shape) for shape in shapes})
                for field_name, shapes in sorted((value.get(scope) or {}).items())
            }
            for scope in ("filament", "process", "machine")
        }
    except (AttributeError, TypeError) as exc:
        raise ValueError("bundle manifest has invalid preset_field_inventory") from exc


def _field_inventory_sha256(
    inventory: dict[str, dict[str, list[str]]],
) -> str:
    payload = json.dumps(
        inventory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _source_lock_from_bundle(bundle: Path) -> dict[str, object]:
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read(MANIFEST_NAME))
    required = (
        "source",
        "repository",
        "ref",
        "commit",
        "commit_date",
        "profiles_tree",
        "content_sha256",
        "file_count",
        "vendor_count",
        "version",
    )
    missing = [field for field in required if field not in manifest]
    if missing:
        raise ValueError(f"bundle manifest is missing: {', '.join(missing)}")
    inventory = _normalise_field_inventory(manifest.get("preset_field_inventory"))
    return {
        "format": SOURCE_LOCK_FORMAT,
        "source": manifest["source"],
        "repository": manifest["repository"],
        "ref": manifest["ref"],
        "commit": manifest["commit"],
        "commit_date": manifest["commit_date"],
        "profiles_tree": manifest["profiles_tree"],
        "content_sha256": manifest["content_sha256"],
        "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "file_count": manifest["file_count"],
        "vendor_count": manifest["vendor_count"],
        "bundle_manifest_version": manifest["version"],
        "preset_field_inventory": inventory,
        "field_inventory_sha256": _field_inventory_sha256(inventory),
    }


def _write_source_lock(bundle: Path, target: Path) -> None:
    payload = _source_lock_from_bundle(bundle)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def _group(name: str) -> tuple[str, str]:
    """Split an archive path into the vendor and the part of its profile set."""
    parts = name.split("/")
    if len(parts) == 1:
        return parts[0].removesuffix(".json"), "vendor manifest"
    scope = parts[1] if len(parts) > 2 else "other"
    return parts[0], scope


def _print_profile_changes(current: dict[str, str], fresh: dict[str, str]) -> None:
    """Report edited profile contents: nozzle, bed, speeds and material settings
    live here, and they matter even when the model list is untouched."""
    added = sorted(set(fresh) - set(current))
    removed = sorted(set(current) - set(fresh))
    modified = sorted(
        name for name in set(fresh) & set(current) if fresh[name] != current[name]
    )
    if not (added or removed or modified):
        return

    buckets: dict[tuple[str, str], dict[str, list[str]]] = {}
    for kind, names in (("added", added), ("modified", modified), ("removed", removed)):
        for name in names:
            entry = buckets.setdefault(_group(name), {})
            entry.setdefault(kind, []).append(Path(name).stem)

    total = len(added) + len(modified) + len(removed)
    print(f"profile files changed ({total}):")
    for (vendor, scope), kinds in sorted(buckets.items()):
        summary = ", ".join(
            f"{len(items)} {kind}" for kind, items in sorted(kinds.items())
        )
        print(f"  {vendor} · {scope}: {summary}")
        for kind, items in sorted(kinds.items()):
            shown = ", ".join(items[:6])
            if len(items) > 6:
                shown += f", +{len(items) - 6} more"
            print(f"      {kind}: {shown}")


def _check_registry_alignment(
    source_lock: dict[str, object], *, required: bool
) -> bool:
    """Keep schema review tied to field shape, not unrelated profile bytes."""
    try:
        registry = FIELD_REGISTRY.read_text(encoding="utf-8")
    except OSError as exc:
        if required:
            raise ValueError(f"cannot read Orca field registry: {exc}") from exc
        return False
    pinned = re.search(r'"field-inventory-sha256:([0-9a-f]{64})"', registry)
    if not pinned:
        message = "Orca field registry has no field-inventory-sha256 version"
        if required:
            raise ValueError(message)
        print(f"\nВНИМАНИЕ: {message}.")
        return False
    digest = str(source_lock["field_inventory_sha256"])
    if digest == pinned.group(1):
        return True
    print()
    print("ВНИМАНИЕ: реестр полей OrcaSlicer отстал от этого источника.")
    print(f"  реестр   : field-inventory-sha256:{pinned.group(1)}")
    print(f"  источник: field-inventory-sha256:{digest}")
    print("Сначала разберите изменившиеся поля по редакторам и passthrough-контракту,")
    print("затем обновите registry version. Одна подмена контрольной суммы не является ревью.")
    if required:
        raise ValueError("Orca field registry is not aligned with the accepted source")
    return False


def _bundle_matches_source_lock(bundle: Path, source_lock: Path) -> bool:
    if not bundle.is_file() or not source_lock.is_file():
        return False
    try:
        lock = json.loads(source_lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    expected = lock.get("bundle_sha256") if isinstance(lock, dict) else None
    return (
        isinstance(expected, str)
        and hashlib.sha256(bundle.read_bytes()).hexdigest() == expected
    )


def _report(current: Path | None, fresh: Path) -> bool:
    """Print what an import of the fresh bundle would change. True when it differs."""
    fresh_manifest, fresh_models, fresh_files = _read_bundle(fresh)
    print(
        f"upstream commit : {fresh_manifest['commit']} ({fresh_manifest['commit_date']})"
    )

    if current is None or not current.exists():
        total = sum(len(names) for names in fresh_models.values())
        print(
            f"no current bundle at {current}; the archive brings "
            f"{len(fresh_models)} vendors and {total} printer models"
        )
        return True

    current_manifest, current_models, current_files = _read_bundle(current)
    print(
        f"current commit  : {current_manifest['commit']} ({current_manifest['commit_date']})"
    )

    if current_manifest["profiles_tree"] == fresh_manifest["profiles_tree"]:
        print("\nProfiles are identical — nothing to import.")
        return False

    new_vendors = sorted(set(fresh_models) - set(current_models))
    gone_vendors = sorted(set(current_models) - set(fresh_models))
    added: list[str] = []
    retired: list[str] = []
    for vendor in sorted(set(fresh_models) | set(current_models)):
        before = current_models.get(vendor, set())
        after = fresh_models.get(vendor, set())
        added.extend(f"{vendor} · {name}" for name in sorted(after - before))
        retired.extend(f"{vendor} · {name}" for name in sorted(before - after))

    print()
    if new_vendors:
        print(f"new vendors ({len(new_vendors)}): {', '.join(new_vendors)}")
    if gone_vendors:
        print(f"vendors gone ({len(gone_vendors)}): {', '.join(gone_vendors)}")
    if added:
        print(f"printer models added ({len(added)}):")
        for item in added:
            print(f"  + {item}")
    if retired:
        print(f"printer models retired ({len(retired)}):")
        for item in retired:
            print(f"  - {item}")
    if not (new_vendors or gone_vendors or added or retired):
        print("printer models: no change")

    print()
    _print_profile_changes(current_files, fresh_files)
    return True


def main() -> int:
    args = _parse_args()
    source_lock = (args.source_lock or args.output.with_name(SOURCE_LOCK_NAME)).resolve()
    work_dir = Path(tempfile.mkdtemp(prefix="orca-catalog-"))
    keep = args.keep_work_dir
    try:
        try:
            profiles = _checkout_profiles(args.repository, args.ref, work_dir)
            fresh = work_dir / "bundle.zip"
            _build(profiles, fresh, args, source_lock)
        except CommandFailed as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return exc.returncode

        fresh_lock = _source_lock_from_bundle(fresh)
        try:
            _check_registry_alignment(fresh_lock, required=args.write)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            keep = True
            return 2

        print()
        current = args.output if _bundle_matches_source_lock(args.output, source_lock) else None
        if args.output.exists() and current is None:
            print(
                "WARNING: local bundle.zip does not match the tracked source lock; "
                "it is not used as the accepted comparison baseline."
            )
        differs = _report(current, fresh)

        if args.write:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary_bundle = args.output.with_name(f".{args.output.name}.tmp")
            shutil.copy2(fresh, temporary_bundle)
            temporary_bundle.replace(args.output)
            print(f"\nWritten to {args.output}")
            _write_source_lock(args.output, source_lock)
            print(f"Source lock written to {source_lock}")
        elif differs:
            keep = True
            print(f"\nArchive kept at {fresh}")
            print(
                "Re-run with --write to replace the local bundle and its tracked source lock."
            )
        return 0
    finally:
        if keep:
            print(f"Work directory: {work_dir}")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
