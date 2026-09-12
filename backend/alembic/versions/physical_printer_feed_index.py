"""Add the physical-printer feed access path.

Revision ID: physical_printer_feed_idx
Revises: spool_feed_indexes
"""

from alembic import op

revision = "physical_printer_feed_idx"
down_revision = "spool_feed_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_user_printer_devices_user_created_id",
        "user_printer_devices",
        ["user_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_printer_devices_user_created_id",
        table_name="user_printer_devices",
    )
