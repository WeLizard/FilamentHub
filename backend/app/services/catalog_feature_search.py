"""Resolve translated catalog feature labels to their stored canonical codes."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.catalog_color_groups import (
    MULTICOLOR_COLOR_TYPES,
    FilamentColorGroup,
    resolve_color_group_aliases,
)
from app.services.filament_features import (
    ADDITIVES,
    COLOR_TYPES,
    EFFECTS,
    PROPERTY_CLAIMS,
    spelling_key,
)


@dataclass(frozen=True)
class CatalogFeatureCodes:
    effects: tuple[str, ...] = ()
    additives: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    color_groups: tuple[FilamentColorGroup, ...] = ()
    color_types: tuple[str, ...] = ()
    transparent: bool = False


def _normalize(value: str) -> str:
    return spelling_key(value)


def _searchable(spellings: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    return {
        code: tuple(dict.fromkeys(_normalize(label) for label in (code, *labels)))
        for code, labels in spellings.items()
        if code != "none" and not code.startswith("pattern")
    }


# Search aliases are the input spellings of each code (filament_features), so a
# visible label in any interface language or a common abbreviation finds the
# stored code.
_NORMALIZED_LABELS = {
    "effects": _searchable(EFFECTS),
    "additives": _searchable(ADDITIVES),
    "claims": _searchable(PROPERTY_CLAIMS),
}

_TRANSPARENCY_LABELS = tuple(
    _normalize(label)
    for label in ("transparent", "translucent", "прозрачный", "полупрозрачный", "透明", "半透明")
)
_MULTICOLOR_TYPES = list(MULTICOLOR_COLOR_TYPES)
_MULTICOLOR_LABELS = tuple(
    _normalize(label)
    for label in (
        "multicolor",
        "multicolour",
        "multi color",
        "multi colour",
        "многоцветный",
        "多色",
    )
)
_NORMALIZED_COLOR_TYPE_LABELS = {
    color_type: labels
    for color_type, labels in _searchable(COLOR_TYPES).items()
    if color_type in _MULTICOLOR_TYPES
}
# Abbreviations ("cf", "fr") match only as whole words: as substrings they
# would turn "fresh" into a flame-retardant search.
_SHORT_LABEL = 3


def _matches(needle: str, label: str) -> bool:
    if len(label) <= _SHORT_LABEL:
        return label in needle.split()
    return label in needle or (len(needle) >= 3 and needle in label)


def resolve_catalog_feature_codes(search: str) -> CatalogFeatureCodes:
    """Return every canonical feature whose visible label matches the query."""
    needle = _normalize(search)
    if not needle:
        return CatalogFeatureCodes()

    matched: dict[str, list[str]] = {"effects": [], "additives": [], "claims": []}
    for kind, codes in _NORMALIZED_LABELS.items():
        for code, labels in codes.items():
            if any(_matches(needle, label) for label in labels):
                matched[kind].append(code)

    color_types = [
        color_type
        for color_type, labels in _NORMALIZED_COLOR_TYPE_LABELS.items()
        if any(_matches(needle, label) for label in labels)
    ]
    if any(_matches(needle, label) for label in _MULTICOLOR_LABELS):
        color_types = list(_MULTICOLOR_TYPES)

    return CatalogFeatureCodes(
        effects=tuple(matched["effects"]),
        additives=tuple(matched["additives"]),
        claims=tuple(matched["claims"]),
        color_groups=resolve_color_group_aliases(search),
        color_types=tuple(color_types),
        transparent=any(_matches(needle, label) for label in _TRANSPARENCY_LABELS),
    )
