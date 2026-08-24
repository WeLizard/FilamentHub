"""Build the canonical OrcaSlicer catalog-source archive.

The input is an official ``resources/profiles`` checkout. The archive carries
source provenance so CI and the admin UI can tell exactly which upstream commit
is installed. It is deterministic for one source tree and commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = PROJECT_ROOT / "backend" / "data" / "catalog_sources" / "orca" / "bundle.zip"
MANIFEST_NAME = "filamenthub-source.json"
MANIFEST_FORMAT = "filamenthub.catalog-source"
SOURCE_LOCK_FORMAT = "filamenthub.catalog-source-lock"
DEFAULT_REPOSITORY = "https://github.com/OrcaSlicer/OrcaSlicer"
PRESET_SCOPES = ("filament", "process", "machine")


def _git(source_dir: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(source_dir), *args],
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _source_digest(source_dir: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(source_dir).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _vendor_count(source_dir: Path, files: list[Path]) -> int:
    count = 0
    for path in files:
        if path.parent != source_dir:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("name") and value.get("version"):
            count += 1
    return count


def _preset_scope(path: Path | PurePosixPath) -> str | None:
    parts = {part.lower() for part in path.parts}
    return next((scope for scope in PRESET_SCOPES if scope in parts), None)


def _json_shape(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        if not value:
            return "array:empty"
        return "array:" + "|".join(sorted({_json_shape(item) for item in value}))
    if isinstance(value, dict):
        return "object"
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def _add_inventory_document(
    inventory: dict[str, dict[str, set[str]]],
    *,
    relative_path: Path | PurePosixPath,
    document: Any,
) -> None:
    scope = _preset_scope(relative_path)
    if scope is None or not isinstance(document, dict):
        return
    for field_name, value in document.items():
        inventory[scope].setdefault(str(field_name), set()).add(_json_shape(value))


def _finalize_inventory(
    inventory: dict[str, dict[str, set[str]]],
) -> dict[str, dict[str, list[str]]]:
    return {
        scope: {
            field_name: sorted(shapes)
            for field_name, shapes in sorted(inventory[scope].items())
        }
        for scope in PRESET_SCOPES
    }


def _field_inventory_from_files(
    source_dir: Path, files: list[Path]
) -> dict[str, dict[str, list[str]]]:
    inventory: dict[str, dict[str, set[str]]] = {
        scope: {} for scope in PRESET_SCOPES
    }
    for path in files:
        relative = path.relative_to(source_dir)
        if _preset_scope(relative) is None:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid Orca JSON {relative.as_posix()}: {exc}") from exc
        _add_inventory_document(
            inventory,
            relative_path=relative,
            document=document,
        )
    return _finalize_inventory(inventory)


def _field_inventory_from_bundle(bundle: Path) -> dict[str, dict[str, list[str]]]:
    inventory: dict[str, dict[str, set[str]]] = {
        scope: {} for scope in PRESET_SCOPES
    }
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read(MANIFEST_NAME))
        recorded = manifest.get("preset_field_inventory")
        if isinstance(recorded, dict):
            return {
                scope: {
                    str(field_name): sorted({str(shape) for shape in shapes})
                    for field_name, shapes in sorted((recorded.get(scope) or {}).items())
                }
                for scope in PRESET_SCOPES
            }
        for name in archive.namelist():
            relative = PurePosixPath(name)
            if relative.suffix.lower() != ".json" or _preset_scope(relative) is None:
                continue
            try:
                document = json.loads(archive.read(name))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid Orca JSON {name} in previous bundle: {exc}") from exc
            _add_inventory_document(
                inventory,
                relative_path=relative,
                document=document,
            )
    return _finalize_inventory(inventory)


def _field_inventory_from_source_lock(
    source_lock: Path,
) -> dict[str, dict[str, list[str]]]:
    value = json.loads(source_lock.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format") != SOURCE_LOCK_FORMAT:
        raise ValueError("invalid Orca catalog source lock format")
    recorded = value.get("preset_field_inventory")
    if not isinstance(recorded, dict):
        raise ValueError("source lock has no preset_field_inventory baseline")
    try:
        return {
            scope: {
                str(field_name): sorted({str(shape) for shape in shapes})
                for field_name, shapes in sorted((recorded.get(scope) or {}).items())
            }
            for scope in PRESET_SCOPES
        }
    except (AttributeError, TypeError) as exc:
        raise ValueError("invalid preset_field_inventory in source lock") from exc


def _field_inventory_from_reference(
    reference: Path,
) -> dict[str, dict[str, list[str]]]:
    if zipfile.is_zipfile(reference):
        return _field_inventory_from_bundle(reference)
    return _field_inventory_from_source_lock(reference)


def _field_delta(
    previous: dict[str, dict[str, list[str]]],
    current: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, Any]]:
    delta: dict[str, dict[str, Any]] = {}
    for scope in PRESET_SCOPES:
        old_fields = previous.get(scope, {})
        new_fields = current.get(scope, {})
        added = sorted(set(new_fields) - set(old_fields))
        removed = sorted(set(old_fields) - set(new_fields))
        shape_changed = {
            field_name: {
                "before": old_fields[field_name],
                "after": new_fields[field_name],
            }
            for field_name in sorted(set(old_fields) & set(new_fields))
            if old_fields[field_name] != new_fields[field_name]
        }
        if added or removed or shape_changed:
            delta[scope] = {
                "added": added,
                "removed": removed,
                "shape_changed": shape_changed,
            }
    return delta


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Official OrcaSlicer resources/profiles directory")
    parser.add_argument("--output", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--compare-with",
        type=Path,
        default=None,
        help=(
            "Accepted bundle or source-lock.json to compare preset fields against. "
            "Defaults to --output. Production refreshes pass the tracked source lock "
            "so the lifecycle gate also works in a clean clone without bundle.zip."
        ),
    )
    parser.add_argument("--repository", default=None)
    parser.add_argument("--ref", default=None, help="Tracked upstream ref, normally main")
    parser.add_argument("--commit", default=None)
    parser.add_argument("--commit-date", default=None)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--accept-field-delta",
        action="store_true",
        help="Acknowledge reviewed added/removed/shape-changed preset fields.",
    )
    return parser.parse_args()


def _manifest(
    args: argparse.Namespace,
    source_dir: Path,
    files: list[Path],
    field_inventory: dict[str, dict[str, list[str]]],
) -> dict[str, Any]:
    repository = args.repository or _git(source_dir, "config", "--get", "remote.origin.url")
    repository = repository or DEFAULT_REPOSITORY
    commit = args.commit or _git(source_dir, "rev-parse", "HEAD")
    if not commit:
        raise ValueError("cannot determine source commit; pass --commit")

    dirty_output = _git(source_dir, "status", "--porcelain", "--", str(source_dir))
    dirty = bool(dirty_output)
    if dirty and not args.allow_dirty:
        raise ValueError("resources/profiles contains uncommitted changes; use --allow-dirty explicitly")

    commit_date = args.commit_date or _git(source_dir, "show", "-s", "--format=%cI", commit)
    if not commit_date:
        commit_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    git_root_raw = _git(source_dir, "rev-parse", "--show-toplevel")
    profiles_tree = None
    if git_root_raw:
        try:
            relative = source_dir.relative_to(Path(git_root_raw)).as_posix()
        except ValueError:
            relative = "resources/profiles"
        profiles_tree = _git(source_dir, "rev-parse", f"{commit}:{relative}")
        is_shallow = _git(source_dir, "rev-parse", "--is-shallow-repository") == "true"
        profiles_commit = None if is_shallow else _git(
            source_dir, "log", "-1", "--format=%H", "--", relative
        )
    else:
        profiles_commit = None

    ref = args.ref or _git(source_dir, "branch", "--show-current") or "main"
    manifest = {
        "format": MANIFEST_FORMAT,
        "version": 2,
        "source": "orca",
        "repository": repository,
        "ref": ref,
        "commit": commit,
        "commit_date": commit_date,
        "profiles_tree": profiles_tree,
        "dirty": dirty,
        "file_count": len(files),
        "vendor_count": _vendor_count(source_dir, files),
        "content_sha256": _source_digest(source_dir, files),
        "preset_field_inventory": field_inventory,
    }
    if profiles_commit:
        manifest["profiles_commit"] = profiles_commit
    return manifest


def main() -> int:
    args = _parse_args()
    source_dir = args.source.resolve()
    output = args.output.resolve()
    if not source_dir.is_dir():
        print(f"ERROR: source directory not found: {source_dir}", file=sys.stderr)
        return 1

    files = sorted(source_dir.rglob("*.json"), key=lambda path: path.relative_to(source_dir).as_posix())
    if not files:
        print(f"ERROR: no .json files under {source_dir}", file=sys.stderr)
        return 1

    try:
        field_inventory = _field_inventory_from_files(source_dir, files)
        manifest = _manifest(args, source_dir, files, field_inventory)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if manifest["vendor_count"] == 0:
        print("ERROR: no Orca vendor manifests found at source root", file=sys.stderr)
        return 1

    baseline = (args.compare_with or output).resolve()
    if baseline.is_file():
        try:
            previous_inventory = _field_inventory_from_reference(baseline)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            print(f"ERROR: cannot read previous field inventory: {exc}", file=sys.stderr)
            return 1
        field_delta = _field_delta(previous_inventory, field_inventory)
        if field_delta and not args.accept_field_delta:
            print(
                "ERROR: Orca preset field lifecycle changed; review the JSON below "
                "and rerun with --accept-field-delta.",
                file=sys.stderr,
            )
            print(json.dumps(field_delta, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(_zip_info(MANIFEST_NAME), manifest_bytes, compresslevel=9)
        for path in files:
            archive.writestr(
                _zip_info(path.relative_to(source_dir).as_posix()),
                path.read_bytes(),
                compresslevel=9,
            )
    temporary.replace(output)

    report = {
        "output": str(output),
        **{
            key: value
            for key, value in manifest.items()
            if key != "preset_field_inventory"
        },
        "preset_field_counts": {
            scope: len(fields) for scope, fields in field_inventory.items()
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
