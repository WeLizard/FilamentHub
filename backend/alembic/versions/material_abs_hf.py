"""ABS HF (high flow) becomes a reference subtype of ABS.

Revision ID: material_abs_hf
Revises: filament_tech_properties

Stored base/subtype columns are re-derived from app.services.material_types for
rows whose derivation changes; the reference row is added.
"""

import sqlalchemy as sa

from alembic import op
from app.services.material_types import material_type_seed_rows, resolve_material_type

revision = "material_abs_hf"
down_revision = "filament_tech_properties"
branch_labels = None
depends_on = None

SUBTYPE = "ABS HF"

filaments = sa.table(
    "filaments",
    sa.column("material_type", sa.String),
    sa.column("base_material_type", sa.String),
    sa.column("material_subtype", sa.String),
)
properties = sa.table(
    "material_properties",
    sa.column("material_type", sa.String),
    sa.column("display_name", sa.String),
    sa.column("base_type", sa.String),
    sa.column("aliases", sa.JSON),
    sa.column("wiki_article_slug", sa.String),
)


def upgrade() -> None:
    bind = op.get_bind()
    stored = bind.execute(
        sa.select(
            filaments.c.material_type,
            filaments.c.base_material_type,
            filaments.c.material_subtype,
        ).distinct()
    ).all()
    for material_type, base, subtype in stored:
        resolution = resolve_material_type(material_type)
        if (resolution.base, resolution.subtype) == (base, subtype):
            continue
        bind.execute(
            filaments.update()
            .where(filaments.c.material_type == material_type)
            .values(base_material_type=resolution.base, material_subtype=resolution.subtype)
        )
    existing = {row[0] for row in bind.execute(sa.select(properties.c.material_type))}
    if SUBTYPE not in existing:
        op.bulk_insert(
            properties,
            [row for row in material_type_seed_rows() if row["material_type"] == SUBTYPE],
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        filaments.update()
        .where(filaments.c.material_subtype == SUBTYPE)
        .values(material_subtype=None)
    )
    bind.execute(
        properties.delete().where(
            properties.c.material_type == SUBTYPE, properties.c.base_type == "ABS"
        )
    )
