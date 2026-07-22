"""PrinterConnectionBinding — normalized endpoint bound to a physical printer.

Revision ID: printer_conn_bindings
Revises: orca_conn_observations
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "printer_conn_bindings"
down_revision: str | None = "orca_conn_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "printer_connection_bindings"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("physical_printer_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), server_default="orcaslicer_plugin", nullable=False),
        sa.Column("normalized_endpoint", sa.String(length=600), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("scheme", sa.String(length=20), nullable=True),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column("print_host", sa.String(length=500), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["physical_printer_id"], ["user_printer_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pcb_user_endpoint", TABLE, ["user_id", "normalized_endpoint"], unique=True)
    op.create_index("ix_pcb_physical_printer", TABLE, ["physical_printer_id"])


def downgrade() -> None:
    op.drop_index("ix_pcb_physical_printer", table_name=TABLE)
    op.drop_index("ix_pcb_user_endpoint", table_name=TABLE)
    op.drop_table(TABLE)
