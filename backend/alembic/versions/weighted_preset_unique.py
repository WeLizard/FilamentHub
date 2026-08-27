"""Enforce one generated weighted preset per filament.

Revision ID: weighted_preset_unique
Revises: material_slot_assignment_rev
"""

import sqlalchemy as sa

from alembic import op

revision = "weighted_preset_unique"
down_revision = "material_slot_assignment_rev"
branch_labels = None
depends_on = None


def upgrade() -> None:
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT filament_id, COUNT(*) AS weighted_count
            FROM presets
            WHERE is_weighted IS TRUE
              AND filament_id IS NOT NULL
            GROUP BY filament_id
            HAVING COUNT(*) > 1
            ORDER BY filament_id
            """
            )
        )
        .all()
    )
    if duplicates:
        listed = ", ".join(
            f"filament {row.filament_id}: {row.weighted_count} rows" for row in duplicates
        )
        raise RuntimeError(
            "Cannot enforce one weighted preset per filament while duplicates "
            f"exist ({listed}). Review and consolidate them explicitly, then rerun."
        )

    op.create_index(
        "uq_presets_weighted_filament",
        "presets",
        ["filament_id"],
        unique=True,
        postgresql_where=sa.text("is_weighted IS TRUE"),
        sqlite_where=sa.text("is_weighted = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_presets_weighted_filament", table_name="presets")
