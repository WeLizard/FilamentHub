"""Build one versioned, reproducible OctoPrint Bridge release candidate."""

from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "octoprint_filamenthub_bridge"
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"
RELEASE_NOTES_RENDERER = ROOT.parent / "scripts" / "render_plugin_release_notes.py"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
TEXT_PACKAGE_SUFFIXES = {".css", ".jinja2", ".js", ".json", ".md", ".py", ".txt"}


def _normalized_text(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _canonical_package_payload(name: str, payload: bytes) -> bytes:
    if Path(name).suffix.lower() in TEXT_PACKAGE_SUFFIXES:
        return _normalized_text(payload)
    return payload


def _runtime_version() -> str:
    source_path = PACKAGE / "__init__.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    versions = [
        node.value.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "PLUGIN_VERSION"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    if len(versions) != 1:
        raise ValueError("PLUGIN_VERSION must be assigned exactly once")
    return versions[0]


def current_version() -> str:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    package_version = project["version"]
    runtime_version = _runtime_version()
    if package_version != runtime_version:
        raise ValueError(
            f"Package version {package_version!r} does not match "
            f"PLUGIN_VERSION {runtime_version!r}"
        )
    return package_version


def default_release_output_root() -> Path:
    return ROOT / "dist" / f"release-{current_version()}"


def _record_digest(payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
    return "sha256=" + digest.rstrip(b"=").decode("ascii")


def _canonical_metadata(version: str) -> bytes:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    authors = project.get("authors")
    if not isinstance(authors, list) or len(authors) != 1:
        raise ValueError("The Bridge wheel must declare exactly one author")
    author = authors[0].get("name") if isinstance(authors[0], dict) else None
    fields = {
        "name": project.get("name"),
        "description": project.get("description"),
        "requires-python": project.get("requires-python"),
        "license": project.get("license"),
        "author": author,
    }
    if not all(isinstance(value, str) and value for value in fields.values()):
        raise ValueError("Bridge project metadata is incomplete")
    readme = README.read_bytes()
    return (
        "Metadata-Version: 2.4\n"
        f"Name: {fields['name']}\n"
        f"Version: {version}\n"
        f"Summary: {fields['description']}\n"
        f"Author: {fields['author']}\n"
        f"License-Expression: {fields['license']}\n"
        f"Requires-Python: {fields['requires-python']}\n"
        "Description-Content-Type: text/markdown\n"
        "\n"
    ).encode("utf-8") + _normalized_text(readme).rstrip(b"\n") + b"\n"


def _canonical_wheel_metadata() -> bytes:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: filamenthub octoprint build_package.py\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
        "\n"
    ).encode("utf-8")


def _normalize_wheel(wheel_path: Path, version: str) -> None:
    with zipfile.ZipFile(wheel_path) as archive:
        original = {name: archive.read(name) for name in archive.namelist()}

    dist_info = f"octoprint_filamenthubbridge-{version}.dist-info"
    metadata_path = f"{dist_info}/METADATA"
    wheel_metadata_path = f"{dist_info}/WHEEL"
    entry_points_path = f"{dist_info}/entry_points.txt"
    top_level_path = f"{dist_info}/top_level.txt"
    record_path = f"{dist_info}/RECORD"
    expected_dist_info = {
        metadata_path,
        wheel_metadata_path,
        entry_points_path,
        top_level_path,
        record_path,
    }
    package_entries = {
        name for name in original if name.startswith("octoprint_filamenthub_bridge/")
    }
    if set(original) != package_entries | expected_dist_info or not package_entries:
        raise ValueError(
            "Bridge wheel contents differ from the dependency-free package contract: "
            f"{sorted(original)}"
        )

    payloads = {
        name: _canonical_package_payload(name, original[name])
        for name in package_entries
    }
    payloads.update(
        {
            metadata_path: _canonical_metadata(version),
            wheel_metadata_path: _canonical_wheel_metadata(),
            entry_points_path: (
                b"[octoprint.plugin]\n"
                b"filamenthub_bridge = octoprint_filamenthub_bridge\n"
            ),
            top_level_path: b"octoprint_filamenthub_bridge\n",
        }
    )
    rows = [
        [name, _record_digest(payloads[name]), str(len(payloads[name]))]
        for name in sorted(payloads)
    ]
    rows.append([record_path, "", ""])
    record_buffer = io.StringIO(newline="")
    csv.writer(record_buffer, lineterminator="\n").writerows(rows)
    payloads[record_path] = record_buffer.getvalue().encode("utf-8")

    temporary = wheel_path.with_suffix(wheel_path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name in sorted(payloads):
                entry = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
                entry.compress_type = zipfile.ZIP_STORED
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, payloads[name])
        temporary.replace(wheel_path)
    finally:
        temporary.unlink(missing_ok=True)


def _copy_build_source(destination: Path) -> None:
    shutil.copytree(PACKAGE, destination / PACKAGE.name)
    for filename in ("pyproject.toml", "README.md", "MANIFEST.in", "CHANGELOG.md"):
        shutil.copy2(ROOT / filename, destination / filename)


def build(output_root: Path) -> tuple[Path, Path]:
    version = current_version()
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="filamenthub-octoprint-") as temporary:
        build_source = Path(temporary) / "source"
        build_output = Path(temporary) / "package"
        build_source.mkdir()
        build_output.mkdir()
        _copy_build_source(build_source)
        environment = os.environ.copy()
        environment["SOURCE_DATE_EPOCH"] = "315532800"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--sdist",
                "--outdir",
                str(build_output),
            ],
            cwd=build_source,
            env=environment,
            check=True,
        )
        wheel_source = build_output / (
            f"octoprint_filamenthubbridge-{version}-py3-none-any.whl"
        )
        sdist_source = build_output / f"octoprint_filamenthubbridge-{version}.tar.gz"
        wheel_path = output_root / wheel_source.name
        sdist_path = output_root / sdist_source.name
        shutil.copy2(wheel_source, wheel_path)
        shutil.copy2(sdist_source, sdist_path)

    _normalize_wheel(wheel_path, version)
    return wheel_path, sdist_path


def stage_release_metadata(
    output_root: Path, wheel_path: Path, sdist_path: Path
) -> tuple[Path, Path]:
    notes_path = output_root / "RELEASE_NOTES.md"
    subprocess.run(
        [
            sys.executable,
            str(RELEASE_NOTES_RENDERER),
            "--component",
            "bridge",
            "--output",
            str(notes_path),
        ],
        cwd=ROOT.parent,
        check=True,
    )
    checksum_path = output_root / "SHA256SUMS"
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in (wheel_path, sdist_path)
    ]
    checksum_path.write_text("".join(lines), encoding="utf-8", newline="\n")
    return notes_path, checksum_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a versioned FilamentHub Bridge release candidate"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output root (default: "
            "octoprint-plugin/dist/release-<current-version>)"
        ),
    )
    args = parser.parse_args()
    output_root = (
        default_release_output_root()
        if args.output is None
        else args.output.resolve()
    )
    if args.output is None and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    wheel_path, sdist_path = build(output_root)
    notes_path, checksum_path = stage_release_metadata(
        output_root, wheel_path, sdist_path
    )
    for path in (wheel_path, sdist_path, notes_path, checksum_path):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
