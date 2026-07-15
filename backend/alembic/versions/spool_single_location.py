"""enforce single physical location per user spool

Revision ID: spool_single_location
Revises: brand_slug_redirects
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "spool_single_location"
down_revision: str | None = "brand_slug_redirects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Preflight: a spool bound to several gates keeps only its freshest
    # binding; stale duplicates are detached (rows and presets stay intact).
    op.execute(
        """
        UPDATE preset_gate_states AS pgs
        SET spool_id = NULL
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY spool_id
                       ORDER BY source_ts DESC, id DESC
                   ) AS rn
            FROM preset_gate_states
            WHERE spool_id IS NOT NULL
        ) ranked
        WHERE pgs.id = ranked.id AND ranked.rn > 1
        """
    )
    op.create_index(
        "uq_gate_state_active_spool",
        "preset_gate_states",
        ["spool_id"],
        unique=True,
        postgresql_where=sa.text("spool_id IS NOT NULL"),
        sqlite_where=sa.text("spool_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_gate_state_active_spool", table_name="preset_gate_states")
