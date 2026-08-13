"""add normalized catalogue colour groups

Revision ID: filament_color_groups
Revises: print_job_history
Create Date: 2026-08-12
"""

import colorsys
import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "filament_color_groups"
down_revision: str | None = "print_job_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _classify(color_hex: str | None, visual_settings: object) -> str | None:
    match = _HEX_RE.fullmatch(color_hex.strip()) if color_hex else None
    if match is None:
        return None

    value = match.group(1)
    red, green, blue = (int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    hue_degrees = hue * 360
    effects: set[str] = set()
    if isinstance(visual_settings, dict):
        raw_effects = visual_settings.get("effects")
        if isinstance(raw_effects, list):
            effects.update(str(effect).strip().casefold() for effect in raw_effects if effect)
        filler = visual_settings.get("filler")
        if filler:
            effects.add(str(filler).strip().casefold())
    metallic = "metallic" in effects

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


def upgrade() -> None:
    op.add_column("filaments", sa.Column("color_group", sa.String(length=16), nullable=True))
    op.add_column(
        "filaments",
        sa.Column(
            "color_group_source",
            sa.String(length=10),
            server_default="auto",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_filaments_color_group",
        "filaments",
        "color_group IS NULL OR color_group IN "
        "('black','white','gray','red','orange','yellow','green','blue',"
        "'purple','pink','brown','gold','silver')",
    )
    op.create_check_constraint(
        "ck_filaments_color_group_source",
        "filaments",
        "color_group_source IN ('auto','manual')",
    )

    filaments = sa.table(
        "filaments",
        sa.column("id", sa.Integer()),
        sa.column("color_hex", sa.String()),
        sa.column("visual_settings", sa.JSON()),
        sa.column("color_group", sa.String()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(filaments.c.id, filaments.c.color_hex, filaments.c.visual_settings)
    ).mappings()
    payload = [
        {
            "row_id": row["id"],
            "group": _classify(row["color_hex"], row["visual_settings"]),
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

    op.create_index("ix_filaments_color_group", "filaments", ["color_group"])


def downgrade() -> None:
    op.drop_index("ix_filaments_color_group", table_name="filaments")
    op.drop_constraint("ck_filaments_color_group_source", "filaments", type_="check")
    op.drop_constraint("ck_filaments_color_group", "filaments", type_="check")
    op.drop_column("filaments", "color_group_source")
    op.drop_column("filaments", "color_group")
