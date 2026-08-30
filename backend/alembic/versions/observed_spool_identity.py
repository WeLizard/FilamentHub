"""Preserve observed spool identity separately from desired assignments."""

import sqlalchemy as sa

from alembic import op

revision = "observed_spool_identity"
down_revision = "orca_sync_report_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("material_slot_observations", sa.Column("spool_id", sa.Integer(), nullable=True))
    op.add_column(
        "material_slot_observations",
        sa.Column("spool_identity_known", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_slot_observation_spool",
        "material_slot_observations",
        "user_spools",
        ["spool_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_slot_observation_spool", "material_slot_observations", type_="foreignkey"
    )
    op.drop_column("material_slot_observations", "spool_identity_known")
    op.drop_column("material_slot_observations", "spool_id")
