"""Copy the printer-protocol modules that Edge shares with the OrcaSlicer plugin.

The plugin is one file installed into OrcaSlicer and Edge is a package built
from ``edge-agent/`` alone, so neither can import the other. What both must
read the same way (a Bambu status report, a Bambu printer certificate) is
written once, in ``orca-plugin/``, and copied here. Run this after editing a
source module; the Edge tests fail while a copy differs from its source.
"""

from __future__ import annotations

import argparse
from pathlib import Path

EDGE_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = EDGE_ROOT.parent / "orca-plugin"
PROVIDERS = EDGE_ROOT / "src" / "filamenthub_edge" / "providers"
MIRRORS = {
    "filamenthub_bambu.py": "_bambu_report.py",
    "filamenthub_bambu_trust.py": "_bambu_trust.py",
}


def render(source_name: str, source: str) -> str:
    return (
        f"# Copy of orca-plugin/{source_name}. Do not edit: change that file and run\n"
        "# edge-agent/scripts/mirror_plugin_modules.py.\n"
        "# ruff: noqa\n"
        "# mypy: ignore-errors\n" + source
    )


def mirrors() -> list[tuple[Path, str]]:
    """Each copy's path and the text it must hold."""
    return [
        (PROVIDERS / target, render(name, (PLUGIN_ROOT / name).read_text(encoding="utf-8")))
        for name, target in MIRRORS.items()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report differences, write nothing")
    args = parser.parse_args()
    stale = []
    for path, text in mirrors():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        stale.append(path.name)
        if not args.check:
            path.write_text(text, encoding="utf-8", newline="\n")
    if stale and args.check:
        raise SystemExit("Out of date: " + ", ".join(stale))
    print("updated: " + ", ".join(stale) if stale else "up to date")


if __name__ == "__main__":
    main()
