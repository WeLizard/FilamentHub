"""Separate personal preset ownership from official organization assets.

Revision ID: official_preset_ownership
Revises: octoprint_bridge_routing
"""

import sqlalchemy as sa

from alembic import op

revision = "official_preset_ownership"
down_revision = "octoprint_bridge_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("presets") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("derived_from_preset_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_presets_created_by_user_id_users",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_presets_derived_from_preset_id_presets",
            "presets",
            ["derived_from_preset_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_presets_created_by_user_id", ["created_by_user_id"])
        batch_op.create_index("ix_presets_derived_from_preset_id", ["derived_from_preset_id"])

    op.execute("UPDATE presets SET created_by_user_id = user_id WHERE user_id IS NOT NULL")

    # Evidence-based backfill only: a creator who had exactly one Organization
    # with an active grant for the preset's Brand can be assigned unambiguously.
    op.execute(
        """
        WITH candidates AS (
            SELECT p.id AS preset_id,
                   MIN(om.organization_id) AS organization_id,
                   COUNT(DISTINCT om.organization_id) AS organization_count
              FROM presets p
              JOIN filaments f ON f.id = p.filament_id
              JOIN organization_memberships om
                ON om.user_id = p.user_id AND om.active = true
              JOIN brand_territorial_grants btg
                ON btg.organization_id = om.organization_id
               AND btg.brand_id = f.brand_id
               AND btg.status = 'active'
               AND btg.revoked_at IS NULL
             WHERE p.is_official = true
               AND p.organization_id IS NULL
               AND p.user_id IS NOT NULL
             GROUP BY p.id
        )
        UPDATE presets p
           SET organization_id = candidates.organization_id
          FROM candidates
         WHERE p.id = candidates.preset_id
           AND candidates.organization_count = 1
        """
    )

    # Official rows with a proven Organization cease to be personal assets.
    op.execute(
        """
        UPDATE presets
           SET user_id = NULL
         WHERE is_official = true
           AND organization_id IS NOT NULL
        """
    )


def downgrade() -> None:
    # Preserve an actor owner for rows that became Organization-owned before
    # removing the explicit provenance columns.
    op.execute(
        """
        UPDATE presets
           SET user_id = created_by_user_id
         WHERE user_id IS NULL
           AND created_by_user_id IS NOT NULL
        """
    )
    with op.batch_alter_table("presets") as batch_op:
        batch_op.drop_index("ix_presets_derived_from_preset_id")
        batch_op.drop_index("ix_presets_created_by_user_id")
        batch_op.drop_constraint(
            "fk_presets_derived_from_preset_id_presets", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_presets_created_by_user_id_users", type_="foreignkey"
        )
        batch_op.drop_column("derived_from_preset_id")
        batch_op.drop_column("created_by_user_id")
