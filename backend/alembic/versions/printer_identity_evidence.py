"""Separate connection evidence from machine presets.

Revision ID: printer_identity_evidence
Revises: observed_spool_identity
"""

import sqlalchemy as sa

from alembic import op

revision = "printer_identity_evidence"
down_revision = "observed_spool_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("printer_discovery_key", sa.String(300)))
    op.add_column("printer_connection_bindings", sa.Column("endpoint_token", sa.String(64)))
    op.add_column("printer_connection_bindings", sa.Column("identity_kind", sa.String(50)))
    op.add_column("printer_connection_bindings", sa.Column("identity_token", sa.String(64)))
    op.add_column(
        "printer_connection_bindings",
        sa.Column("assignment_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "printer_connection_bindings",
        sa.Column("status", sa.String(20), nullable=False, server_default="bound"),
    )
    op.create_index(
        "ix_pcb_user_endpoint_token", "printer_connection_bindings", ["user_id", "endpoint_token"]
    )
    op.create_table(
        "printer_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "physical_printer_id",
            sa.Integer(),
            sa.ForeignKey("user_printer_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "kind", "token", name="uq_printer_identity_user_token"),
    )
    op.create_index(
        "ix_printer_identities_physical_printer_id", "printer_identities", ["physical_printer_id"]
    )


def downgrade():
    op.drop_table("printer_identities")
    op.drop_index("ix_pcb_user_endpoint_token", table_name="printer_connection_bindings")
    for name in (
        "status",
        "assignment_confirmed",
        "identity_token",
        "identity_kind",
        "endpoint_token",
    ):
        op.drop_column("printer_connection_bindings", name)
    op.drop_column("users", "printer_discovery_key")
