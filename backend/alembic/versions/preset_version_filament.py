"""Preset versions remember the material they were saved for.

Replacing a preset's material makes a new version. Whoever stays on an earlier
version keeps its settings and its material, so the replacement reaches them as
an update instead of changing under them. Existing versions get the preset's
current material: no earlier link was recorded.

Revision ID: preset_version_filament
Revises: edge_nodes
"""

import sqlalchemy as sa

from alembic import op

revision = "preset_version_filament"
down_revision = "edge_nodes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("preset_versions", sa.Column("filament_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE preset_versions AS v
        SET filament_id = p.filament_id
        FROM presets AS p
        WHERE p.id = v.preset_id AND p.filament_id IS NOT NULL
        """
    )
    op.create_foreign_key(
        "fk_pv_filament",
        "preset_versions",
        "filaments",
        ["filament_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_preset_versions_filament_id", "preset_versions", ["filament_id"])


def downgrade() -> None:
    op.drop_index("ix_preset_versions_filament_id", table_name="preset_versions")
    op.drop_constraint("fk_pv_filament", "preset_versions", type_="foreignkey")
    op.drop_column("preset_versions", "filament_id")
