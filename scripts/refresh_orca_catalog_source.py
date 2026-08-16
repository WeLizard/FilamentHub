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
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER = PROJECT_ROOT / "scripts" / "build_catalog_source_orca.py"
DEFAULT_TARGET = PROJECT_ROOT / "backend" / "data" / "catalog_sources" / "orca" / "bundle.zip"
DEFAULT_REPOSITORY = "https://github.com/OrcaSlicer/OrcaSlicer"
MANIFEST_NAME = "filamenthub-source.json"
PROFILES_PATH = "resources/profiles"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_TARGET)
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
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(command)}")


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


def _build(profiles: Path, target: Path, args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(BUILDER),
        str(profiles),
        "--output",
        str(target),
        "--repository",
        args.repository,
        "--ref",
        args.ref,
    ]
    if args.accept_field_delta:
        command.append("--accept-field-delta")
    _run(command)


def _read_bundle(path: Path) -> tuple[dict, dict[str, set[str]]]:
    """Return the manifest and every printer model, grouped by vendor."""
    models: dict[str, set[str]] = {}
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read(MANIFEST_NAME))
        for name in archive.namelist():
            if "/" in name or not name.endswith(".json") or name == MANIFEST_NAME:
                continue
            try:
                vendor = json.loads(archive.read(name))
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
    return manifest, models


def _report(current: Path | None, fresh: Path) -> bool:
    """Print what an import of the fresh bundle would change. True when it differs."""
    fresh_manifest, fresh_models = _read_bundle(fresh)
    print(f"upstream commit : {fresh_manifest['commit']} ({fresh_manifest['commit_date']})")

    if current is None or not current.exists():
        total = sum(len(names) for names in fresh_models.values())
        print(f"no current bundle at {current}; the archive brings "
              f"{len(fresh_models)} vendors and {total} printer models")
        return True

    current_manifest, current_models = _read_bundle(current)
    print(f"current commit  : {current_manifest['commit']} ({current_manifest['commit_date']})")

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
        print("No printer models change; upstream touched profile contents only.")
        print("Importing would refresh presets and machine data, not the model list.")
    return True


def main() -> int:
    args = _parse_args()
    work_dir = Path(tempfile.mkdtemp(prefix="orca-catalog-"))
    keep = args.keep_work_dir
    try:
        profiles = _checkout_profiles(args.repository, args.ref, work_dir)
        fresh = work_dir / "bundle.zip"
        _build(profiles, fresh, args)

        print()
        differs = _report(args.output, fresh)

        if args.write:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fresh, args.output)
            print(f"\nWritten to {args.output}")
        elif differs:
            keep = True
            print(f"\nArchive kept at {fresh}")
            print("Re-run with --write to replace the tracked bundle.")
        return 0
    finally:
        if keep:
            print(f"Work directory: {work_dir}")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
