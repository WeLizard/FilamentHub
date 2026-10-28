"""Whether two filaments of one brand are probably the same product.

Names are written differently in every language and by every contributor
("PLA Matte Grey" / "PLA Matte" + colour "серый"), so the comparison works on
tokens: the product words that remain after the brand and the colour are
removed must match, and the colours must match.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.services.catalog_color_groups import color_group_labels

_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+")

_SHADES = {
    "light": ("light", "светло", "светлый"),
    "dark": ("dark", "темно", "темный"),
}
_FINISHES = {
    "matte": ("matte", "matt", "матовый"),
    "silk": ("silk", "шелк", "шелковый"),
}


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")


def _build_word_map() -> dict[str, tuple[str, ...]]:
    words: dict[str, tuple[str, ...]] = {}
    for group, labels in color_group_labels().items():
        for label in labels:
            words[_fold(label)] = (group,)
    for canonical, labels in {**_SHADES, **_FINISHES}.items():
        for label in labels:
            words[_fold(label)] = (canonical,)
    # "Light blue" is written as one word in Russian.
    words["голубой"] = ("light", "blue")
    return words


_WORD_MAP = _build_word_map()
_FINISH_TOKENS = frozenset(_FINISHES)
_COLOR_TOKENS = frozenset(color_group_labels()) | frozenset(_SHADES)


def tokenize(value: str | None) -> list[str]:
    if not value:
        return []
    text = _fold(value).replace("+", " plus ")
    result: list[str] = []
    for token in _TOKEN_RE.findall(text):
        result.extend(_WORD_MAP.get(token, (token,)))
    return result


@dataclass(frozen=True)
class FilamentIdentity:
    product: frozenset[str]
    color: frozenset[str]
    hex: str | None


def filament_identity(
    *,
    brand_name: str | None,
    name: str,
    material_type: str | None,
    color_name: str | None,
    color_hex: str | None,
) -> FilamentIdentity:
    brand_tokens = set(tokenize(brand_name))
    color_name_tokens = tokenize(color_name)
    own_color = [token for token in color_name_tokens if token not in _FINISH_TOKENS]
    color_from_name: list[str] = []
    product: set[str] = set()
    for token in tokenize(material_type) + tokenize(name):
        if token in brand_tokens:
            continue
        if token in _COLOR_TOKENS or token in own_color:
            color_from_name.append(token)
            continue
        product.add(token)
    # "matte white" in the colour field is a finish of the product, not a colour.
    product |= {token for token in color_name_tokens if token in _FINISH_TOKENS}
    return FilamentIdentity(
        product=frozenset(product),
        color=frozenset(own_color or color_from_name),
        hex=(color_hex or "").upper() or None,
    )


def same_color(left: FilamentIdentity, right: FilamentIdentity) -> bool:
    if left.color and right.color:
        return left.color == right.color
    if left.hex and right.hex:
        return left.hex == right.hex
    return not (left.color or right.color or left.hex or right.hex)


def probable_duplicate(left: FilamentIdentity, right: FilamentIdentity) -> bool:
    return left.product == right.product and same_color(left, right)


def identity_of(filament: object, brand_name: str | None) -> FilamentIdentity:
    """Identity of a ``Filament`` row."""
    return filament_identity(
        brand_name=brand_name,
        name=filament.name,  # type: ignore[attr-defined]
        material_type=filament.material_type,  # type: ignore[attr-defined]
        color_name=filament.color_name,  # type: ignore[attr-defined]
        color_hex=filament.color_hex,  # type: ignore[attr-defined]
    )
