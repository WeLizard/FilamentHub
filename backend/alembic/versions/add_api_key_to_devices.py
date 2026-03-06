"""Add api_key column to user_printer_devices.

Revision ID: add_api_key_to_devices
Revises: add_first_used_at
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa

revision = "add_api_key_to_devices"
down_revision = "add_first_used_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_printer_devices",
        sa.Column("api_key", sa.String(64), nullable=True),
    )
    op.create_index("ix_user_printer_devices_api_key", "user_printer_devices", ["api_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_printer_devices_api_key", table_name="user_printer_devices")
    op.drop_column("user_printer_devices", "api_key")
