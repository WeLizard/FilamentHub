"""A replacement device key that overlaps the active one until first use.

Revision ID: device_pending_api_key
Revises: device_ws_transitions
"""

import sqlalchemy as sa

from alembic import op

revision = "device_pending_api_key"
down_revision = "device_ws_transitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_printer_devices", sa.Column("pending_api_key", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_user_printer_devices_pending_api_key",
        "user_printer_devices",
        ["pending_api_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_printer_devices_pending_api_key", table_name="user_printer_devices")
    op.drop_column("user_printer_devices", "pending_api_key")
