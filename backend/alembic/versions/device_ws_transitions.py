"""Native Spoolman WebSocket open/close times on a printer device.

Revision ID: device_ws_transitions
Revises: material_slot_visibility

Only transitions are stored; whether a socket is open right now is a Redis lease.
"""

import sqlalchemy as sa

from alembic import op

revision = "device_ws_transitions"
down_revision = "material_slot_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_printer_devices",
        sa.Column("ws_connected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_printer_devices",
        sa.Column("ws_disconnected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_printer_devices", "ws_disconnected_at")
    op.drop_column("user_printer_devices", "ws_connected_at")
