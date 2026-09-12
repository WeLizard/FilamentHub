"""Add indexes for bounded notification feeds.

Revision ID: notification_feed_indexes
Revises: account_email_change_proof
"""

from alembic import op

revision = "notification_feed_indexes"
down_revision = "account_email_change_proof"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_notifications_user_feed",
        "notifications",
        ["user_id", "id"],
    )
    op.create_index(
        "ix_notifications_user_unread_feed",
        "notifications",
        ["user_id", "read", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_unread_feed", table_name="notifications")
    op.drop_index("ix_notifications_user_feed", table_name="notifications")
