"""ABS+, PETG+ and ASA+ become reference subtypes.

Revision ID: material_plus_subtypes
Revises: spool_purchase_date

The derived base/subtype columns are written only when a filament is saved, so
rows typed before the reference grew are re-derived here from
``app.services.material_types``. Only rows whose derivation changes are touched.
"""

import sqlalchemy as sa

from alembic import op
from app.services.material_types import material_type_seed_rows, resolve_material_type

revision = "material_plus_subtypes"
down_revision = "spool_purchase_date"
branch_labels = None
depends_on = None

NEW_SUBTYPES = ("ABS+", "PETG+", "ASA+")

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
    )
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
    missing = [
        row
        for row in material_type_seed_rows()
        if row["material_type"] in NEW_SUBTYPES and row["material_type"] not in existing
    ]
    if missing:
        op.bulk_insert(properties, missing)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        filaments.update()
        .where(filaments.c.material_subtype.in_(NEW_SUBTYPES))
        .values(material_subtype=None)
    )
    for code in NEW_SUBTYPES:
        base = code.rstrip("+")
        bind.execute(
            properties.delete().where(
                properties.c.material_type == code, properties.c.base_type == base
            )
        )
