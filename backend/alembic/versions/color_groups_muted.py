"""separate muted colours from true neutrals

Revision ID: color_groups_muted
Revises: color_groups_oklab
Create Date: 2026-08-12
"""

import re
from collections.abc import Callable, Sequence
from math import hypot

import sqlalchemy as sa

from alembic import op

revision: str = "color_groups_muted"
down_revision: str | None = "color_groups_oklab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_BASE_PALETTE = {
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
_MUTED_ANCHORS = {
    "orange": ("#E64A19", "#F4511E"),
    "green": ("#556B2F", "#6B7D52", "#8A9A5B", "#BFD8A6"),
    "blue": ("#78909C", "#90A4AE"),
    "pink": ("#B76E79", "#C58F89", "#D8A39D"),
    "brown": ("#B87333", "#B8895A", "#C2A277", "#D2B48C"),
}
_CHROMATIC_GROUPS = tuple(
    group for group in _BASE_PALETTE if group not in {"black", "white", "gray", "silver"}
)
_NON_METALLIC_CHROMATIC_GROUPS = tuple(
    group for group in _CHROMATIC_GROUPS if group != "gold"
)
_NON_METALLIC_V1_GROUPS = tuple(
    group for group in _BASE_PALETTE if group not in {"gold", "silver"}
)
_NEUTRAL_CHROMA_MAX = 0.035


def _effects(visual_settings: object) -> set[str]:
    if not isinstance(visual_settings, dict):
        return set()
    raw_effects = visual_settings.get("effects")
    values = (
        {str(effect).strip().casefold() for effect in raw_effects if effect}
        if isinstance(raw_effects, list)
        else set()
    )
    filler = visual_settings.get("filler")
    if filler:
        values.add(str(filler).strip().casefold())
    return values


def _oklab(color_hex: str) -> tuple[float, float, float]:
    value = color_hex.removeprefix("#")
    red, green, blue = (int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = linear(red), linear(green), linear(blue)
    cone_l = (0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue) ** (1 / 3)
    cone_m = (0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue) ** (1 / 3)
    cone_s = (0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue) ** (1 / 3)
    return (
        0.2104542553 * cone_l + 0.7936177850 * cone_m - 0.0040720468 * cone_s,
        1.9779984951 * cone_l - 2.4285922050 * cone_m + 0.4505937099 * cone_s,
        0.0259040371 * cone_l + 0.7827717662 * cone_m - 0.8086757660 * cone_s,
    )


def _create_palette(*, include_muted: bool) -> dict[str, tuple[tuple[float, float, float], ...]]:
    return {
        group: tuple(
            _oklab(color_hex)
            for color_hex in (
                *colors,
                *(_MUTED_ANCHORS.get(group, ()) if include_muted else ()),
            )
        )
        for group, colors in _BASE_PALETTE.items()
    }


_OKLAB_PALETTE_V1 = _create_palette(include_muted=False)
_OKLAB_PALETTE_V2 = _create_palette(include_muted=True)


def _nearest_group(
    sample: tuple[float, float, float],
    candidates: tuple[str, ...],
    palette: dict[str, tuple[tuple[float, float, float], ...]],
) -> str:
    def nearest_distance(group: str) -> float:
        return min(
            sum(
                (component - anchor_component) ** 2
                for component, anchor_component in zip(sample, anchor, strict=True)
            )
            for anchor in palette[group]
        )

    return min(candidates, key=nearest_distance)


def _classify_v2(color_hex: str | None, visual_settings: object) -> str | None:
    match = _HEX_RE.fullmatch(color_hex.strip()) if color_hex else None
    if match is None:
        return None
    sample = _oklab(match.group(1))
    lightness, axis_a, axis_b = sample
    chroma = hypot(axis_a, axis_b)
    metallic = "metallic" in _effects(visual_settings)

    if lightness <= 0.20 or (lightness <= 0.28 and chroma <= 0.08):
        return "black"
    if lightness >= 0.93 and chroma <= 0.04:
        return "white"
    if chroma <= _NEUTRAL_CHROMA_MAX:
        return "silver" if metallic else "gray"

    candidates = _CHROMATIC_GROUPS if metallic else _NON_METALLIC_CHROMATIC_GROUPS
    return _nearest_group(sample, candidates, _OKLAB_PALETTE_V2)


def _classify_v1(color_hex: str | None, visual_settings: object) -> str | None:
    match = _HEX_RE.fullmatch(color_hex.strip()) if color_hex else None
    if match is None:
        return None
    sample = _oklab(match.group(1))
    metallic = "metallic" in _effects(visual_settings)
    candidates = tuple(_BASE_PALETTE) if metallic else _NON_METALLIC_V1_GROUPS
    return _nearest_group(sample, candidates, _OKLAB_PALETTE_V1)


def _reclassify(classifier: Callable[[str | None, object], str | None]) -> None:
    filaments = sa.table(
        "filaments",
        sa.column("id", sa.Integer()),
        sa.column("color_hex", sa.String()),
        sa.column("visual_settings", sa.JSON()),
        sa.column("color_group", sa.String()),
        sa.column("color_group_source", sa.String()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(filaments.c.id, filaments.c.color_hex, filaments.c.visual_settings).where(
            filaments.c.color_group_source == "auto"
        )
    ).mappings()
    payload = [
        {
            "row_id": row["id"],
            "group": classifier(row["color_hex"], row["visual_settings"]),
        }
        for row in rows
    ]
    if payload:
        connection.execute(
            sa.update(filaments)
            .where(filaments.c.id == sa.bindparam("row_id"))
            .values(color_group=sa.bindparam("group")),
            payload,
        )


def upgrade() -> None:
    _reclassify(_classify_v2)


def downgrade() -> None:
    _reclassify(_classify_v1)
