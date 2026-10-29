"""Base polymer and subtype of a filament's material type.

Revision ID: material_base_subtype
Revises: user_limits

``filaments.material_type`` stays as written by the manufacturer; two derived
columns let the catalog filter by the polymer family. The material type
reference comes from ``app.services.material_types`` so it has one definition.
Existing rows of ``material_properties`` are kept and only receive their base.
"""

import sqlalchemy as sa

from alembic import op
from app.services.material_types import material_type_seed_rows, resolve_material_type

revision = "material_base_subtype"
down_revision = "user_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filaments", sa.Column("base_material_type", sa.String(length=50), nullable=True))
    op.add_column("filaments", sa.Column("material_subtype", sa.String(length=50), nullable=True))
    op.create_index("ix_filaments_base_material_type", "filaments", ["base_material_type"])
    op.create_index("ix_filaments_material_subtype", "filaments", ["material_subtype"])

    op.add_column(
        "material_properties", sa.Column("base_type", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "material_properties",
        sa.Column("aliases", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "material_properties",
        sa.Column("wiki_article_slug", sa.String(length=200), nullable=True),
    )
    op.create_index("ix_material_properties_base_type", "material_properties", ["base_type"])

    bind = op.get_bind()
    filaments = sa.table(
        "filaments",
        sa.column("material_type", sa.String),
        sa.column("base_material_type", sa.String),
        sa.column("material_subtype", sa.String),
    )
    for (material_type,) in bind.execute(sa.select(filaments.c.material_type).distinct()):
        resolution = resolve_material_type(material_type)
        if resolution.base is None:
            continue
        bind.execute(
            filaments.update()
            .where(filaments.c.material_type == material_type)
            .values(base_material_type=resolution.base, material_subtype=resolution.subtype)
        )

    properties = sa.table(
        "material_properties",
        sa.column("material_type", sa.String),
        sa.column("display_name", sa.String),
        sa.column("base_type", sa.String),
        sa.column("aliases", sa.JSON),
        sa.column("wiki_article_slug", sa.String),
    )
    existing = {row[0] for row in bind.execute(sa.select(properties.c.material_type))}
    for material_type in existing:
        base = resolve_material_type(material_type).base
        if base is not None:
            bind.execute(
                properties.update()
                .where(properties.c.material_type == material_type)
                .values(base_type=base)
            )
    missing = [row for row in material_type_seed_rows() if row["material_type"] not in existing]
    if missing:
        op.bulk_insert(properties, missing)


def downgrade() -> None:
    op.drop_index("ix_material_properties_base_type", table_name="material_properties")
    op.drop_column("material_properties", "wiki_article_slug")
    op.drop_column("material_properties", "aliases")
    op.drop_column("material_properties", "base_type")
    op.drop_index("ix_filaments_material_subtype", table_name="filaments")
    op.drop_index("ix_filaments_base_material_type", table_name="filaments")
    op.drop_column("filaments", "material_subtype")
    op.drop_column("filaments", "base_material_type")
