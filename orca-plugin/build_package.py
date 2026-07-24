from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "filamenthub_plugin.py"

# The source is kept dev-convenient — a localhost default and diagnostic logging so
# it can be run directly against a local contour. The prod wheel must carry none of
# that: prod_source() drops the marked dev block and every fh_log(...) call and
# forces the prod site URL, so the Hub artifact stays lean and can never ship a
# localhost default.
DEV_BLOCK_START = "# fh-dev:start"
DEV_BLOCK_END = "# fh-dev:end"
DEV_SITE_DEFAULT = '"http://localhost:3000"'
PROD_SITE_DEFAULT = '"https://filamenthub.ru"'


def extract_metadata(source: str) -> dict[str, object]:
    lines = source.splitlines()
    try:
        start = lines.index("# /// script")
        end = lines.index("# ///", start + 1)
    except ValueError as exc:
        raise ValueError("PEP 723 metadata block is missing") from exc

    metadata_lines: list[str] = []
    for line in lines[start + 1 : end]:
        if not line.startswith("#"):
            raise ValueError("Every PEP 723 metadata line must be a comment")
        metadata_lines.append(line[2:] if line.startswith("# ") else line[1:])

    metadata = tomllib.loads("\n".join(metadata_lines))
    plugin = metadata.get("tool", {}).get("orcaslicer", {}).get("plugin", {})
    if not isinstance(plugin, dict):
        raise ValueError("[tool.orcaslicer.plugin] metadata is missing")
    if plugin.get("id") != "filamenthub":
        raise ValueError("Plugin id must remain 'filamenthub'")
    version = plugin.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("Plugin version is missing")
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        raise ValueError("Plugin Hub version must use numeric X.Y.Z format")
    if metadata.get("dependencies") != []:
        raise ValueError("The single-file package must remain dependency-free")
    return metadata


def extract_runtime_version(source: str) -> str:
    module = ast.parse(source, filename=str(SOURCE))
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "PLUGIN_VERSION" for target in node.targets):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    raise ValueError("PLUGIN_VERSION constant is missing")


def prod_source(source: str) -> str:
    """Return the source stripped of all dev-only diagnostics with the prod site
    URL forced. Raises if the input is not the expected dev source, so an
    unnormalized wheel can never ship silently."""
    out: list[str] = []
    in_dev_block = False
    saw_marker = False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(DEV_BLOCK_START):
            in_dev_block = True
            saw_marker = True
            continue
        if stripped.startswith(DEV_BLOCK_END):
            in_dev_block = False
            continue
        if in_dev_block or line.lstrip().startswith("fh_log("):
            continue
        out.append(line)
    if not saw_marker:
        raise ValueError(f"{DEV_BLOCK_START!r} marker not found — refusing to build an unnormalized wheel")
    result = "\n".join(out)
    if source.endswith("\n"):
        result += "\n"
    if DEV_SITE_DEFAULT not in result:
        raise ValueError("dev SITE_URL default not found — cannot force the prod URL")
    result = result.replace(DEV_SITE_DEFAULT, PROD_SITE_DEFAULT)
    ast.parse(result, filename="filamenthub_plugin.py[prod]")
    for token in ("fh_log", "DEBUG_LOG", ".fh_sync.log", DEV_BLOCK_START, DEV_SITE_DEFAULT):
        if token in result:
            raise ValueError(f"prod source still contains a dev token: {token!r}")
    return result


def _build_wheel(prod_bytes: bytes, version: str, output_root: Path) -> Path:
    """Build the Hub wheel from the prod-normalized module in an isolated dir, so
    setuptools never packages the in-place dev source."""
    build_dir = output_root / "prod-build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    (build_dir / "filamenthub_plugin.py").write_bytes(prod_bytes)
    shutil.copy2(ROOT / "pyproject.toml", build_dir / "pyproject.toml")
    wheels_out = output_root / "wheels"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheels_out)],
        cwd=build_dir,
        check=True,
    )
    return wheels_out / f"filamenthub-{version}-py3-none-any.whl"


def build(output_root: Path, wheel: bool = True) -> Path:
    source_bytes = SOURCE.read_bytes()
    source = source_bytes.decode("utf-8")
    ast.parse(source, filename=str(SOURCE))
    metadata = extract_metadata(source)
    plugin = metadata["tool"]["orcaslicer"]["plugin"]
    version = plugin["version"]
    runtime_version = extract_runtime_version(source)
    if runtime_version != version:
        raise ValueError(
            f"Metadata version {version!r} does not match PLUGIN_VERSION {runtime_version!r}"
        )

    prod_bytes = prod_source(source).encode("utf-8")

    package_dir = output_root / f"filamenthub-{version}"
    package_dir.mkdir(parents=True, exist_ok=True)
    package_path = package_dir / "filamenthub_plugin.py"
    package_path.write_bytes(prod_bytes)

    digest = hashlib.sha256(prod_bytes).hexdigest()
    (package_dir / "SHA256SUMS").write_text(
        f"{digest}  filamenthub_plugin.py\n", encoding="utf-8", newline="\n"
    )
    (package_dir / "package-metadata.json").write_text(
        json.dumps(
            {
                "id": plugin["id"],
                "name": plugin["name"],
                "description": plugin["description"],
                "author": plugin["author"],
                "version": version,
                "network": plugin.get("network", []),
                "requires_python": metadata.get("requires-python"),
                "dependencies": metadata.get("dependencies"),
                "entry_file": package_path.name,
                "sha256": digest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if wheel:
        wheel_path = _build_wheel(prod_bytes, version, output_root)
        print(wheel_path)
    return package_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the FilamentHub OrcaSlicer plugin package")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist",
        help="Output root (default: orca-plugin/dist)",
    )
    parser.add_argument(
        "--no-wheel",
        action="store_true",
        help="Only stage the prod-normalized package; skip building the wheel",
    )
    args = parser.parse_args()
    package_dir = build(args.output.resolve(), wheel=not args.no_wheel)
    print(package_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
