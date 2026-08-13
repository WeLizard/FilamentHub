"""Normalize catalogue colours without rewriting manufacturer colour names."""

from __future__ import annotations

import re
import unicodedata
from math import hypot
from typing import Literal, cast

FilamentColorGroup = Literal[
    "black",
    "white",
    "gray",
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "purple",
    "pink",
    "brown",
    "gold",
    "silver",
]
ColorGroupSource = Literal["auto", "manual"]
MULTICOLOR_COLOR_TYPES = ("two", "three", "gradient", "transition")

COLOR_GROUPS: tuple[FilamentColorGroup, ...] = (
    "black",
    "white",
    "gray",
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "purple",
    "pink",
    "brown",
    "gold",
    "silver",
)

# A deliberately compact reference map rather than a dictionary of named
# colours.  The representative HEX remains the source value; these anchors are
# only used to place it into a coarse, language-independent search family.
COLOR_GROUP_PALETTE: dict[FilamentColorGroup, tuple[str, ...]] = {
    "black": ("#000000", "#111827", "#1F2937", "#2B2B2B"),
    "white": ("#FFFFFF", "#FAFAF9", "#F5F5F4", "#FFF7ED"),
    "gray": ("#4B5563", "#6B7280", "#9CA3AF", "#D1D5DB"),
    "red": ("#7F1D1D", "#B91C1C", "#EF4444", "#F87171", "#FF0000"),
    "orange": ("#9A3412", "#C2410C", "#F97316", "#FB923C", "#FF7A00"),
    "yellow": ("#A16207", "#CA8A04", "#EAB308", "#FACC15", "#FFD900"),
    "green": ("#14532D", "#15803D", "#22C55E", "#4ADE80", "#00A651", "#008080"),
    "blue": ("#172554", "#1D4ED8", "#3B82F6", "#60A5FA", "#0066FF", "#00FFFF"),
    "purple": ("#4C1D95", "#6D28D9", "#8B5CF6", "#A855F7", "#7C3AED", "#800080"),
    "pink": ("#831843", "#BE185D", "#EC4899", "#F472B6", "#FF69B4", "#FFB6C1"),
    "brown": ("#3F2D20", "#5C3A21", "#7C4A2D", "#8B5E3C", "#8B4513", "#A52A2A"),
    "gold": ("#806000", "#A67C00", "#B8860B", "#D4AF37", "#E5C158"),
    "silver": ("#707780", "#8E959E", "#A7ADB5", "#C0C0C0", "#D5D8DC"),
}

# Muted colours need denser anchors than the compact palette shown in the UI.
# These are colour-space references, not aliases for manufacturer colour names.
_MUTED_COLOR_ANCHORS: dict[FilamentColorGroup, tuple[str, ...]] = {
    "orange": ("#E64A19", "#F4511E"),
    "green": ("#556B2F", "#6B7D52", "#8A9A5B", "#BFD8A6"),
    "blue": ("#78909C", "#90A4AE"),
    "pink": ("#B76E79", "#C58F89", "#D8A39D"),
    "brown": ("#B87333", "#B8895A", "#C2A277", "#D2B48C"),
}

_CHROMATIC_GROUPS = tuple(
    group for group in COLOR_GROUPS if group not in {"black", "white", "gray", "silver"}
)
_NON_METALLIC_CHROMATIC_GROUPS = tuple(
    group for group in _CHROMATIC_GROUPS if group != "gold"
)
_NEUTRAL_CHROMA_MAX = 0.035

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_SEPARATORS = re.compile(r"[\W_]+", re.UNICODE)


def _normalize_search(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return _SEPARATORS.sub(" ", normalized).strip()


_COLOR_LABELS: dict[FilamentColorGroup, tuple[str, ...]] = {
    "black": ("black", "черный", "чёрный", "黑", "黑色"),
    "white": ("white", "белый", "白", "白色"),
    "gray": ("gray", "grey", "серый", "灰", "灰色"),
    "red": ("red", "красный", "红", "红色"),
    "orange": ("orange", "оранжевый", "橙", "橙色"),
    "yellow": ("yellow", "желтый", "жёлтый", "黄", "黄色"),
    "green": ("green", "зеленый", "зелёный", "绿", "绿色"),
    "blue": ("blue", "синий", "голубой", "蓝", "蓝色"),
    "purple": ("purple", "violet", "фиолетовый", "紫", "紫色"),
    "pink": ("pink", "розовый", "粉", "粉色"),
    "brown": ("brown", "коричневый", "棕", "棕色"),
    "gold": ("gold", "golden", "золотой", "золото", "金", "金色"),
    "silver": ("silver", "серебряный", "серебро", "银", "银色"),
}
_NORMALIZED_COLOR_LABELS = {
    group: tuple(_normalize_search(label) for label in labels)
    for group, labels in _COLOR_LABELS.items()
}


def resolve_color_group_aliases(search: str) -> tuple[FilamentColorGroup, ...]:
    """Resolve visible ru/en/zh colour labels to canonical catalogue groups."""
    needle = _normalize_search(search)
    if not needle:
        return ()
    return tuple(
        group
        for group, labels in _NORMALIZED_COLOR_LABELS.items()
        if any(label in needle or (len(needle) >= 3 and needle in label) for label in labels)
    )


def _visual_effects(visual_settings: dict | None) -> set[str]:
    if not isinstance(visual_settings, dict):
        return set()
    raw_effects = visual_settings.get("effects")
    effects = (
        {str(effect).strip().casefold() for effect in raw_effects if effect}
        if isinstance(raw_effects, list)
        else set()
    )
    filler = visual_settings.get("filler")
    if filler:
        effects.add(str(filler).strip().casefold())
    return effects


def _hex_to_oklab(color_hex: str) -> tuple[float, float, float]:
    """Convert a validated six-digit sRGB HEX value to perceptual OKLab."""
    value = color_hex.removeprefix("#")
    red, green, blue = (int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))

    def linear(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = linear(red), linear(green), linear(blue)
    cone_l = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    cone_m = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    cone_s = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    cone_l, cone_m, cone_s = cone_l ** (1 / 3), cone_m ** (1 / 3), cone_s ** (1 / 3)
    return (
        0.2104542553 * cone_l + 0.7936177850 * cone_m - 0.0040720468 * cone_s,
        1.9779984951 * cone_l - 2.4285922050 * cone_m + 0.4505937099 * cone_s,
        0.0259040371 * cone_l + 0.7827717662 * cone_m - 0.8086757660 * cone_s,
    )


_OKLAB_PALETTE = {
    group: tuple(
        _hex_to_oklab(color_hex)
        for color_hex in (*colors, *_MUTED_COLOR_ANCHORS.get(group, ()))
    )
    for group, colors in COLOR_GROUP_PALETTE.items()
}


def classify_color_group(
    color_hex: str | None,
    visual_settings: dict | None = None,
) -> FilamentColorGroup | None:
    """Return a cautious search hint derived from the representative HEX.

    This is deliberately not a colour-name translator. A contributor can
    override the result manually, while the original name and complete palette
    remain untouched.
    """
    match = _HEX_RE.fullmatch(color_hex.strip()) if color_hex else None
    if match is None:
        return None

    sample = _hex_to_oklab(match.group(1))
    lightness, axis_a, axis_b = sample
    chroma = hypot(axis_a, axis_b)
    metallic = "metallic" in _visual_effects(visual_settings)

    # Near-neutral colours are handled before hue matching. Without this
    # boundary, a sparse gray palette steals muted but visibly chromatic
    # colours such as moss, dusty rose and light wood tones.
    if lightness <= 0.20 or (lightness <= 0.28 and chroma <= 0.08):
        return "black"
    if lightness >= 0.93 and chroma <= 0.04:
        return "white"
    if chroma <= _NEUTRAL_CHROMA_MAX:
        return "silver" if metallic else "gray"

    candidates = _CHROMATIC_GROUPS if metallic else _NON_METALLIC_CHROMATIC_GROUPS

    def nearest_distance(group: FilamentColorGroup) -> float:
        return min(
            sum(
                (component - anchor_component) ** 2
                for component, anchor_component in zip(sample, anchor, strict=True)
            )
            for anchor in _OKLAB_PALETTE[group]
        )

    return min(candidates, key=nearest_distance)


def resolve_color_group(
    *,
    color_hex: str | None,
    visual_settings: dict | None,
    requested_group: str | None,
    requested_source: str | None,
) -> tuple[FilamentColorGroup | None, ColorGroupSource]:
    """Apply the manual-override contract and return persisted values."""
    if requested_source == "manual":
        if requested_group is None:
            return None, "manual"
        if requested_group in COLOR_GROUPS:
            return cast(FilamentColorGroup, requested_group), "manual"
    return classify_color_group(color_hex, visual_settings), "auto"
