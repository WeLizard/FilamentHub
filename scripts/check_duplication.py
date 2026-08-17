"""Find copied code that should live in one place.

Three checks, from most to least certain:

* repeated ``className`` strings — an exact copy of a styling decision, which is
  what made one blur change touch thirty-nine call sites;
* repeated string literals — a value or key that has no single owner;
* repeated blocks of statements — logic copied instead of shared.

Exact repetition is what a script finds reliably; whether it deserves extracting
is a judgement call, so this reports and never rewrites. Some repetition is
coincidence, and coupling genuinely separate concerns to remove it is worse than
leaving it alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SEARCH_ROOTS = ("frontend/src", "backend/app")
SKIP_DIRS = {
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    # Migrations repeat Alembic boilerplate by design and are never edited again.
    "versions",
}
CODE_SUFFIXES = {".ts", ".tsx", ".py"}

CLASSNAME_RE = re.compile(r'className\s*=\s*"([^"]{4,})"')
# Matched without a length bound so that quotes pair correctly; short values are
# dropped afterwards. A bounded pattern re-pairs the closing quote of one literal
# with the opening quote of the next and reports the code between them.
STRING_LITERAL_RE = re.compile(r'"([^"\n\\]*)"|\'([^\'\n\\]*)\'')

MIN_LITERAL_LENGTH = 12

# Tokens that carry visual identity. A class string built only of layout utilities
# is an idiom every page repeats on purpose; naming it would buy nothing.
IDENTITY_TOKEN_RE = re.compile(
    r"^(bg-|border|shadow|rounded|backdrop-|ring-|from-|via-|to-|text-(?!left|right|center|xs|sm|base|lg|xl|\dxl))"
)
CLASS_TOKEN_RE = re.compile(r"^[a-z][a-z0-9:/\[\].-]*$")
PY_IGNORABLE_RE = re.compile(r"^\s*(#|\"\"\"|'''|from |import |@|\)|\]|\}|else:|try:)")
TS_IGNORABLE_RE = re.compile(r"^\s*(//|/\*|\*|import |export \{|\)|\]|\}|<|/>)")


class Finding(NamedTuple):
    """One repeated thing and where it repeats."""

    kind: str
    count: int
    files: list[str]
    sample: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "count": self.count,
            "files": self.files,
            "sample": self.sample,
        }


def _iter_files(roots: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        base = PROJECT_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in CODE_SUFFIXES or not path.is_file():
                continue
            if SKIP_DIRS.intersection(part for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _placements(occurrences: list[tuple[Path, int]]) -> list[str]:
    seen: dict[str, int] = defaultdict(int)
    for path, _line in occurrences:
        seen[_relative(path)] += 1
    return [f"{name} ×{n}" if n > 1 else name for name, n in sorted(seen.items())]


def _looks_like_class_list(value: str) -> bool:
    tokens = value.split()
    return len(tokens) >= 2 and all(CLASS_TOKEN_RE.match(token) for token in tokens)


def _is_styling_decision(value: str) -> bool:
    tokens = value.split()
    return len(tokens) >= 3 and any(IDENTITY_TOKEN_RE.match(token) for token in tokens)


def find_repeated_classnames(files: list[Path], threshold: int) -> list[Finding]:
    """Identical class strings: the same styling decision written out repeatedly."""
    hits: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for path in files:
        if path.suffix != ".tsx":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in CLASSNAME_RE.finditer(line):
                value = " ".join(match.group(1).split())
                if _is_styling_decision(value):
                    hits[value].append((path, number))

    return [
        Finding("className", len(places), _placements(places), value)
        for value, places in hits.items()
        if len(places) >= threshold
    ]


def find_repeated_literals(files: list[Path], threshold: int) -> list[Finding]:
    """The same literal in several files: a value without a single owner."""
    hits: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ", "//", "#", "*", '"""', "'''")):
                continue
            for match in STRING_LITERAL_RE.finditer(line):
                value = match.group(1) if match.group(1) is not None else match.group(2)
                if len(value) < MIN_LITERAL_LENGTH or " " not in value:
                    continue
                if value.startswith(("http", "/", ".")):
                    continue
                # Class strings have their own check, and SQL/enum keywords such as
                # "SET NULL" repeat because the vocabulary is fixed.
                if _looks_like_class_list(value) or value.upper() == value:
                    continue
                hits[value].append((path, number))

    findings = []
    for value, places in hits.items():
        distinct_files = {path for path, _ in places}
        if len(places) < threshold or len(distinct_files) < 2:
            continue
        # Repetition inside declarative models is the ORM's shape, not copied logic.
        if all("app/models/" in _relative(path) for path in distinct_files):
            continue
        findings.append(Finding("literal", len(places), _placements(places), value))
    return findings


def _significant_lines(path: Path) -> list[tuple[int, str]]:
    ignorable = PY_IGNORABLE_RE if path.suffix == ".py" else TS_IGNORABLE_RE
    lines = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if len(stripped) < 4 or ignorable.match(raw):
            continue
        lines.append((number, " ".join(stripped.split())))
    return lines


def find_repeated_blocks(files: list[Path], window: int) -> list[Finding]:
    """Runs of identical statements — logic copied rather than shared."""
    hits: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for path in files:
        lines = _significant_lines(path)
        for start in range(len(lines) - window + 1):
            chunk = lines[start : start + window]
            body = "\n".join(text for _n, text in chunk)
            digest = hashlib.sha1(body.encode("utf-8")).hexdigest()
            hits[digest].append((path, chunk[0][0]))

    findings = []
    samples: dict[str, str] = {}
    for path in files:
        lines = _significant_lines(path)
        for start in range(len(lines) - window + 1):
            chunk = lines[start : start + window]
            body = "\n".join(text for _n, text in chunk)
            samples.setdefault(hashlib.sha1(body.encode("utf-8")).hexdigest(), chunk[0][1])

    for digest, places in hits.items():
        distinct_files = {path for path, _ in places}
        # Overlapping windows inside one function would report the same copy many times.
        if len(places) < 2 or (len(distinct_files) == 1 and len(places) < 3):
            continue
        findings.append(
            Finding("block", len(places), _placements(places), samples[digest] + " …")
        )
    return findings


def _dedupe_blocks(findings: list[Finding]) -> list[Finding]:
    """One report per set of places, not one per overlapping window."""
    best: dict[tuple[str, ...], Finding] = {}
    for finding in findings:
        key = tuple(finding.files)
        if key not in best or finding.count > best[key].count:
            best[key] = finding
    return list(best.values())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classname-threshold", type=int, default=3)
    parser.add_argument("--literal-threshold", type=int, default=4)
    parser.add_argument("--block-window", type=int, default=8)
    parser.add_argument("--top", type=int, default=15, help="findings shown per check")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--fail-over",
        type=int,
        default=None,
        help="exit 1 when total findings exceed this number",
    )
    return parser.parse_args()


def _report(title: str, findings: list[Finding], top: int) -> None:
    print(f"\n{title}: {len(findings)}")
    if not findings:
        return
    for finding in sorted(findings, key=lambda item: item.count, reverse=True)[:top]:
        print(f"  ×{finding.count}  {finding.sample[:100]}")
        for place in finding.files[:6]:
            print(f"        {place}")
        if len(finding.files) > 6:
            print(f"        … ещё файлов: {len(finding.files) - 6}")


def main() -> int:
    args = _parse_args()
    files = _iter_files(SEARCH_ROOTS)

    classnames = find_repeated_classnames(files, args.classname_threshold)
    literals = find_repeated_literals(files, args.literal_threshold)
    blocks = _dedupe_blocks(find_repeated_blocks(files, args.block_window))
    total = len(classnames) + len(literals) + len(blocks)

    if args.as_json:
        print(
            json.dumps(
                {
                    "files_scanned": len(files),
                    "classnames": [item.as_dict() for item in classnames],
                    "literals": [item.as_dict() for item in literals],
                    "blocks": [item.as_dict() for item in blocks],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Просмотрено файлов: {len(files)}")
        _report("Повторяющиеся строки классов", classnames, args.top)
        _report("Повторяющиеся литералы", literals, args.top)
        _report("Повторяющиеся блоки кода", blocks, args.top)
        print(f"\nВсего находок: {total}")

    if args.fail_over is not None and total > args.fail_over:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
