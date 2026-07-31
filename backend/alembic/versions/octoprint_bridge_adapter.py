"""Add adapter-owned storage for the native OctoPrint Bridge.

Revision ID: octoprint_bridge_adapter
Revises: feedback_thread_messages
Create Date: 2026-07-31
"""

import sqlalchemy as sa

from alembic import op

revision = "octoprint_bridge_adapter"
down_revision = "feedback_thread_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "octoprint_bridge_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column("pairing_code_hash", sa.String(length=64), nullable=True),
        sa.Column("pairing_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("paired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("instance_id", sa.String(length=200), nullable=True),
        sa.Column("plugin_version", sa.String(length=50), nullable=True),
        sa.Column("octoprint_version", sa.String(length=50), nullable=True),
        sa.Column("active_slot_index", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"],
            ["physical_printer_connectors.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id"),
        sa.UniqueConstraint("pairing_code_hash"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "octoprint_bridge_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("consumed_weight_g", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["octoprint_bridge_connections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "event_id",
            name="uq_octobridge_event_connection",
        ),
    )
    op.create_index(
        "ix_octobridge_event_connection",
        "octoprint_bridge_events",
        ["connection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_octobridge_event_connection",
        table_name="octoprint_bridge_events",
    )
    op.drop_table("octoprint_bridge_events")
    op.drop_table("octoprint_bridge_connections")
