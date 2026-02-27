"""add_spool_fk_to_preset_slot_tables

Revision ID: b9f3d6e2a1c4
Revises: 042335145290
Create Date: 2026-02-27 16:20:00.000000

Adds referential integrity for spool_id columns used by HH preset-slot integration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b9f3d6e2a1c4"
down_revision: Union[str, None] = "042335145290"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Cleanup invalid references before adding FKs.
    op.execute(
        """
        UPDATE preset_gate_states AS pgs
        SET spool_id = NULL
        WHERE spool_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM user_spools AS us
            WHERE us.id = pgs.spool_id
          )
        """
    )
    op.execute(
        """
        UPDATE preset_usage_events AS pue
        SET spool_id = NULL
        WHERE spool_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM user_spools AS us
            WHERE us.id = pue.spool_id
          )
        """
    )

    op.create_foreign_key(
        "fk_preset_gate_states_spool_id_user_spools",
        "preset_gate_states",
        "user_spools",
        ["spool_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_preset_usage_events_spool_id_user_spools",
        "preset_usage_events",
        "user_spools",
        ["spool_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_preset_gate_states_spool_id",
        "preset_gate_states",
        ["spool_id"],
        unique=False,
    )
    op.create_index(
        "ix_preset_usage_events_spool_id",
        "preset_usage_events",
        ["spool_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_preset_usage_events_spool_id", table_name="preset_usage_events")
    op.drop_index("ix_preset_gate_states_spool_id", table_name="preset_gate_states")

    op.drop_constraint(
        "fk_preset_usage_events_spool_id_user_spools",
        "preset_usage_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_preset_gate_states_spool_id_user_spools",
        "preset_gate_states",
        type_="foreignkey",
    )
