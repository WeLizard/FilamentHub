"""Track explicit printer bridge credential generations and rotation.

Revision ID: edge_active_source_binding
Revises: printer_bridge_usage_receipts
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "edge_active_source_binding"
down_revision = "printer_bridge_usage_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "printer_bridge_credentials",
        sa.Column(
            "credential_generation",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "printer_bridge_credentials",
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("printer_bridge_credentials", "rotated_at")
    op.drop_column("printer_bridge_credentials", "credential_generation")
