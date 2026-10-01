"""Generate the OrcaSlicer preset option schema from the official sources.

The website renders preset settings from this schema, so it has to say what
OrcaSlicer itself says: which options exist, their labels, tooltips, units,
types, ranges, complexity modes and the tab/group they live in. Nothing is
written by hand; the input is a checkout of the upstream repository read through
``git show`` (the working tree is never touched).

Sources, all read at one upstream commit:

* ``src/libslic3r/PrintConfig.cpp``    option definitions (``PrintConfigDef``)
* ``src/libslic3r/Preset.cpp``         which keys belong to which preset kind
* ``src/slic3r/GUI/Tab.cpp``           pages, groups and row order of the editors
* ``src/libslic3r/PublishSettings.cpp`` key lists the printer extruder page loops over
* ``src/libslic3r/MaterialType.cpp``   values of the open ``filament_type`` list
* ``localization/i18n/{ru,zh_CN}``     translations of the same strings

Usage (from the repository root)::

    python scripts/generate_orca_preset_schema.py --upstream F:/OrcaSlicer-upstream
    python scripts/generate_orca_preset_schema.py --upstream F:/OrcaSlicer-upstream --check

``--check`` regenerates in memory and fails when the committed files differ.
Both OrcaSlicer and FilamentHub are AGPL-3.0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "frontend" / "src" / "data"
DEFAULT_UPSTREAM = Path(os.environ.get("ORCA_UPSTREAM", "F:/OrcaSlicer-upstream"))
DEFAULT_REF = "origin/main"
REPOSITORY = "https://github.com/OrcaSlicer/OrcaSlicer"
SCHEMA_FORMAT = "filamenthub.orca-preset-schema"
SCHEMA_VERSION = 1
KINDS = ("filament", "process", "machine")
OUTPUT_NAME = "orcaPresetSchema.{kind}.json"

SRC_PRINT_CONFIG = "src/libslic3r/PrintConfig.cpp"
SRC_PRESET = "src/libslic3r/Preset.cpp"
SRC_TAB = "src/slic3r/GUI/Tab.cpp"
SRC_PUBLISH = "src/libslic3r/PublishSettings.cpp"
SRC_MATERIAL = "src/libslic3r/MaterialType.cpp"
PO_FILES = {
    "ru": "localization/i18n/ru/OrcaSlicer_ru.po",
    "zh": "localization/i18n/zh_CN/OrcaSlicer_zh_CN.po",
}
SOURCE_FILES = [
    SRC_PRINT_CONFIG,
    SRC_PRESET,
    SRC_TAB,
    SRC_PUBLISH,
    SRC_MATERIAL,
    *PO_FILES.values(),
]

# Orca names the machine pages in the order the tab shows them, but builds the
# multimaterial, extruder and motion pages detached and inserts them by position
# (TabPrinter::build_unregular_pages). The resulting order is fixed here and the
# generator refuses it when the built page titles stop matching.
MACHINE_PAGE_ORDER = (
    "Basic information",
    "Machine G-code",
    "Multimaterial",
    "Extruder",
    "Motion ability",
    "Notes",
)

# ConfigOptionMode: develop is shown to nobody by default; the website treats it
# as expert (see frontend/src/data/orcaFieldModes.ts).
MODE_NAMES = {
    "comSimple": "simple",
    "comAdvanced": "advanced",
    "comExpert": "expert",
    "comDevelop": "expert",
}

BASE_TYPES = {
    "coBool": "bool",
    "coInt": "int",
    "coFloat": "float",
    "coPercent": "percent",
    "coFloatOrPercent": "float_or_percent",
    "coString": "string",
    "coEnum": "enum",
    "coPoint": "points",
    "coPoint3": "points",
    "coNone": "other",
}
VECTOR_BASE = {name + "s": value for name, value in BASE_TYPES.items()}
VECTOR_BASE.update(
    {
        "coFloatsOrPercents": "float_or_percent",
        "coPointsGroups": "points",
        "coIntsGroups": "other",
    }
)
del VECTOR_BASE["coFloatOrPercents"]
ALL_TYPES = {**BASE_TYPES, **VECTOR_BASE}


class Unresolved(Exception):
    """A construct the generator does not understand; reported, never guessed."""


# --------------------------------------------------------------------------
# Upstream access
# --------------------------------------------------------------------------


class Upstream:
    def __init__(self, repository: Path, ref: str) -> None:
        self.repository = repository
        self.ref = ref
        self.commit = self._git("rev-parse", "--verify", f"{ref}^{{commit}}").strip()
        self.committed_at = self._git("log", "-1", "--format=%cI", self.commit).strip()

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repository), *args],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(
                f"git {' '.join(args)} failed in {self.repository}: "
                f"{result.stderr.decode('utf-8', 'replace').strip()}"
            )
        return result.stdout.decode("utf-8")

    def read(self, path: str) -> str:
        return self._git("show", f"{self.commit}:{path}")


# --------------------------------------------------------------------------
# C++ lexing
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Tok:
    kind: str  # id | str | num | punct | chr
    value: str

    def __repr__(self) -> str:
        return f"{self.kind}:{self.value}"


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
    |(?P<lcomment>//[^\n]*)
    |(?P<bcomment>/\*.*?\*/)
    |(?P<str>(?:u8|u|U)?"(?:[^"\\\n]|\\.)*")
    |(?P<chr>'(?:[^'\\\n]|\\.)+')
    |(?P<id>[A-Za-z_][A-Za-z_0-9]*)
    |(?P<num>0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[fFuUlL]*)
    |(?P<punct>::|->|\+\+|--|<<|>>|<=|>=|==|!=|&&|\|\||\+=|-=|\*=|/=|[^\s])
    """,
    re.VERBOSE | re.DOTALL,
)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", '"': '"', "'": "'", "\\": "\\"}


def decode_c_string(literal: str) -> str:
    body = literal[literal.index('"') + 1 : -1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        nxt = body[i + 1]
        if nxt == "u":
            out.append(chr(int(body[i + 2 : i + 6], 16)))
            i += 6
        elif nxt == "U":
            out.append(chr(int(body[i + 2 : i + 10], 16)))
            i += 10
        elif nxt == "x":
            j = i + 2
            while j < len(body) and body[j] in "0123456789abcdefABCDEF":
                j += 1
            out.append(chr(int(body[i + 2 : j], 16)))
            i = j
        else:
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
    return "".join(out)


def strip_inactive_preprocessor(source: str) -> str:
    """Drop ``#define`` bodies and the branches of ``#if`` the build never takes.

    ``#if 0`` and ``#else`` of ``#if 1`` are inactive; any other condition keeps
    its first branch only. Dropped lines are blanked so offsets stay readable.
    """
    lines = source.split("\n")
    out: list[str] = []
    stack: list[bool] = []  # active state of each open conditional
    taken: list[bool] = []  # whether the first branch was the active one
    continuation = False
    for line in lines:
        stripped = line.strip()
        if continuation:
            continuation = line.rstrip().endswith("\\")
            out.append("")
            continue
        if stripped.startswith("#"):
            directive = stripped[1:].strip()
            word = directive.split(None, 1)[0] if directive else ""
            word = re.split(r"\W", word, maxsplit=1)[0]
            if word in ("if", "ifdef", "ifndef"):
                condition = directive[len(word) :].strip()
                active = condition != "0"
                stack.append(active)
                taken.append(active)
            elif word == "else" and stack:
                stack[-1] = not taken[-1]
            elif word == "elif" and stack:
                stack[-1] = False
            elif word == "endif" and stack:
                stack.pop()
                taken.pop()
            if word == "define":
                continuation = line.rstrip().endswith("\\")
            out.append("")
            continue
        out.append(line if all(stack) else "")
    return "\n".join(out)


def tokenize(source: str) -> list[Tok]:
    tokens: list[Tok] = []
    for match in _TOKEN_RE.finditer(strip_inactive_preprocessor(source)):
        kind = match.lastgroup
        if kind in ("ws", "lcomment", "bcomment"):
            continue
        assert kind is not None
        tokens.append(Tok(kind, match.group()))
    return tokens


def is_punct(tok: Tok, value: str) -> bool:
    return tok.kind == "punct" and tok.value == value


_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")", "]", "}"}


def match_close(tokens: list[Tok], index: int) -> int:
    """Index of the bracket closing the one at ``index``."""
    depth = 0
    for i in range(index, len(tokens)):
        tok = tokens[i]
        if tok.kind == "punct":
            if tok.value in _OPEN:
                depth += 1
            elif tok.value in _CLOSE:
                depth -= 1
                if depth == 0:
                    return i
    raise Unresolved("unbalanced brackets")


def split_top(tokens: list[Tok], separator: str) -> list[list[Tok]]:
    parts: list[list[Tok]] = [[]]
    depth = 0
    for tok in tokens:
        if tok.kind == "punct":
            if tok.value in _OPEN:
                depth += 1
            elif tok.value in _CLOSE:
                depth -= 1
            elif tok.value == separator and depth == 0:
                parts.append([])
                continue
        parts[-1].append(tok)
    return parts


def find_top(tokens: list[Tok], value: str) -> int:
    depth = 0
    for i, tok in enumerate(tokens):
        if tok.kind != "punct":
            continue
        if tok.value in _OPEN:
            depth += 1
        elif tok.value in _CLOSE:
            depth -= 1
        elif tok.value == value and depth == 0:
            return i
    return -1


def find_open(tokens: list[Tok], bracket: str) -> int:
    """First ``bracket`` ((, [ or {) that opens at nesting depth zero."""
    depth = 0
    for i, tok in enumerate(tokens):
        if tok.kind != "punct":
            continue
        if tok.value == bracket and depth == 0:
            return i
        if tok.value in _OPEN:
            depth += 1
        elif tok.value in _CLOSE:
            depth -= 1
    return -1


def strip_parens(tokens: list[Tok]) -> list[Tok]:
    while (
        len(tokens) >= 2 and is_punct(tokens[0], "(") and match_close(tokens, 0) == len(tokens) - 1
    ):
        tokens = tokens[1:-1]
    return tokens


def find_call(tokens: list[Tok], name: str) -> tuple[int, list[list[Tok]]] | None:
    """Locate ``name(args...)`` and return its position and top-level arguments."""
    for i in range(len(tokens) - 1):
        if tokens[i].kind == "id" and tokens[i].value == name and is_punct(tokens[i + 1], "("):
            end = match_close(tokens, i + 1)
            inner = tokens[i + 2 : end]
            args = split_top(inner, ",") if inner else []
            return i, args
    return None


# --------------------------------------------------------------------------
# Statement tree
# --------------------------------------------------------------------------


@dataclass
class Simple:
    tokens: list[Tok]


@dataclass
class Block:
    body: list[Any]


@dataclass
class For:
    header: list[Tok]
    body: Any


@dataclass
class If:
    cond: list[Tok]
    then: Any
    other: Any | None


@dataclass
class Opaque:
    pass


def parse_statements(tokens: list[Tok], start: int, end: int) -> list[Any]:
    out: list[Any] = []
    i = start
    while i < end:
        node, i = parse_statement(tokens, i, end)
        if node is not None:
            out.append(node)
    return out


def parse_statement(tokens: list[Tok], i: int, end: int) -> tuple[Any | None, int]:
    tok = tokens[i]
    if is_punct(tok, ";"):
        return None, i + 1
    if is_punct(tok, "{"):
        close = match_close(tokens, i)
        return Block(parse_statements(tokens, i + 1, close)), close + 1
    if (
        tok.kind == "id"
        and tok.value in ("for", "if", "while", "switch")
        and is_punct(tokens[i + 1], "(")
    ):
        close = match_close(tokens, i + 1)
        header = tokens[i + 2 : close]
        if tok.value == "switch":
            body_close = match_close(tokens, close + 1)
            return Opaque(), body_close + 1
        body, j = parse_statement(tokens, close + 1, end)
        if tok.value == "for" or tok.value == "while":
            return For(header, body) if tok.value == "for" else Opaque(), j
        other = None
        if j < end and tokens[j].kind == "id" and tokens[j].value == "else":
            other, j = parse_statement(tokens, j + 1, end)
        return If(header, body, other), j
    depth = 0
    j = i
    while j < end:
        t = tokens[j]
        if t.kind == "punct":
            if t.value in _OPEN:
                depth += 1
            elif t.value in _CLOSE:
                depth -= 1
            elif t.value == ";" and depth == 0:
                break
        j += 1
    return Simple(tokens[i:j]), j + 1


def find_function(tokens: list[Tok], qualified: str) -> list[Any]:
    """Parse the body of ``Class::function(...) { ... }``."""
    cls, name = qualified.split("::")
    for i in range(len(tokens) - 4):
        if (
            tokens[i].kind == "id"
            and tokens[i].value == cls
            and is_punct(tokens[i + 1], "::")
            and tokens[i + 2].kind == "id"
            and tokens[i + 2].value == name
            and is_punct(tokens[i + 3], "(")
        ):
            close = match_close(tokens, i + 3)
            j = close + 1
            while j < len(tokens) and not is_punct(tokens[j], "{"):
                if is_punct(tokens[j], ";"):
                    break
                j += 1
            if j < len(tokens) and is_punct(tokens[j], "{"):
                body_close = match_close(tokens, j)
                return parse_statements(tokens, j + 1, body_close)
    raise Unresolved(f"function {qualified} not found")


# --------------------------------------------------------------------------
# Expression evaluation (only the shapes the sources actually use)
# --------------------------------------------------------------------------

TEXT_MACROS = {"L", "_", "_L", "_u8L", "u8L", "_u8", "Slic3r::I18N::translate"}


def eval_text(tokens: list[Tok], env: dict[str, Any]) -> tuple[str, str | None]:
    """String value of an expression and its gettext context, if any."""
    tokens = strip_parens(tokens)
    if not tokens:
        raise Unresolved("empty expression")
    question = find_top(tokens, "?")
    if question >= 0:
        # `cond ? a : b`: the else branch is the single-extruder / default case
        # in the only ternaries the editors use for titles.
        colon = find_top(tokens[question + 1 :], ":")
        if colon < 0:
            raise Unresolved("ternary without else")
        return eval_text(tokens[question + 1 + colon + 1 :], env)
    plus = split_top(tokens, "+")
    if len(plus) > 1:
        return "".join(eval_text(part, env)[0] for part in plus), None
    if tokens[0].value == "L" and len(tokens) > 1 and all(t.kind == "str" for t in tokens[1:]):
        return "".join(decode_c_string(t.value) for t in tokens[1:]), None
    if all(tok.kind == "str" for tok in tokens):
        return "".join(decode_c_string(tok.value) for tok in tokens), None
    if tokens[0].kind == "id" and len(tokens) >= 3 and is_punct(tokens[1], "("):
        if match_close(tokens, 1) == len(tokens) - 1:
            name = tokens[0].value
            args = split_top(tokens[2:-1], ",")
            if name in TEXT_MACROS:
                return eval_text(args[0], env)
            if name == "L_CONTEXT":
                return eval_text(args[0], env)[0], eval_text(args[1], env)[0]
    if (
        len(tokens) >= 5
        and tokens[0].value == "wxString"
        and is_punct(tokens[1], "::")
        and tokens[2].value == "Format"
    ):
        args = split_top(tokens[4:-1], ",")
        return eval_text(args[0], env)
    for i in range(len(tokens) - 2):
        if (
            tokens[i].value == "format"
            and is_punct(tokens[i - 1], "::")
            and is_punct(tokens[i + 1], "(")
        ):
            close = match_close(tokens, i + 1)
            fmt = eval_text(tokens[i + 2 : close], env)[0]
            operands = split_top(tokens[close + 1 :], "%")[1:]
            for number, operand in enumerate(operands, start=1):
                operand = [t for t in operand if not is_punct(t, ")")]
                value = eval_text(operand[:1], env)[0] if operand else ""
                fmt = fmt.replace(f"%{number}%", value)
            return fmt, None
    if len(tokens) == 1 and tokens[0].kind == "id" and tokens[0].value in env:
        value = env[tokens[0].value]
        if isinstance(value, str):
            return value, None
    if len(tokens) == 3 and is_punct(tokens[1], "."):
        key = f"{tokens[0].value}.{tokens[2].value}"
        if isinstance(env.get(key), str):
            return env[key], None
    raise Unresolved("text expression: " + render(tokens))


def eval_number(tokens: list[Tok], env: dict[str, Any] | None = None) -> float | int:
    tokens = strip_parens(tokens)
    sign = 1
    if tokens and is_punct(tokens[0], "-"):
        sign = -1
        tokens = tokens[1:]
    if len(tokens) == 1 and tokens[0].kind == "id" and env is not None:
        constant = env.get(tokens[0].value)
        if isinstance(constant, (int, float)) and not isinstance(constant, bool):
            return sign * constant
    if len(tokens) == 1 and tokens[0].kind == "num":
        text = tokens[0].value.rstrip("fFuUlL")
        if text.lower().startswith("0x"):
            return sign * int(text, 16)
        value = float(text)
        return sign * (int(value) if value.is_integer() and "." not in text else value)
    raise Unresolved("number expression: " + render(tokens))


def eval_bool(tokens: list[Tok]) -> bool:
    tokens = strip_parens(tokens)
    if len(tokens) == 1 and tokens[0].value in ("true", "false"):
        return tokens[0].value == "true"
    raise Unresolved("bool expression: " + render(tokens))


def render(tokens: list[Tok]) -> str:
    text = " ".join(t.value for t in tokens)
    return text if len(text) <= 160 else text[:157] + "..."


def has_ident(tokens: list[Tok], *names: str) -> bool:
    return any(t.kind == "id" and t.value in names for t in tokens)


def assignment_target(tokens: list[Tok]) -> str | None:
    """Name assigned by ``[type] name = ...`` at the top level."""
    eq = find_top(tokens, "=")
    if eq <= 0 or tokens[eq - 1].kind != "id":
        return None
    return tokens[eq - 1].value


# --------------------------------------------------------------------------
# PrintConfigDef extraction
# --------------------------------------------------------------------------


@dataclass
class OptionDef:
    key: str
    cpp_type: str
    nullable: bool = False
    props: dict[str, Any] = field(default_factory=dict)
    enum_values: list[str] = field(default_factory=list)
    enum_labels: list[str] = field(default_factory=list)
    enum_map: str | None = None
    # gettext context of a text property (only the few strings that carry one).
    contexts: dict[str, str] = field(default_factory=dict)


TEXT_PROPS = ("label", "full_label", "tooltip", "sidetext", "category", "ratio_over", "gui_flags")
NUMBER_PROPS = ("min", "max", "height")
BOOL_PROPS = ("multiline", "full_width", "readonly", "is_code")
IDENT_PROPS = ("mode", "gui_type")


class PrintConfigReader:
    """Evaluate ``PrintConfigDef::init_common_params`` and ``init_fff_params``."""

    def __init__(
        self, tokens: list[Tok], material_names: list[str], enum_maps: dict[str, list[str]]
    ):
        self.tokens = tokens
        self.material_names = material_names
        self.enum_maps = enum_maps
        self.options: dict[str, OptionDef] = OrderedDict()
        self.unresolved: list[dict[str, str]] = []
        self.redefined: list[str] = []
        self.aliases: dict[str, OptionDef] = {}
        self.current: OptionDef | None = None
        self.override_keys = self._string_list("filament_extruder_override_keys")

    def _string_list(self, name: str) -> list[str]:
        for i, tok in enumerate(self.tokens):
            if tok.kind == "id" and tok.value == name and is_punct(self.tokens[i + 1], "="):
                close = match_close(self.tokens, i + 2)
                return [
                    decode_c_string(t.value) for t in self.tokens[i + 3 : close] if t.kind == "str"
                ]
        raise Unresolved(f"list {name} not found")

    def run(self) -> None:
        for function in ("init_common_params", "init_fff_params"):
            env: dict[str, Any] = {}
            for node in find_function(self.tokens, f"PrintConfigDef::{function}"):
                self.exec(node, env)

    def note(self, key: str, prop: str, reason: str) -> None:
        self.unresolved.append({"key": key, "what": prop, "detail": reason})

    def exec(self, node: Any, env: dict[str, Any]) -> None:
        if isinstance(node, Block):
            for child in node.body:
                self.exec(child, env)
        elif isinstance(node, For):
            self.exec_for(node, env)
        elif isinstance(node, Simple):
            self.exec_simple(node.tokens, env)

    def exec_for(self, node: For, env: dict[str, Any]) -> None:
        header = node.header
        colon = find_top(header, ":")
        if colon < 0:
            raise Unresolved("classic for loop in PrintConfigDef: " + render(header))
        variable = header[colon - 1].value
        iterable = header[colon + 1 :]
        if is_punct(iterable[0], "{"):
            for part in split_top(iterable[1:-1], ","):
                inner = {**env, variable: eval_text(part, env)[0]}
                self.exec(node.body, inner)
        elif render(iterable) == "axes":
            # struct AxisDefault list local to init_fff_params: x, y, z, e.
            for axis in ("x", "y", "z", "e"):
                self.exec(node.body, {**env, f"{variable}.name": axis})
        elif render(iterable) == "MaterialType :: all ( )":
            if self.current is None:
                raise Unresolved("material loop without option")
            self.current.enum_values = list(self.material_names)
        elif render(iterable) == "filament_extruder_override_keys":
            self.expand_filament_overrides()
        else:
            raise Unresolved("loop over " + render(iterable))

    def expand_filament_overrides(self) -> None:
        # The loop in init_fff_params derives each `filament_<x>` override from
        # the printer option `<x>`: same text, range and enum, nullable vector,
        # mode simple for the four options OrcaSlicer calls out, advanced otherwise.
        simple = {
            "filament_retraction_length",
            "filament_z_hop",
            "filament_long_retractions_when_cut",
            "filament_retraction_distances_when_cut",
        }
        for key in self.override_keys:
            source = self.options.get(key[len("filament_") :])
            if source is None:
                self.note(key, "override", f"source option {key[9:]} is not defined")
                continue
            derived = OptionDef(key, source.cpp_type, nullable=True)
            for prop in ("label", "full_label", "tooltip", "sidetext", "min", "max"):
                if prop in source.props:
                    derived.props[prop] = source.props[prop]
            derived.contexts = dict(source.contexts)
            derived.enum_values = list(source.enum_values)
            derived.enum_labels = list(source.enum_labels)
            derived.enum_map = source.enum_map
            derived.props["mode"] = "comSimple" if key in simple else "comAdvanced"
            self.register(derived)

    def register(self, option: OptionDef) -> OptionDef:
        existing = self.options.get(option.key)
        if existing is not None:
            # ConfigDef::add reuses the entry of a key that is defined twice, so
            # the later definition only overlays the fields it assigns again.
            self.redefined.append(option.key)
            existing.cpp_type = option.cpp_type
            existing.nullable = existing.nullable or option.nullable
            option = existing
        self.options[option.key] = option
        self.current = option
        return option

    def exec_simple(self, tokens: list[Tok], env: dict[str, Any]) -> None:
        if not tokens:
            return
        if has_ident(tokens, "add", "add_nullable") and any(
            t.value == "def" and is_punct(tokens[i + 1], "=") for i, t in enumerate(tokens[:-1])
        ):
            self.start_option(tokens, env)
            return
        if (
            len(tokens) == 5
            and tokens[0].value == "const"
            and tokens[1].value in ("int", "double", "float")
            and is_punct(tokens[3], "=")
        ):
            env[tokens[2].value] = eval_number(tokens[4:])
            return
        if tokens[0].value == "def" and len(tokens) > 1 and is_punct(tokens[1], "->"):
            self.set_property(tokens, env)
            return
        name = assignment_target(tokens)
        if name and has_ident(tokens, "to_upper_copy"):
            env[name] = env.get("axis.name", "").upper()

    def start_option(self, tokens: list[Tok], env: dict[str, Any]) -> None:
        call = find_call(tokens, "add") or find_call(tokens, "add_nullable")
        if call is None:
            return
        index, args = call
        nullable = tokens[index].value == "add_nullable"
        try:
            key = eval_text(args[0], env)[0]
        except Unresolved as error:
            self.note("?", "key", str(error))
            return
        type_name = render(args[1]) if len(args) > 1 else ""
        if type_name not in ALL_TYPES:
            self.note(key, "type", type_name)
            return
        option = self.register(OptionDef(key, type_name, nullable=nullable))
        if tokens[0].value == "auto":
            # `auto alias = def = this->add(...)`: later options copy from the alias.
            self.aliases[tokens[1].value] = option

    def set_property(self, tokens: list[Tok], env: dict[str, Any]) -> None:
        option = self.current
        if option is None:
            return
        prop = tokens[2].value
        rest = tokens[3:]
        try:
            if prop in ("enum_values", "enum_labels"):
                self.set_enum_list(option, prop, rest, env)
                return
            if not rest or not is_punct(rest[0], "="):
                return
            value = rest[1:]
            if len(value) == 3 and is_punct(value[1], "->") and value[0].value in self.aliases:
                self.copy_from_alias(option, prop, self.aliases[value[0].value], value[2].value)
                return
            if prop in TEXT_PROPS:
                text, context = eval_text(value, env)
                option.props[prop] = text
                if context:
                    option.contexts[prop] = context
            elif prop in NUMBER_PROPS:
                option.props[prop] = eval_number(value, env)
            elif prop == "nullable":
                option.nullable = eval_bool(value)
            elif prop in BOOL_PROPS:
                option.props[prop] = eval_bool(value)
            elif prop in IDENT_PROPS:
                option.props[prop] = render(value).split("::")[-1].strip()
            elif prop == "enum_keys_map":
                match = re.search(r"ConfigOptionEnum\s*<\s*(\w+)\s*>", render(value))
                option.enum_map = match.group(1) if match else None
        except Unresolved as error:
            self.note(option.key, prop, str(error))

    def set_enum_list(
        self, option: OptionDef, prop: str, rest: list[Tok], env: dict[str, Any]
    ) -> None:
        target = option.enum_values if prop == "enum_values" else option.enum_labels
        if not rest:
            return
        if is_punct(rest[0], "."):
            if len(rest) > 1 and rest[1].value in ("push_back", "emplace_back"):
                target.append(eval_text(rest[3:-1], env)[0])
            return
        if not is_punct(rest[0], "="):
            return
        value = rest[1:]
        if len(value) == 3 and is_punct(value[1], "->") and value[0].value in self.aliases:
            self.copy_from_alias(option, prop, self.aliases[value[0].value], value[2].value)
        elif value and is_punct(value[0], "{"):
            target[:] = [eval_text(part, env)[0] for part in split_top(value[1:-1], ",") if part]
        else:
            raise Unresolved("enum list: " + render(value))

    @staticmethod
    def copy_from_alias(option: OptionDef, prop: str, source: OptionDef, source_prop: str) -> None:
        if prop in ("enum_values", "enum_labels") and source_prop == prop:
            setattr(option, prop, list(getattr(source, prop)))
        elif source_prop in source.props:
            option.props[prop] = source.props[source_prop]
            if source_prop in source.contexts:
                option.contexts[prop] = source.contexts[source_prop]


def parse_enum_maps(tokens: list[Tok]) -> dict[str, list[str]]:
    """``s_keys_map_<Enum>`` initialisers: enum name to its keys in value order."""
    maps: dict[str, list[str]] = {}
    for i, tok in enumerate(tokens):
        if tok.kind == "id" and tok.value.startswith("s_keys_map_"):
            j = i + 1
            if is_punct(tokens[j], "="):
                j += 1
            if not is_punct(tokens[j], "{"):
                continue
            close = match_close(tokens, j)
            pairs = []
            for entry in split_top(tokens[j + 1 : close], ","):
                if not entry or not is_punct(entry[0], "{"):
                    continue
                parts = split_top(entry[1:-1], ",")
                if len(parts) == 2 and parts[0] and parts[0][0].kind == "str":
                    pairs.append((decode_c_string(parts[0][0].value), render(parts[1])))
            maps[tok.value[len("s_keys_map_") :]] = [key for key, _ in pairs]
    return maps


def parse_string_set(tokens: list[Tok], name: str) -> list[str]:
    """Strings of ``<name> = { ... };`` or ``<name>{ ... }`` in declaration order."""
    for i, tok in enumerate(tokens):
        if tok.kind == "id" and tok.value == name:
            j = i + 1
            if j < len(tokens) and is_punct(tokens[j], "="):
                j += 1
            if j < len(tokens) and is_punct(tokens[j], "{"):
                close = match_close(tokens, j)
                return [decode_c_string(t.value) for t in tokens[j + 1 : close] if t.kind == "str"]
    raise Unresolved(f"string list {name} not found")


def parse_material_names(source: str) -> list[str]:
    return re.findall(r'^\s*\{"([^"]+)",\s*\d+', source, re.MULTILINE)


def parse_publish_keys(tokens: list[Tok], function: str) -> list[str]:
    """First element of each ``{ "key", "icon" }`` row of a publishable list."""
    for i, tok in enumerate(tokens):
        if tok.kind == "id" and tok.value == function and is_punct(tokens[i + 1], "("):
            j = i
            while not is_punct(tokens[j], "{"):
                j += 1
            close = match_close(tokens, j)
            body = tokens[j + 1 : close]
            for k, inner in enumerate(body):
                if is_punct(inner, "=") and is_punct(body[k + 1], "{"):
                    end = match_close(body, k + 1)
                    rows = split_top(body[k + 2 : end], ",")
                    return [
                        decode_c_string(row[1].value)
                        for row in rows
                        if len(row) > 1 and is_punct(row[0], "{") and row[1].kind == "str"
                    ]
    raise Unresolved(f"{function} not found")


# --------------------------------------------------------------------------
# Preset kind membership
# --------------------------------------------------------------------------


def preset_option_keys(preset_tokens: list[Tok], config_tokens: list[Tok]) -> dict[str, list[str]]:
    """Keys each preset kind stores, as listed by ``Preset.cpp``/``PrintConfig.cpp``."""
    printer = parse_string_set(preset_tokens, "s_Preset_printer_options")
    printer += parse_string_set(preset_tokens, "s_Preset_machine_limits_options")
    printer += parse_string_set(config_tokens, "m_extruder_option_keys")
    return {
        "filament": parse_string_set(preset_tokens, "s_Preset_filament_options"),
        "process": parse_string_set(preset_tokens, "s_Preset_print_options"),
        "machine": printer,
    }


# --------------------------------------------------------------------------
# Tab.cpp: pages, groups and rows
# --------------------------------------------------------------------------


@dataclass
class Row:
    keys: list[tuple[str, str | None]]
    label: str | None = None
    tooltip: str | None = None
    widget: bool = False


@dataclass
class GroupNode:
    title: str
    rows: list[Row] = field(default_factory=list)


@dataclass
class PageNode:
    title: str
    detached: bool
    groups: list[GroupNode] = field(default_factory=list)


@dataclass
class LineVar:
    label: str
    tooltip: str
    items: list[tuple[str, str | None]] = field(default_factory=list)


@dataclass
class OptVar:
    key: str
    overrides: dict[str, Any] = field(default_factory=dict)
    virtual: bool = False


@dataclass
class Helper:
    group_param: int | None
    key_param: int
    captured_group: str | None


OPTION_CALLS = (
    "append_single_option_line",
    "append_option",
    "append_line",
    "create_line_with_widget",
    "append_option_line",
    "get_option",
)

# Tab-side tweaks of an option definition (`option.opt.<name> = ...`).
TAB_OVERRIDE_PROPS = (
    "label",
    "tooltip",
    "is_code",
    "full_width",
    "height",
    "multiline",
    "gui_type",
)


def without_lambda_bodies(tokens: list[Tok]) -> list[Tok]:
    """Statement tokens minus lambda bodies; brace initialisers are kept."""
    out: list[Tok] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if is_punct(tok, "{") and out and is_punct(out[-1], ")"):
            i = match_close(tokens, i) + 1
            out.append(Tok("punct", "{"))
            out.append(Tok("punct", "}"))
            continue
        out.append(tok)
        i += 1
    return out


class TabInterpreter:
    """Replay the editor builders of ``Tab.cpp`` to learn page/group/row order.

    Only the construct shapes the builders use are understood: plain calls,
    ``for`` loops over literal key lists, the row-building lambdas and the
    helper functions. Anything else that mentions an option call is reported
    instead of silently skipped.
    """

    def __init__(
        self,
        tab_tokens: list[Tok],
        options: dict[str, OptionDef],
        publish: dict[str, list[str]],
    ) -> None:
        self.tab_tokens = tab_tokens
        self.options = options
        self.publish = publish
        self.pages: list[PageNode] = []
        self.overrides: dict[str, dict[str, Any]] = {}
        self.virtual: list[str] = []
        self.unresolved: list[dict[str, str]] = []
        self.duplicate_placements: list[str] = []
        self.placed: set[str] = set()
        self.functions = {
            "add_filament_overrides_page": "TabFilament::add_filament_overrides_page",
            "build_kinematics_page": "TabPrinter::build_kinematics_page",
            "build_unregular_pages": "TabPrinter::build_unregular_pages",
        }
        self.depth = 0

    def run(self, entry: str) -> None:
        self.call(entry, {})

    def call(self, qualified: str, env: dict[str, Any]) -> None:
        self.depth += 1
        if self.depth > 8:
            raise Unresolved("function call nesting too deep")
        for node in find_function(self.tab_tokens, qualified):
            self.exec(node, env)
        self.depth -= 1

    def note(self, what: str, detail: str) -> None:
        self.unresolved.append({"what": what, "detail": detail})

    # -- statements --------------------------------------------------------

    def exec(self, node: Any, env: dict[str, Any]) -> None:
        if isinstance(node, Block):
            for child in node.body:
                self.exec(child, env)
        elif isinstance(node, If):
            # Both branches contribute: conditions depend on runtime flavour and
            # connection state, and an option belongs to the schema when any
            # configuration shows it.
            self.exec(node.then, env)
            if node.other is not None:
                self.exec(node.other, env)
        elif isinstance(node, For):
            self.exec_for(node, env)
        elif isinstance(node, Simple):
            self.exec_simple(node.tokens, env)

    def exec_for(self, node: For, env: dict[str, Any]) -> None:
        header = node.header
        if find_top(header, ";") >= 0:
            # `for (auto i = old; i < count; ++i)`: the initial build runs it for
            # the first extruder only.
            self.exec(node.body, {**env, "extruder_idx": 0})
            return
        colon = find_top(header, ":")
        if colon < 0:
            raise Unresolved("for loop: " + render(header))
        variable = header[colon - 1].value
        iterable = header[colon + 1 :]
        try:
            items = self.iterable(iterable, env)
        except Unresolved as error:
            if self.mentions_option_call(node.body):
                self.note("loop", str(error))
            return
        for item in items:
            self.exec(node.body, {**env, variable: item, f"{variable}.key": item})

    def iterable(self, tokens: list[Tok], env: dict[str, Any]) -> list[str]:
        if is_punct(tokens[0], "{"):
            return [eval_text(part, env)[0] for part in split_top(tokens[1:-1], ",") if part]
        if len(tokens) == 1 and isinstance(env.get(tokens[0].value), list):
            return list(env[tokens[0].value])
        if len(tokens) == 3 and is_punct(tokens[1], "(") and tokens[0].value in self.publish:
            return list(self.publish[tokens[0].value])
        raise Unresolved("loop over " + render(tokens))

    def mentions_option_call(self, node: Any) -> bool:
        if isinstance(node, Simple):
            return has_ident(without_lambda_bodies(node.tokens), *OPTION_CALLS)
        if isinstance(node, Block):
            return any(self.mentions_option_call(child) for child in node.body)
        if isinstance(node, For):
            return self.mentions_option_call(node.body)
        if isinstance(node, If):
            return self.mentions_option_call(node.then) or (
                node.other is not None and self.mentions_option_call(node.other)
            )
        return False

    def exec_simple(self, tokens: list[Tok], env: dict[str, Any]) -> None:
        if not tokens:
            return
        try:
            handled = self.dispatch(tokens, env)
        except Unresolved as error:
            self.note(str(error), render(tokens))
            return
        if not handled and has_ident(without_lambda_bodies(tokens), *OPTION_CALLS):
            self.note("unhandled option call", render(tokens))

    def dispatch(self, tokens: list[Tok], env: dict[str, Any]) -> bool:
        top = without_lambda_bodies(tokens)
        name = assignment_target(top)

        if has_ident(top, "add_options_page"):
            _, args = find_call(top, "add_options_page") or (0, [])
            detached = len(args) >= 3 and render(args[2]) == "true"
            page = PageNode(eval_text(args[0], env)[0], detached)
            self.pages.append(page)
            if name:
                env[name] = page
            return True

        if has_ident(top, "new_optgroup"):
            index, args = find_call(top, "new_optgroup") or (0, [])
            page = env.get(top[index - 2].value)
            if not isinstance(page, PageNode):
                raise Unresolved("optgroup of unknown page")
            group = GroupNode(eval_text(args[0], env)[0] if args else "")
            page.groups.append(group)
            if name:
                env[name] = group
            return True

        if self.helper_call(top, env):
            return True

        if name and find_open(top, "[") >= 0 and has_ident(tokens, "create_single_option_line"):
            self.define_lambda(top, env)
            return True

        if has_ident(top[:1], "Option") and len(top) > 3 and is_punct(top[2], "("):
            args = split_top(top[3:-1], ",")
            if len(args) == 2:
                env[top[1].value] = OptVar(eval_text(args[1], env)[0], virtual=True)
                return True
        if has_ident(top, "Option") and name and find_call(top, "Option"):
            _, args = find_call(top, "Option") or (0, [])
            if len(args) == 2:
                env[name] = OptVar(eval_text(args[1], env)[0], virtual=True)
                return True

        if (
            has_ident(top, "get_option")
            and name
            and not has_ident(top, "append_option", "append_single_option_line", "Line")
        ):
            _, args = find_call(top, "get_option") or (0, [])
            env[name] = OptVar(eval_text(args[0], env)[0])
            return True

        if (
            len(top) > 6
            and is_punct(top[1], ".")
            and top[2].value == "opt"
            and is_punct(top[3], ".")
        ):
            var = env.get(top[0].value)
            prop = top[4].value
            if isinstance(var, OptVar) and prop in TAB_OVERRIDE_PROPS and is_punct(top[5], "="):
                value = top[6:]
                if prop in ("label", "tooltip"):
                    var.overrides[prop] = eval_text(value, env)[0]
                elif prop == "height":
                    var.overrides[prop] = eval_number(value, env)
                elif prop == "gui_type":
                    var.overrides[prop] = render(value).split("::")[-1].strip()
                else:
                    var.overrides[prop] = eval_bool(value)
                return True
            return False

        if self.is_line_declaration(top, env):
            self.declare_line(top, env)
            return True

        call = find_call(top, "append_option")
        if call is not None:
            index, args = call
            line = env.get(top[index - 2].value)
            if not isinstance(line, LineVar):
                raise Unresolved("append_option on unknown line")
            line.items.append(self.keyed(self.option_ref(args[0], env)))
            return True

        call = find_call(top, "append_line")
        if call is not None:
            index, args = call
            group = env.get(top[index - 2].value)
            line = env.get(render(args[0]))
            if not isinstance(group, GroupNode) or not isinstance(line, LineVar):
                raise Unresolved("append_line of unknown group or line")
            self.emit(group, Row(list(line.items), line.label or None, line.tooltip or None))
            return True

        call = find_call(top, "append_single_option_line")
        if call is not None:
            index, args = call
            group = env.get(top[index - 2].value)
            if not isinstance(group, GroupNode):
                raise Unresolved("append_single_option_line on unknown group")
            self.emit(group, Row([self.keyed(self.option_ref(args[0], env))]))
            return True

        call = find_call(top, "create_line_with_widget")
        if call is not None:
            _, args = call
            group = env.get(args[0][0].value)
            if not isinstance(group, GroupNode):
                raise Unresolved("widget line on unknown group")
            self.emit(group, Row([(eval_text(args[1], env)[0], None)], widget=True))
            return True

        call = find_call(top, "append_option_line")
        if call is not None:
            _, args = call
            group = env.get(render(args[0]))
            if not isinstance(group, GroupNode):
                raise Unresolved("append_option_line on unknown group")
            self.emit(group, Row([(eval_text(args[1], env)[0], None)]))
            return True

        if has_ident(top, "vector") and find_open(top, "{") > 1:
            brace = find_open(top, "{")
            items = split_top(top[brace + 1 : match_close(top, brace)], ",")
            env[top[brace - 1].value] = [eval_text(item, env)[0] for item in items if item]
            return True

        self.maybe_call_function(top, env)
        if name and not has_ident(top, *self.functions):
            self.bind_value(top, name, env)
        return False

    # -- helpers -----------------------------------------------------------

    def option_ref(self, tokens: list[Tok], env: dict[str, Any]) -> OptVar:
        if len(tokens) == 1 and isinstance(env.get(tokens[0].value), OptVar):
            return env[tokens[0].value]
        call = find_call(tokens, "get_option")
        if call is not None:
            return OptVar(eval_text(call[1][0], env)[0])
        return OptVar(eval_text(tokens, env)[0])

    def keyed(self, ref: OptVar) -> tuple[str, str | None]:
        if ref.virtual or ref.key not in self.options:
            self.virtual.append(ref.key)
        extra = {k: v for k, v in ref.overrides.items() if k != "label"}
        if extra:
            self.overrides.setdefault(ref.key, {}).update(extra)
        return ref.key, ref.overrides.get("label")

    def emit(self, group: GroupNode, row: Row) -> None:
        row.keys = [(key, label) for key, label in row.keys if key in self.options]
        if not row.keys:
            return
        for key, _ in row.keys:
            if key in self.placed:
                self.duplicate_placements.append(key)
            self.placed.add(key)
        group.rows.append(row)

    def is_line_declaration(self, top: list[Tok], env: dict[str, Any]) -> bool:
        if has_ident(top[:3], "Line"):
            return True
        if has_ident(top, "Line") and find_open(top, "{") >= 0 and assignment_target(top):
            return True
        return (
            len(top) > 2
            and top[0].kind == "id"
            and is_punct(top[1], "=")
            and is_punct(top[2], "{")
            and isinstance(env.get(top[0].value), LineVar)
        )

    def declare_line(self, top: list[Tok], env: dict[str, Any]) -> None:
        brace = find_open(top, "{")
        if brace < 0:
            raise Unresolved("line without initialiser")
        name = assignment_target(top[:brace]) or top[brace - 1].value
        args = split_top(top[brace + 1 : match_close(top, brace)], ",")
        label = eval_text(args[0], env)[0] if args and args[0] else ""
        tooltip = ""
        if len(args) > 1 and args[1]:
            call = find_call(args[1], "get_option")
            if call is not None:
                source = self.options.get(eval_text(call[1][0], env)[0])
                tooltip = source.props.get("tooltip", "") if source else ""
            else:
                tooltip = eval_text(args[1], env)[0]
        env[name] = LineVar(label, tooltip)

    def define_lambda(self, top: list[Tok], env: dict[str, Any]) -> None:
        name = assignment_target(top)
        bracket = find_open(top, "[")
        captures_end = match_close(top, bracket)
        captures = [t.value for t in top[bracket + 1 : captures_end] if t.kind == "id"]
        params = split_top(top[captures_end + 2 : match_close(top, captures_end + 1)], ",")
        group_param = key_param = None
        for index, param in enumerate(params):
            if has_ident(param, "ConfigOptionsGroupShp"):
                group_param = index
            elif has_ident(param, "string"):
                key_param = index
        if name is None or key_param is None:
            raise Unresolved("row helper lambda without key parameter")
        captured = next((c for c in captures if isinstance(env.get(c), GroupNode)), None)
        env[f"<helper>{name}"] = Helper(group_param, key_param, captured)

    def helper_call(self, top: list[Tok], env: dict[str, Any]) -> bool:
        if len(top) < 3 or top[0].kind != "id" or not is_punct(top[1], "("):
            return False
        helper = env.get(f"<helper>{top[0].value}")
        if not isinstance(helper, Helper):
            return False
        args = split_top(top[2:-1], ",")
        if helper.group_param is not None:
            group = env.get(render(args[helper.group_param]))
        else:
            group = env.get(helper.captured_group or "")
        if not isinstance(group, GroupNode):
            raise Unresolved("helper call on unknown group")
        self.emit(group, Row([(eval_text(args[helper.key_param], env)[0], None)]))
        return True

    def maybe_call_function(self, top: list[Tok], env: dict[str, Any]) -> None:
        for index, tok in enumerate(top[:-1]):
            if tok.kind == "id" and tok.value in self.functions and is_punct(top[index + 1], "("):
                args = split_top(top[index + 2 : match_close(top, index + 1)], ",")
                inner: dict[str, Any] = {}
                if tok.value == "build_unregular_pages" and args and render(args[0]) == "true":
                    inner["from_initial_build"] = True
                self.call(self.functions[tok.value], inner)
                return

    def bind_value(self, top: list[Tok], name: str, env: dict[str, Any]) -> None:
        value = top[find_top(top, "=") + 1 :]
        if not value:
            return
        try:
            if is_punct(value[0], "{") and not has_ident(top, "Option", "Line"):
                env[name] = [eval_text(p, env)[0] for p in split_top(value[1:-1], ",") if p]
            elif any(t.kind == "str" for t in value):
                env[name] = eval_text(value, env)[0]
            elif len(value) == 1 and value[0].kind == "num":
                env[name] = eval_number(value)
        except Unresolved:
            return

    # -- results -----------------------------------------------------------

    def ordered_pages(self) -> list[PageNode]:
        """Pages in tab order, resolving the detached machine pages."""
        attached = [p for p in self.pages if not p.detached]
        detached = [p for p in self.pages if p.detached]
        if not detached:
            return attached
        by_title = {p.title: p for p in [*attached, *detached]}
        if set(by_title) != set(MACHINE_PAGE_ORDER):
            self.note("machine page order", "built pages: " + ", ".join(by_title))
            return [*attached, *detached]
        return [by_title[title] for title in MACHINE_PAGE_ORDER]


# --------------------------------------------------------------------------
# Translations
# --------------------------------------------------------------------------


class Catalog:
    """Non-fuzzy, translated entries of one gettext ``.po`` file."""

    def __init__(self, text: str) -> None:
        self.entries: dict[tuple[str | None, str], str] = {}
        self._parse(text)

    def _parse(self, text: str) -> None:
        block: list[str] = []
        for line in text.split("\n") + [""]:
            if line.strip():
                block.append(line)
                continue
            if block:
                self._entry(block)
                block = []

    def _entry(self, lines: list[str]) -> None:
        fuzzy = any(line.startswith("#,") and "fuzzy" in line for line in lines)
        fields: dict[str, str] = {}
        current: str | None = None
        for line in lines:
            if line.startswith("#"):
                continue
            match = re.match(
                r"(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+(\".*\")\s*$", line
            )
            if match:
                current = match.group(1)
                fields[current] = decode_c_string(match.group(2))
            elif current and line.startswith('"'):
                fields[current] += decode_c_string(line)
        msgid, msgstr = fields.get("msgid"), fields.get("msgstr")
        if fuzzy or not msgid or not msgstr or "msgid_plural" in fields:
            return
        self.entries[(fields.get("msgctxt"), msgid)] = msgstr

    def get(self, text: str, context: str | None = None) -> str | None:
        found = self.entries.get((context, text))
        if found is None and context is not None:
            found = self.entries.get((None, text))
        if found is None or found == text:
            return None
        return found


class Translator:
    def __init__(self, catalogs: dict[str, Catalog]) -> None:
        self.catalogs = catalogs

    def texts(
        self, source: dict[str, tuple[str, str | None] | list[str]]
    ) -> dict[str, dict[str, Any]]:
        """Translations of named strings, per language; untranslated names are absent."""
        result: dict[str, dict[str, Any]] = {}
        for lang, catalog in self.catalogs.items():
            fields: dict[str, Any] = {}
            for name, value in source.items():
                if isinstance(value, list):
                    translated = [catalog.get(item) or item for item in value]
                    if translated != value:
                        fields[name] = translated
                else:
                    text, context = value
                    found = catalog.get(text, context)
                    if found is not None:
                        fields[name] = found
            if fields:
                result[lang] = fields
        return result

    def title(self, text: str) -> dict[str, str]:
        return {lang: found for lang, c in self.catalogs.items() if (found := c.get(text))}


# --------------------------------------------------------------------------
# Schema assembly
# --------------------------------------------------------------------------


@dataclass
class Context:
    options: dict[str, OptionDef]
    enum_maps: dict[str, list[str]]
    variant_keys: set[str]
    silent_keys: set[str]
    translator: Translator


def option_entry(
    option: OptionDef,
    tab_overrides: dict[str, Any],
    context: Context,
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    props = {**option.props, **{k: v for k, v in tab_overrides.items() if k in TAB_OVERRIDE_PROPS}}
    base = ALL_TYPES[option.cpp_type]
    vector = option.cpp_type in VECTOR_BASE and option.cpp_type != "coPoints"
    multiline = bool(props.get("multiline"))
    code = bool(props.get("is_code"))
    kind = base
    if base == "string" and code:
        kind = "gcode"
    elif base == "string" and multiline:
        kind = "multiline"

    entry: dict[str, Any] = {"type": kind}
    if vector:
        entry["vector"] = True
    if option.nullable:
        entry["nullable"] = True
    for name, prop in (
        ("label", "label"),
        ("full_label", "full_label"),
        ("tooltip", "tooltip"),
        ("unit", "sidetext"),
    ):
        if props.get(prop):
            entry[name] = props[prop]
    if "full_label" in entry and entry["full_label"] == entry.get("label"):
        del entry["full_label"]
    mode = props.get("mode", "comSimple")
    entry["mode"] = MODE_NAMES[mode]
    if mode == "comDevelop":
        entry["develop"] = True
    for name in ("min", "max"):
        if name in props:
            entry[name] = props[name]

    values = list(option.enum_values)
    if not values and base == "enum" and option.enum_map:
        values = list(context.enum_maps.get(option.enum_map, []))
        if values:
            issues.append({"key": option.key, "what": "enum values taken from the C++ enum map"})
    if base == "enum" and not values:
        issues.append({"key": option.key, "what": "enum without values"})
    if values:
        entry["values"] = values
        if option.enum_labels:
            if len(option.enum_labels) == len(values):
                entry["labels"] = list(option.enum_labels)
            else:
                issues.append({"key": option.key, "what": "enum labels do not match values"})
        if props.get("gui_type") in ("f_enum_open", "i_enum_open"):
            entry["open"] = True
    if props.get("ratio_over"):
        entry["ratio_over"] = props["ratio_over"]
    if props.get("gui_type"):
        entry["gui"] = props["gui_type"]
    for name in ("full_width", "readonly"):
        if props.get(name):
            entry[name] = True
    if code:
        entry["code"] = True
    if "height" in props:
        entry["height"] = props["height"]
    if option.key in context.variant_keys:
        entry["variant"] = True
    if option.key in context.silent_keys:
        entry["silent_pair"] = True

    sources: dict[str, Any] = {}
    for name, prop in (
        ("label", "label"),
        ("full_label", "full_label"),
        ("tooltip", "tooltip"),
        ("unit", "sidetext"),
    ):
        if name in entry:
            sources[name] = (props[prop], option.contexts.get(prop))
    if "labels" in entry:
        sources["labels"] = entry["labels"]
    translated = context.translator.texts(sources)
    if translated:
        entry["tr"] = translated
    return entry


def row_entry(row: Row, translator: Translator) -> Any:
    keys: list[Any] = []
    for key, label in row.keys:
        if label is None:
            keys.append(key)
            continue
        item: dict[str, Any] = {"key": key, "label": label}
        titles = translator.title(label)
        if titles:
            item["tr"] = titles
        keys.append(item)
    if len(keys) == 1 and isinstance(keys[0], str) and not (row.label or row.tooltip or row.widget):
        return keys[0]
    entry: dict[str, Any] = {"keys": keys}
    if row.label:
        entry["label"] = row.label
    if row.tooltip:
        entry["tooltip"] = row.tooltip
    if row.widget:
        entry["widget"] = True
    sources: dict[str, Any] = {}
    if row.label:
        sources["label"] = (row.label, None)
    if row.tooltip:
        sources["tooltip"] = (row.tooltip, None)
    translated = translator.texts(sources)
    if translated:
        entry["tr"] = translated
    return entry


def page_entries(pages: list[PageNode], translator: Translator) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in pages:
        groups: list[dict[str, Any]] = []
        for group in page.groups:
            if not group.rows:
                continue
            node: dict[str, Any] = {"title": group.title}
            titles = translator.title(group.title) if group.title else {}
            if titles:
                node["tr"] = titles
            node["rows"] = [row_entry(row, translator) for row in group.rows]
            groups.append(node)
        if not groups:
            continue
        node = {"title": page.title}
        titles = translator.title(page.title)
        if titles:
            node["tr"] = titles
        node["groups"] = groups
        out.append(node)
    return out


def build_documents(upstream: Upstream) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    config_tokens = tokenize(upstream.read(SRC_PRINT_CONFIG))
    preset_tokens = tokenize(upstream.read(SRC_PRESET))
    tab_tokens = tokenize(upstream.read(SRC_TAB))
    publish_tokens = tokenize(upstream.read(SRC_PUBLISH))
    enum_maps = parse_enum_maps(config_tokens)

    reader = PrintConfigReader(
        config_tokens, parse_material_names(upstream.read(SRC_MATERIAL)), enum_maps
    )
    reader.run()
    listed = preset_option_keys(preset_tokens, config_tokens)
    publish = {
        "publishable_printer_retraction_options": parse_publish_keys(
            publish_tokens, "publishable_printer_retraction_options"
        ),
        "publishable_printer_z_hop_options": parse_publish_keys(
            publish_tokens, "publishable_printer_z_hop_options"
        ),
    }

    translator = Translator({lang: Catalog(upstream.read(path)) for lang, path in PO_FILES.items()})
    variant_keys: set[str] = set()
    for name in (
        "print_options_with_variant",
        "filament_options_with_variant",
        "printer_options_with_variant_1",
        "printer_extruder_options",
    ):
        variant_keys.update(parse_string_set(config_tokens, name))
    context = Context(
        reader.options,
        enum_maps,
        variant_keys,
        set(parse_string_set(config_tokens, "printer_options_with_variant_2")),
        translator,
    )

    builders = {
        "filament": "TabFilament::build",
        "process": "TabPrint::build",
        "machine": "TabPrinter::build_fff",
    }
    source = {
        "repository": REPOSITORY,
        "commit": upstream.commit,
        "committed_at": upstream.committed_at,
        "files": SOURCE_FILES,
        "generator": "scripts/generate_orca_preset_schema.py",
    }
    documents: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {"redefined": sorted(set(reader.redefined))}
    for kind in KINDS:
        tab = TabInterpreter(tab_tokens, reader.options, publish)
        tab.run(builders[kind])
        pages = tab.ordered_pages()

        placed = {
            key
            for page in pages
            for group in page.groups
            for row in group.rows
            for key, _ in row.keys
        }
        defined_listed = [k for k in listed[kind] if k in reader.options]
        keys = sorted(set(defined_listed) | placed)
        issues: list[dict[str, str]] = []
        options = {
            key: option_entry(reader.options[key], tab.overrides.get(key, {}), context, issues)
            for key in keys
        }
        documents[kind] = {
            "format": SCHEMA_FORMAT,
            "version": SCHEMA_VERSION,
            "kind": kind,
            "source": source,
            "pages": page_entries(pages, translator),
            "options": options,
            "diagnostics": {
                "listed_without_definition": sorted(
                    {k for k in listed[kind] if k not in reader.options}
                ),
                "placed_but_not_listed": sorted(placed - set(listed[kind])),
                "unplaced": sorted(set(options) - placed),
                "placed_twice": sorted(set(tab.duplicate_placements)),
                "ui_only_keys": sorted(set(tab.virtual)),
                "unresolved": [*reader.unresolved, *tab.unresolved, *issues],
            },
        }
        summary[kind] = {
            "listed": len(set(listed[kind])),
            "options": len(options),
            "placed": len(placed & set(options)),
            "with_ru": sum(1 for o in options.values() if "ru" in o.get("tr", {})),
            "with_zh": sum(1 for o in options.values() if "zh" in o.get("tr", {})),
        }
    return documents, summary


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def format_document(document: dict[str, Any]) -> str:
    """One line per page header, group and option so regeneration diffs stay readable."""
    lines = ["{"]
    for name in ("format", "version", "kind", "source"):
        lines.append(f'"{name}": {_json(document[name])},')
    lines.append('"pages": [')
    page_blocks = []
    for page in document["pages"]:
        head = {k: v for k, v in page.items() if k != "groups"}
        block = [f'{_json(head)[:-1]}, "groups": [']
        block.append(",\n".join(_json(group) for group in page["groups"]))
        block.append("]}")
        page_blocks.append("\n".join(block))
    lines.append(",\n".join(page_blocks))
    lines.append("],")
    lines.append('"options": {')
    lines.append(
        ",\n".join(f"{_json(key)}: {_json(entry)}" for key, entry in document["options"].items())
    )
    lines.append("},")
    lines.append(f'"diagnostics": {_json(document["diagnostics"])}')
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--upstream", type=Path, default=DEFAULT_UPSTREAM, help="OrcaSlicer git checkout"
    )
    parser.add_argument("--ref", default=DEFAULT_REF, help="upstream revision to read")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--check", action="store_true", help="fail when committed files differ")
    args = parser.parse_args(argv)

    upstream = Upstream(args.upstream, args.ref)
    documents, summary = build_documents(upstream)
    rendered = {
        OUTPUT_NAME.format(kind=kind): format_document(document)
        for kind, document in documents.items()
    }
    print(f"upstream {upstream.commit} ({upstream.committed_at})")
    for kind in KINDS:
        print(f"  {kind}: {summary[kind]}")
    unresolved = sum(len(d["diagnostics"]["unresolved"]) for d in documents.values())
    print(f"  unresolved entries: {unresolved}")

    if args.check:
        stale = [
            name
            for name, text in rendered.items()
            if not (args.output_dir / name).is_file()
            or (args.output_dir / name).read_text(encoding="utf-8") != text
        ]
        if stale:
            print("out of date: " + ", ".join(stale), file=sys.stderr)
            return 1
        print("committed schema matches upstream")
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in rendered.items():
        (args.output_dir / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.output_dir / name} ({len(text.encode('utf-8')) // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
