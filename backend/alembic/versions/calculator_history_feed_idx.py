"""Add the composite access path for calculator history feeds.

Revision ID: calculator_history_feed_idx
Revises: notification_feed_indexes
"""

from alembic import op

revision = "calculator_history_feed_idx"
down_revision = "notification_feed_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_calc_history_user_created_id",
        "calculator_history_entries",
        ["user_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_calc_history_user_created_id",
        table_name="calculator_history_entries",
    )
