"""Copy the printer-protocol code that Edge shares with the OrcaSlicer plugin.

The plugin is one file installed into OrcaSlicer and Edge is a package built
from ``edge-agent/`` alone, so neither can import the other. What both must
do the same way (read a Bambu status report, judge a Bambu printer
certificate, count a Bambu job's filament) is written once, in
``orca-plugin/``, and copied here. Run this after editing a source; the Edge
tests fail while a copy differs from it.

Whole modules are copied as they are. From the plugin's main file only the
named definitions are taken, in the order they appear there.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

EDGE_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = EDGE_ROOT.parent / "orca-plugin"
PROVIDERS = EDGE_ROOT / "src" / "filamenthub_edge" / "providers"
MODULES = {
    "filamenthub_bambu.py": "_bambu_report.py",
    "filamenthub_bambu_trust.py": "_bambu_trust.py",
}
PLUGIN_FILE = "filamenthub_plugin.py"
# How a Bambu job's filament is counted: the per-slot estimate read from the
# print file, and the bookkeeping that turns successive reports into usage.
USAGE_TARGET = "_bambu_usage.py"
USAGE_NAMES = (
    "_MAX_INPUT",
    "_MAX_METADATA",
    "_MAX_GCODE",
    "_MAX_RATIO",
    "_WEIGHT_VECTOR_RE",
    "_LAYER_CHANGE_RE",
    "_TOOL_COMMAND_RE",
    "_EXTRUSION_RE",
    "_bambu_number",
    "_finite_positive",
    "_weights_from_gcode",
    "_weights_from_gcode_stream",
    "_layer_weights_from_gcode_stream",
    "_layer_weights_from_gcode",
    "_safe_zip_info",
    "_normal_name",
    "_plate_number",
    "_weights_from_slice_info",
    "parse_bambu_consumption_file",
    "_bambu_job_key",
    "_bambu_file_candidates",
    "_bambu_usage_routes",
    "_bambu_progress",
    "_bambu_usage_counters",
    "capture_bambu_usage",
    "_buffer_bambu_usage_report",
)
USAGE_PRELUDE = '''\
"""Counting a Bambu job's filament, as the OrcaSlicer plugin does it.

Definitions taken from the plugin's main file; nothing here opens a
connection or touches a file on disk.
"""

import datetime
import hashlib
import io
import json
import math
import posixpath
import re
import uuid
import zipfile
from xml.etree import ElementTree

from ._bambu_report import BAMBU_WIDE_UNIT_BASE, _bambu_bits, _bambu_int, parse_bambu_feed
'''


def _header(source_name: str) -> str:
    return (
        f"# Copy of orca-plugin/{source_name}. Do not edit: change that file and run\n"
        "# edge-agent/scripts/mirror_plugin_modules.py.\n"
        "# ruff: noqa\n"
        "# mypy: ignore-errors\n"
    )


def _extract(source: str, names: tuple[str, ...]) -> str:
    """The source text of the named top-level definitions, in file order."""
    # Split the way the parser counts lines: str.splitlines also breaks on
    # separators that may sit inside a string literal.
    lines = [line + chr(10) for line in source.split(chr(10))]
    found: dict[str, str] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            name = node.name
            start = min([node.lineno, *(item.lineno for item in node.decorator_list)])
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name = node.targets[0].id
            start = node.lineno
        else:
            continue
        if name not in names:
            continue
        if name in found:
            raise SystemExit(f"{name} is defined more than once in the plugin")
        found[name] = "".join(lines[start - 1 : node.end_lineno])
    missing = [name for name in names if name not in found]
    if missing:
        raise SystemExit("Not found in the plugin: " + ", ".join(missing))
    return "\n\n".join(found[name] for name in found)


def mirrors() -> list[tuple[Path, str]]:
    """Each copy's path and the text it must hold."""
    result = [
        (PROVIDERS / target, _header(name) + (PLUGIN_ROOT / name).read_text(encoding="utf-8"))
        for name, target in MODULES.items()
    ]
    plugin = (PLUGIN_ROOT / PLUGIN_FILE).read_text(encoding="utf-8")
    result.append(
        (
            PROVIDERS / USAGE_TARGET,
            _header(PLUGIN_FILE) + USAGE_PRELUDE + "\n\n" + _extract(plugin, USAGE_NAMES),
        )
    )
    return result


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
