"""Add composite access paths for owned spool feeds.

Revision ID: spool_feed_indexes
Revises: calculator_history_feed_idx
"""

from alembic import op

revision = "spool_feed_indexes"
down_revision = "calculator_history_feed_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_spools_user_created_id", "user_spools", ["user_id", "created_at", "id"])
    op.create_index("ix_spools_user_state_created_id", "user_spools", ["user_id", "state", "created_at", "id"])
    op.create_index("ix_spools_user_fil_created_id", "user_spools", ["user_id", "filament_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_spools_user_fil_created_id", table_name="user_spools")
    op.drop_index("ix_spools_user_state_created_id", table_name="user_spools")
    op.drop_index("ix_spools_user_created_id", table_name="user_spools")
