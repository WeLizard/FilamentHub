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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER = PROJECT_ROOT / "scripts" / "build_catalog_source_orca.py"
DEFAULT_TARGET = PROJECT_ROOT / "backend" / "data" / "catalog_sources" / "orca" / "bundle.zip"
FIELD_REGISTRY = PROJECT_ROOT / "backend" / "app" / "services" / "orca_field_registry.py"
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
        # The build goes to a temporary file, so without this the builder has no
        # previous bundle to compare against and its field-lifecycle check never
        # fires — the one guard that notices Orca adding or dropping a setting.
        "--compare-with",
        str(args.output),
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
        summary = ", ".join(f"{len(items)} {kind}" for kind, items in sorted(kinds.items()))
        print(f"  {vendor} · {scope}: {summary}")
        for kind, items in sorted(kinds.items()):
            shown = ", ".join(items[:6])
            if len(items) > 6:
                shown += f", +{len(items) - 6} more"
            print(f"      {kind}: {shown}")


def _warn_if_registry_trails(bundle: Path) -> None:
    """The Orca field registry is pinned to a bundle checksum.

    Since the archive stopped being versioned, a mismatch shows up nowhere in
    git — the only other signal is a failing test, found long after the fact.
    """
    try:
        registry = FIELD_REGISTRY.read_text(encoding="utf-8")
    except OSError:
        return
    pinned = re.search(r'"bundle-sha256:([0-9a-f]{64})"', registry)
    if not pinned:
        return
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    if digest == pinned.group(1):
        return
    print()
    print("ВНИМАНИЕ: реестр полей OrcaSlicer отстал от этого архива.")
    print(f"  реестр : bundle-sha256:{pinned.group(1)}")
    print(f"  архив  : bundle-sha256:{digest}")
    print("Пока реестр не обновлён, тест test_registry_version_matches_bundled_orca_catalog")
    print("падает, а разбор новых полей Orca не сделан. Обновлять реестр вручную,")
    print("разложив новые поля по редакторам, а не подменой контрольной суммы.")


def _report(current: Path | None, fresh: Path) -> bool:
    """Print what an import of the fresh bundle would change. True when it differs."""
    fresh_manifest, fresh_models, fresh_files = _read_bundle(fresh)
    print(f"upstream commit : {fresh_manifest['commit']} ({fresh_manifest['commit_date']})")

    if current is None or not current.exists():
        total = sum(len(names) for names in fresh_models.values())
        print(f"no current bundle at {current}; the archive brings "
              f"{len(fresh_models)} vendors and {total} printer models")
        return True

    current_manifest, current_models, current_files = _read_bundle(current)
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
        print("printer models: no change")

    print()
    _print_profile_changes(current_files, fresh_files)
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
            _warn_if_registry_trails(args.output)
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
