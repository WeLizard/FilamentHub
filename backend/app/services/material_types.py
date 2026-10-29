"""Base polymer and subtype of a filament's material type.

``Filament.material_type`` keeps the manufacturer's spelling ("PA6-CF",
"PLA Plus", "PLA SILK") because the Orca plugin and Spoolman-compatible
clients read it verbatim. The catalog groups by the base polymer and
identifies the specific material by a subtype from the reference below.

Additives (CF, GF), effects (Silk, Matte) and property claims (ESD, FR) are
not subtypes: they are stripped before matching. Nothing is guessed: a type
whose grade is not stated ("Nylon", "PLA Basic") gets only its base, and a
type naming no known polymer gets neither.

The migration ``material_base_subtype`` seeds this reference into
``material_properties``; this module stays the source for resolution. The
derived filament columns are stored, so a change that resolves existing types
differently needs a data migration that re-derives them.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialTypeEntry:
    code: str
    base: str
    aliases: tuple[str, ...] = ()

    @property
    def is_base(self) -> bool:
        return self.code == self.base


def _entry(code: str, base: str | None = None, *aliases: str) -> MaterialTypeEntry:
    return MaterialTypeEntry(code=code, base=base or code, aliases=aliases)


# Base = polymer. Blends take the first-named polymer as base, as ISO 1043-1
# writes the main component first. PCTG, PET and CPE are separate polymers
# from PETG; CPE is a proprietary copolyester whose polymer is not disclosed.
MATERIAL_TYPES: tuple[MaterialTypeEntry, ...] = (
    _entry("PLA", None, "POLYLACTIC ACID"),
    _entry("PLA+", "PLA", "PLA PLUS"),
    _entry("PLA HS", "PLA", "HS PLA", "PLA HIGH SPEED", "HIGH SPEED PLA"),
    _entry("LW-PLA", "PLA", "PLA LW", "LIGHTWEIGHT PLA", "PLA LIGHTWEIGHT"),
    _entry("PLA/PHB", "PLA"),
    _entry("PETG"),
    _entry("PETG+", "PETG", "PETG PLUS"),
    _entry("PCTG"),
    _entry("PET", None, "RPET"),
    _entry("CPE", None, "COPOLYESTER"),
    _entry("ABS"),
    _entry("ABS+", "ABS", "ABS PLUS"),
    _entry("ABS HF", "ABS", "HF ABS", "ABS HIGH FLOW", "HIGH FLOW ABS"),
    _entry("ABS/PC", "ABS", "ABS+PC"),
    _entry("ABS/PA", "ABS", "ABS+PA"),
    _entry("ABS/PBT", "ABS", "ABS+PBT"),
    _entry("MABS"),
    _entry("ASA"),
    _entry("ASA+", "ASA", "ASA PLUS"),
    _entry("HIPS"),
    _entry("SAN"),
    _entry("PC", None, "POLYCARBONATE"),
    _entry("PC/ABS", "PC", "PC+ABS"),
    _entry("PC/PBT", "PC", "PC+PBT"),
    _entry("PA", None, "NYLON", "POLYAMIDE"),
    _entry("PA6", "PA", "NYLON 6", "POLYAMIDE 6"),
    _entry("PA11", "PA", "NYLON 11", "POLYAMIDE 11"),
    _entry("PA12", "PA", "NYLON 12", "POLYAMIDE 12"),
    _entry("PA66", "PA", "NYLON 66", "POLYAMIDE 66", "PA6/6", "NYLON 6/6"),
    _entry("PPA", "PA", "POLYPHTHALAMIDE"),
    _entry("PAHT", "PA", "PA HT"),
    _entry("TPU"),
    _entry("TPE"),
    _entry("TPC"),
    _entry("SBS"),
    _entry("SEBS"),
    _entry("PEBA"),
    _entry("PP", None, "POLYPROPYLENE"),
    _entry("PE", None, "POLYETHYLENE"),
    _entry("HDPE", "PE"),
    _entry("PBT"),
    _entry("PBT/PET", "PBT", "PBT+PET"),
    _entry("PVA"),
    _entry("BVOH"),
    _entry("PVB"),
    _entry("PEEK"),
    _entry("PEKK"),
    _entry("PEI"),
    _entry("PPS"),
    _entry("PPSU"),
    _entry("PSU"),
    _entry("PPO"),
    _entry("POM"),
    _entry("PMMA"),
    _entry("PVDF"),
    _entry("PVC"),
    _entry("PCL"),
    _entry("POK"),
    _entry("PHA"),
    _entry("EVA"),
)

BY_CODE: dict[str, MaterialTypeEntry] = {entry.code: entry for entry in MATERIAL_TYPES}
BASE_CODES: tuple[str, ...] = tuple(entry.code for entry in MATERIAL_TYPES if entry.is_base)

# Wiki articles about a material. A subtype without its own article links to
# its base; the site shows the link only when the article is published.
WIKI_ARTICLES: dict[str, str] = {
    "PLA": "pla-properties",
    "PETG": "petg-properties",
    "ABS": "abs-properties",
    "ASA": "asa-properties",
    "PA": "nylon-properties",
    "PC": "pc-properties",
    "PC/ABS": "pc-abs-properties",
    "TPU": "tpu-properties",
    "TPE": "tpu-properties",
    "TPC": "tpc-properties",
}

# Words that describe an additive, an effect or a claim rather than the
# material itself. Matched as whole tokens after upper-casing.
_MODIFIER_TOKENS = frozenset(
    {
        "CF",
        "GF",
        "CARBON",
        "GLASS",
        "FIBER",
        "FIBRE",
        "ARAMID",
        "KEVLAR",
        "BASALT",
        "CNT",
        "GRAPHENE",
        "ESD",
        "FR",
        "FLAME",
        "RETARDANT",
        "WOOD",
        "CORK",
        "BAMBOO",
        "METAL",
        "IRON",
        "STEEL",
        "COPPER",
        "BRASS",
        "BRONZE",
        "ALUMINIUM",
        "ALUMINUM",
        "MARBLE",
        "STONE",
        "SILK",
        "ШЕЛК",
        "GLOW",
        "MATTE",
        "MATT",
        "GLITTER",
        "SPARKLE",
        "METALLIC",
        "GALAXY",
        "RAINBOW",
        "TRANSLUCENT",
        "TRANSPARENT",
        "CLEAR",
        "RECYCLED",
    }
)
_FILLED_TOKEN_RE = re.compile(r"^(?:CF|GF)\d+%?$")
_TOKEN_RE = re.compile(r"[0-9A-ZА-Я.+%]+")
_POLYAMIDE_RE = re.compile(r"PA\d{1,4}[A-Z]?")
_BLEND_RE = re.compile(r"[A-Z0-9]\s*[/+]\s*[A-Z]")


def _tokens_text(value: str | None) -> str:
    return unicodedata.normalize("NFKC", value or "").upper().replace("Ё", "Е")


def _tokens(value: str) -> list[str]:
    return _TOKEN_RE.findall(_tokens_text(value))


def _key(tokens: list[str]) -> str:
    return "".join(tokens).replace(".", "")


def _is_modifier(token: str) -> bool:
    return token in _MODIFIER_TOKENS or bool(_FILLED_TOKEN_RE.match(token))


# "Carbon fiber" and "CF" are one additive for duplicate checks.
_MODIFIER_SPELLINGS = {"CARBON": "CF", "GLASS": "GF", "FIBER": "", "FIBRE": ""}


def _split_joined(tokens: list[str]) -> list[str]:
    """ "PA6+CF" is two words; "PLA+", "PLA+SILK" and "ABS+PC" keep the known name."""
    result: list[str] = []
    for token in tokens:
        if "+" not in token or _key([token]) in _ALIASES:
            result.append(token)
            continue
        plus = token.find("+")
        while plus != -1 and _key([token[: plus + 1]]) not in _ALIASES:
            plus = token.find("+", plus + 1)
        if plus != -1:
            result.append(token[: plus + 1])
            token = token[plus + 1 :]
        result.extend(part for part in token.split("+") if part)
        if token.endswith("+"):
            result.append("+")
    return result


def _build_alias_index() -> dict[str, MaterialTypeEntry]:
    index: dict[str, MaterialTypeEntry] = {}
    for entry in MATERIAL_TYPES:
        for spelling in (entry.code, *entry.aliases):
            key = _key(_tokens(spelling))
            existing = index.get(key)
            if existing is not None and existing != entry:
                raise ValueError(f"Material type alias {spelling!r} is ambiguous")
            index[key] = entry
    return index


_ALIASES = _build_alias_index()


@dataclass(frozen=True)
class MaterialTypeResolution:
    base: str | None
    subtype: str | None
    modifiers: tuple[str, ...] = ()


def resolve_material_type(value: str | None) -> MaterialTypeResolution:
    """Base polymer and reference subtype named by a free-text material type."""
    tokens = _tokens(value or "")
    if not tokens:
        return MaterialTypeResolution(None, None)
    exact = _ALIASES.get(_key(tokens))
    if exact is not None:
        return MaterialTypeResolution(exact.base, exact.code)

    tokens = _split_joined(tokens)
    material = [token for token in tokens if not _is_modifier(token)]
    modifiers = tuple(
        sorted(
            {
                _MODIFIER_SPELLINGS.get(token, token.rstrip("%"))
                for token in tokens
                if _is_modifier(token)
            }
            - {""}
        )
    )
    if not material:
        return MaterialTypeResolution(None, None, modifiers)
    stripped = _ALIASES.get(_key(material))
    if stripped is not None:
        return MaterialTypeResolution(stripped.base, stripped.code, modifiers)

    # Free text such as "PLA Basic" or "PA6/66": the single named polymer gives
    # the base; a subtype only when every word is accounted for, because the
    # rest may change the grade (PA6/66 is a copolymer, not PA6).
    matches: list[MaterialTypeEntry] = []
    unmatched = 0
    index = 0
    while index < len(material):
        pair = (
            _ALIASES.get(_key(material[index : index + 2])) if index + 1 < len(material) else None
        )
        single = _ALIASES.get(_key(material[index : index + 1]))
        if pair is not None and (single is None or single.is_base and not pair.is_base):
            matches.append(pair)
            index += 2
            continue
        if single is not None:
            matches.append(single)
        else:
            unmatched += 1
            # ISO 1043 polyamide designations (PA612, PA6T): family known, grade
            # not in the reference.
            if _POLYAMIDE_RE.fullmatch(material[index]):
                matches.append(BY_CODE["PA"])
        index += 1
    bases = {entry.base for entry in matches}
    if len(bases) > 1 and _BLEND_RE.search(_tokens_text(value)):
        # A blend ("PLA/PETG") takes its first-named polymer, as ISO 1043-1 orders it.
        return MaterialTypeResolution(matches[0].base, None, modifiers)
    if len(bases) != 1:
        return MaterialTypeResolution(None, None, modifiers)
    base = bases.pop()
    if unmatched:
        return MaterialTypeResolution(base, None, modifiers)
    grades = {entry.code for entry in matches if not entry.is_base}
    if len(grades) > 1:
        return MaterialTypeResolution(base, None, modifiers)
    return MaterialTypeResolution(base, grades.pop() if grades else base, modifiers)


def material_type_identity_key(value: str | None) -> str:
    """Spelling-insensitive identity of a material type for duplicate checks.

    "PLA Plus" and "PLA+" are one material; "PA6" and "PA12" never are, and
    "PA6" and "PA6-CF" stay different products.
    """
    resolution = resolve_material_type(value)
    if resolution.subtype is None:
        return _key(_tokens(value or "")) or (value or "").strip().casefold()
    return "|".join((resolution.subtype, *resolution.modifiers))


def material_wiki_slug(subtype: str | None, base: str | None) -> str | None:
    return WIKI_ARTICLES.get(subtype or "") or WIKI_ARTICLES.get(base or "")


def material_type_seed_rows() -> list[dict[str, object]]:
    return [
        {
            "material_type": entry.code,
            "display_name": entry.code,
            "base_type": entry.base,
            "aliases": list(entry.aliases),
            "wiki_article_slug": WIKI_ARTICLES.get(entry.code),
        }
        for entry in MATERIAL_TYPES
    ]
