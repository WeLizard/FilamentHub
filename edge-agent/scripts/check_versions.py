"""Verify that every FilamentHub Edge release surface has one version."""

from __future__ import annotations

import argparse
import ast
import re
import tomllib
from pathlib import Path

EDGE_ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(r"\d+\.\d+\.\d+")


def _runtime_version(path: Path) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        assigns_runtime_version = any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        )
        if not assigns_runtime_version:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise SystemExit(f"No literal __version__ assignment in {path}")


def _matched_version(path: Path, pattern: re.Pattern[str], label: str) -> str:
    match = pattern.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"No {label} version in {path}")
    return match.group(1)


def edge_versions() -> dict[str, str]:
    pyproject = tomllib.loads((EDGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        "package": pyproject["project"]["version"],
        "runtime": _runtime_version(EDGE_ROOT / "src/filamenthub_edge/__init__.py"),
        "home_assistant": _matched_version(
            EDGE_ROOT / "home-assistant/filamenthub_edge/config.yaml",
            re.compile(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.MULTILINE),
            "Home Assistant",
        ),
        "image": _matched_version(
            EDGE_ROOT / "Dockerfile",
            re.compile(r"^ARG BUILD_VERSION=([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.MULTILINE),
            "Docker image",
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", help="expected numeric version")
    parser.add_argument("--tag", help="expected release tag in edge-vX.Y.Z form")
    parser.add_argument("--print-version", action="store_true")
    args = parser.parse_args()

    versions = edge_versions()
    unique_versions = set(versions.values())
    if len(unique_versions) != 1:
        details = ", ".join(f"{name}={version!r}" for name, version in versions.items())
        raise SystemExit(f"Edge versions differ: {details}")

    version = versions["package"]
    if SEMVER_PATTERN.fullmatch(version) is None:
        raise SystemExit(f"A numeric Edge version is required, got {version!r}")
    if args.expected is not None and args.expected != version:
        raise SystemExit(f"Expected Edge {args.expected!r}, found {version!r}")
    if args.tag is not None and args.tag != f"edge-v{version}":
        raise SystemExit(f"Release tag {args.tag!r} must be edge-v{version}")
    if args.print_version:
        print(version)


if __name__ == "__main__":
    main()
