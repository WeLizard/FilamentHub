"""reclassify automatic colour groups with OKLab anchors

Revision ID: color_groups_oklab
Revises: filament_color_groups
Create Date: 2026-08-12
"""

import colorsys
import re
from collections.abc import Callable, Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "color_groups_oklab"
down_revision: str | None = "filament_color_groups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_PALETTE = {
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
_NON_METALLIC_GROUPS = tuple(group for group in _PALETTE if group not in {"gold", "silver"})


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


_OKLAB_PALETTE = {
    group: tuple(_oklab(color_hex) for color_hex in colors) for group, colors in _PALETTE.items()
}


def _classify_oklab(color_hex: str | None, visual_settings: object) -> str | None:
    match = _HEX_RE.fullmatch(color_hex.strip()) if color_hex else None
    if match is None:
        return None
    sample = _oklab(match.group(1))
    metallic = "metallic" in _effects(visual_settings)
    candidates = tuple(_PALETTE) if metallic else _NON_METALLIC_GROUPS

    def nearest_distance(group: str) -> float:
        return min(
            sum(
                (component - anchor_component) ** 2
                for component, anchor_component in zip(sample, anchor, strict=True)
            )
            for anchor in _OKLAB_PALETTE[group]
        )

    return min(candidates, key=nearest_distance)


def _classify_legacy(color_hex: str | None, visual_settings: object) -> str | None:
    match = _HEX_RE.fullmatch(color_hex.strip()) if color_hex else None
    if match is None:
        return None
    value = match.group(1)
    red, green, blue = (int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    hue_degrees = hue * 360
    metallic = "metallic" in _effects(visual_settings)
    if lightness <= 0.18:
        return "black"
    if saturation <= 0.15:
        if lightness >= 0.88:
            return "white"
        return "silver" if metallic else "gray"
    if metallic and 35 <= hue_degrees < 70:
        return "gold"
    if 15 <= hue_degrees < 50 and lightness < 0.38:
        return "brown"
    if hue_degrees >= 345 or hue_degrees < 15:
        return "pink" if lightness >= 0.68 else "red"
    if hue_degrees < 45:
        return "orange"
    if hue_degrees < 70:
        return "yellow"
    if hue_degrees < 170:
        return "green"
    if hue_degrees < 255:
        return "blue"
    if hue_degrees < 320:
        return "purple"
    return "pink"


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
    _reclassify(_classify_oklab)


def downgrade() -> None:
    _reclassify(_classify_legacy)
