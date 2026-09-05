"""Persist one stable topology source per material system.

Revision ID: adapter_topology_authority
Revises: auth_reset_grant_hash
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "adapter_topology_authority"
down_revision = "auth_reset_grant_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "physical_printer_connectors",
        sa.Column(
            "topology_authority",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "physical_printer_connectors",
        sa.Column("last_topology_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_material_system_topology_authority",
        "physical_printer_connectors",
        ["material_system_id"],
        unique=True,
        postgresql_where=sa.text("topology_authority"),
        sqlite_where=sa.text("topology_authority = 1"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_material_system_topology_authority",
        table_name="physical_printer_connectors",
    )
    op.drop_column("physical_printer_connectors", "last_topology_at")
    op.drop_column("physical_printer_connectors", "topology_authority")
