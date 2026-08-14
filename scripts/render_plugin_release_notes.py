from __future__ import annotations

import argparse
import ast
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")


def read_assignment(path: Path, name: str) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise ValueError(f"{name} is missing from {path}")


def read_project_version(path: Path) -> str:
    project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
    version = project.get("version")
    if not isinstance(version, str):
        raise ValueError(f"project.version is missing from {path}")
    return version


def extract_changelog_section(path: Path, version: str) -> str:
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(f"Invalid release version {version!r}")

    lines = path.read_text(encoding="utf-8").splitlines()
    headings = [
        (index, match.group("version"))
        for index, line in enumerate(lines)
        if (match := re.fullmatch(r"## (?P<version>\d+\.\d+\.\d+)", line.strip()))
    ]
    if not headings:
        raise ValueError(f"No numeric release sections found in {path}")
    if headings[0][1] != version:
        raise ValueError(
            f"Top changelog section in {path} is {headings[0][1]}, expected {version}"
        )

    start = headings[0][0] + 1
    end = headings[1][0] if len(headings) > 1 else len(lines)
    body = "\n".join(lines[start:end]).strip()
    if not body:
        raise ValueError(f"Changelog section {version} in {path} is empty")
    return body


def render_orca_release_notes(root: Path = ROOT) -> str:
    orca_version = read_assignment(
        root / "orca-plugin" / "filamenthub_plugin.py", "PLUGIN_VERSION"
    )
    orca_notes = extract_changelog_section(
        root / "orca-plugin" / "CHANGELOG.md", orca_version
    )
    return (
        f"## FilamentHub for OrcaSlicer {orca_version}\n\n"
        f"{orca_notes}\n\n"
        "Package checksums are available in `SHA256SUMS`.\n"
    )


def render_bridge_release_notes(root: Path = ROOT) -> str:
    bridge_package_version = read_project_version(
        root / "octoprint-plugin" / "pyproject.toml"
    )
    bridge_runtime_version = read_assignment(
        root / "octoprint-plugin" / "octoprint_filamenthub_bridge" / "__init__.py",
        "PLUGIN_VERSION",
    )
    if bridge_package_version != bridge_runtime_version:
        raise ValueError(
            "OctoPrint Bridge versions differ: "
            f"package={bridge_package_version}, runtime={bridge_runtime_version}"
        )

    bridge_notes = extract_changelog_section(
        root / "octoprint-plugin" / "CHANGELOG.md", bridge_package_version
    )
    return (
        f"## FilamentHub Bridge for OctoPrint {bridge_package_version}\n\n"
        f"{bridge_notes}\n\n"
        "Package checksums are available in `SHA256SUMS`.\n"
    )


def render_release_notes(root: Path = ROOT) -> str:
    orca_notes = render_orca_release_notes(root).removesuffix(
        "Package checksums are available in `SHA256SUMS`.\n"
    ).rstrip()
    bridge_notes = render_bridge_release_notes(root).removesuffix(
        "Package checksums are available in `SHA256SUMS`.\n"
    ).strip()
    return (
        f"{orca_notes}\n\n"
        f"{bridge_notes}\n\n"
        "Package checksums are available in `SHA256SUMS`.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render GitHub release notes from the current plugin changelogs."
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--component",
        choices=("all", "orca", "bridge"),
        default="all",
    )
    args = parser.parse_args()

    renderers = {
        "all": render_release_notes,
        "orca": render_orca_release_notes,
        "bridge": render_bridge_release_notes,
    }
    notes = renderers[args.component]()
    if args.output is None:
        print(notes, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(notes, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
