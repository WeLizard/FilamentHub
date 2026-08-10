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
LOCALES = ROOT / "filamenthub_locales"

# The source carries a localhost default so it can be run against a local contour.
# The wheel must never ship that, so prod_source() forces the prod site URL, which
# also flips the plugin off its dev contour and hides the Log button.
DEV_SITE_DEFAULT = '"http://localhost:3000"'
PROD_SITE_DEFAULT = '"https://filamenthub.ru"'
EMBEDDED_UI_COPY_TOKEN = "_EMBEDDED_UI_COPY = {}"


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


def _source_with_embedded_locales(source: str) -> str:
    """Embed the authoritative JSON catalogs into one installable Python file."""
    result = source.replace("\r\n", "\n").replace("\r", "\n")
    if result.count(EMBEDDED_UI_COPY_TOKEN) != 1:
        raise ValueError("embedded locale marker is missing or duplicated")
    catalogs = {}
    for locale_path in sorted(LOCALES.glob("*.json")):
        data = json.loads(locale_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in data.items()
        ):
            raise ValueError(f"invalid locale catalog: {locale_path.name}")
        catalogs[locale_path.stem] = data
    embedded = json.dumps(
        catalogs,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result = result.replace(
        EMBEDDED_UI_COPY_TOKEN,
        "_EMBEDDED_UI_COPY = " + embedded,
        1,
    )
    return result


def dev_source(source: str) -> str:
    """Return a localhost-default single file with all UI catalogs embedded."""
    if DEV_SITE_DEFAULT not in source:
        raise ValueError("dev SITE_URL default not found")
    result = _source_with_embedded_locales(source)
    ast.parse(result, filename="filamenthub_plugin.py[dev]")
    return result


def prod_source(source: str) -> str:
    """Return the source with the prod site URL forced. Raises if the input is not
    the expected dev source, so an unnormalized wheel can never ship silently.

    The release source is also normalized to LF for reproducible single-file
    packages across build platforms.
    """
    if DEV_SITE_DEFAULT not in source:
        raise ValueError("dev SITE_URL default not found — cannot force the prod URL")
    result = source.replace(DEV_SITE_DEFAULT, PROD_SITE_DEFAULT)
    result = _source_with_embedded_locales(result)
    ast.parse(result, filename="filamenthub_plugin.py[prod]")
    if DEV_SITE_DEFAULT in result:
        raise ValueError(f"prod source still contains a dev token: {DEV_SITE_DEFAULT!r}")
    return result


def build_dev(output_root: Path) -> Path:
    """Stage the localhost-default, translation-complete single-file plugin."""
    source = SOURCE.read_text(encoding="utf-8")
    ast.parse(source, filename=str(SOURCE))
    metadata = extract_metadata(source)
    plugin = metadata["tool"]["orcaslicer"]["plugin"]
    version = plugin["version"]
    runtime_version = extract_runtime_version(source)
    if runtime_version != version:
        raise ValueError(
            f"Metadata version {version!r} does not match PLUGIN_VERSION {runtime_version!r}"
        )

    dev_dir = output_root / f"filamenthub-{version}-dev"
    dev_dir.mkdir(parents=True, exist_ok=True)
    dev_path = dev_dir / "filamenthub_plugin.py"
    dev_path.write_text(dev_source(source), encoding="utf-8", newline="\n")
    return dev_path


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
    package_locales = package_dir / LOCALES.name
    if package_locales.exists():
        shutil.rmtree(package_locales)
    shutil.copytree(LOCALES, package_locales)

    digest = hashlib.sha256(prod_bytes).hexdigest()
    checksum_lines = [f"{digest}  filamenthub_plugin.py"]
    for locale_path in sorted(package_locales.glob("*.json")):
        locale_digest = hashlib.sha256(locale_path.read_bytes()).hexdigest()
        checksum_lines.append(
            f"{locale_digest}  {LOCALES.name}/{locale_path.name}"
        )
    (package_dir / "SHA256SUMS").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n"
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
                "locales": sorted(path.stem for path in package_locales.glob("*.json")),
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
    parser.add_argument(
        "--dev-source",
        action="store_true",
        help="Stage one localhost-default .py with all locale catalogs embedded",
    )
    args = parser.parse_args()
    if args.dev_source:
        dev_path = build_dev(args.output.resolve())
        print(dev_path)
        return 0
    package_dir = build(args.output.resolve(), wheel=not args.no_wheel)
    print(package_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
