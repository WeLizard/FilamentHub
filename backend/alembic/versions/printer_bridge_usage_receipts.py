"""Add provider-neutral printer bridge usage and batch receipts.

Revision ID: printer_bridge_usage_receipts
Revises: edge_snapshot_ordering
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "printer_bridge_usage_receipts"
down_revision = "edge_snapshot_ordering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "printer_bridge_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column("source_instance_id", sa.String(length=100), nullable=False),
        sa.Column("receipt_kind", sa.String(length=20), nullable=False),
        sa.Column("receipt_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "consumed_weight_g",
            sa.Float(),
            nullable=False,
        ),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"],
            ["physical_printer_connectors.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connector_id",
            "source_instance_id",
            "receipt_kind",
            "receipt_id",
            name="uq_printer_bridge_receipt_identity",
        ),
    )
    op.create_index(
        "ix_printer_bridge_receipts_connector_id",
        "printer_bridge_receipts",
        ["connector_id"],
    )
    op.create_index(
        "ix_printer_bridge_receipt_sequence",
        "printer_bridge_receipts",
        ["connector_id", "source_instance_id", "receipt_kind", "sequence"],
    )

    # Preserve every native OctoPrint replay receipt before its writer moves to
    # the provider-neutral table. The legacy table remains intact for rollback
    # inspection and is no longer a runtime source of truth.
    op.execute(
        sa.text(
            """
            INSERT INTO printer_bridge_receipts (
                connector_id,
                source_instance_id,
                receipt_kind,
                receipt_id,
                sequence,
                payload_hash,
                consumed_weight_g,
                response_payload,
                created_at
            )
            SELECT
                connection.connector_id,
                COALESCE(
                    NULLIF(connection.instance_id, ''),
                    'octoprint-connection-' || connection.id::text
                ),
                'usage_event',
                event.event_id,
                NULL,
                event.payload_hash,
                event.consumed_weight_g,
                NULL,
                event.created_at
            FROM octoprint_bridge_events AS event
            JOIN octoprint_bridge_connections AS connection
              ON connection.id = event.connection_id
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_printer_bridge_receipt_sequence",
        table_name="printer_bridge_receipts",
    )
    op.drop_index(
        "ix_printer_bridge_receipts_connector_id",
        table_name="printer_bridge_receipts",
    )
    op.drop_table("printer_bridge_receipts")
