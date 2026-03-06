"""Add printer_hostname to user_printer_devices.

Revision ID: add_printer_hostname
Revises: add_api_key_to_devices
"""

import sqlalchemy as sa
from alembic import op

revision = "add_printer_hostname"
down_revision = "add_api_key_to_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_printer_devices",
        sa.Column("printer_hostname", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_printer_devices", "printer_hostname")
