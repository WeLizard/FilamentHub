"""Separate connector liveness from durable snapshot ordering.

Revision ID: edge_snapshot_ordering
Revises: qr_identity_integrity_receipts
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "edge_snapshot_ordering"
down_revision = "qr_identity_integrity_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "physical_printer_connectors",
        sa.Column("last_observation_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "physical_printer_connectors",
        sa.Column("last_snapshot_sequence", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "physical_printer_connectors",
        sa.Column("last_snapshot_source_instance_id", sa.String(length=100), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE physical_printer_connectors AS connector
            SET last_observation_at = observation.last_observation_at
            FROM (
                SELECT connector_id, MAX(observed_at) AS last_observation_at
                FROM (
                    SELECT connector_id, observed_at
                    FROM physical_printer_status_observations
                    UNION ALL
                    SELECT connector_id, observed_at
                    FROM material_slot_observations
                ) AS all_observations
                GROUP BY connector_id
            ) AS observation
            WHERE connector.id = observation.connector_id
            """
        )
    )


def downgrade() -> None:
    op.drop_column(
        "physical_printer_connectors",
        "last_snapshot_source_instance_id",
    )
    op.drop_column("physical_printer_connectors", "last_snapshot_sequence")
    op.drop_column("physical_printer_connectors", "last_observation_at")
