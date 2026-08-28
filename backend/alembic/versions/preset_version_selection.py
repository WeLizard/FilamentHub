"""Pin saved presets to immutable versions and preserve fork bases.

Revision ID: preset_version_selection
Revises: edge_binding_index_repair
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "preset_version_selection"
down_revision = "edge_binding_index_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "preset_versions",
        sa.Column("parent_version_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_pv_parent",
        "preset_versions",
        "preset_versions",
        ["parent_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "presets",
        sa.Column("derived_from_version_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_presets_derived_version",
        "presets",
        "preset_versions",
        ["derived_from_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_presets_derived_version",
        "presets",
        ["derived_from_version_id"],
    )

    op.add_column(
        "user_saved_presets",
        sa.Column("selected_version_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "user_saved_presets",
        sa.Column("seen_version_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_usp_selected_version",
        "user_saved_presets",
        "preset_versions",
        ["selected_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_usp_seen_version",
        "user_saved_presets",
        "preset_versions",
        ["seen_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_usp_selected_version",
        "user_saved_presets",
        ["selected_version_id"],
    )

    # Historical version order is already authoritative. Backfill only the
    # linear predecessor; restored_from_version_id continues to describe the
    # version whose contents were restored.
    op.execute(
        """
        UPDATE preset_versions AS current
        SET parent_version_id = previous.id
        FROM preset_versions AS previous
        WHERE current.parent_version_id IS NULL
          AND previous.preset_id = current.preset_id
          AND previous.version_number = current.version_number - 1
        """
    )

    # Pin every existing library row to the version that was current at the
    # migration boundary. Later publications therefore become opt-in updates.
    op.execute(
        """
        UPDATE user_saved_presets AS saved
        SET selected_version_id = latest.id,
            seen_version_id = latest.id
        FROM (
            SELECT DISTINCT ON (preset_id) id, preset_id
            FROM preset_versions
            ORDER BY preset_id, version_number DESC
        ) AS latest
        WHERE latest.preset_id = saved.preset_id
          AND saved.selected_version_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_usp_selected_version", table_name="user_saved_presets")
    op.drop_constraint(
        "fk_usp_seen_version", "user_saved_presets", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_usp_selected_version", "user_saved_presets", type_="foreignkey"
    )
    op.drop_column("user_saved_presets", "seen_version_id")
    op.drop_column("user_saved_presets", "selected_version_id")

    op.drop_index("ix_presets_derived_version", table_name="presets")
    op.drop_constraint(
        "fk_presets_derived_version", "presets", type_="foreignkey"
    )
    op.drop_column("presets", "derived_from_version_id")

    op.drop_constraint("fk_pv_parent", "preset_versions", type_="foreignkey")
    op.drop_column("preset_versions", "parent_version_id")
