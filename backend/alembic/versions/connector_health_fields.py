"""Connector health: reachability, heartbeat interval, usage authority; native contact time.

Revision ID: connector_health_fields
Revises: connector_per_source

provider_reachable / contact_interval_s come from the connector's heartbeat.
usage_authority marks the one connector per system whose reports are deducted
from spools; user_printer_devices.native_last_seen_at is the native Spoolman
link's own contact time, separate from the merged last_seen_at.
"""

import sqlalchemy as sa

from alembic import op

revision = "connector_health_fields"
down_revision = "connector_per_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "physical_printer_connectors", sa.Column("provider_reachable", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "physical_printer_connectors", sa.Column("contact_interval_s", sa.Integer(), nullable=True)
    )
    op.add_column(
        "physical_printer_connectors",
        sa.Column("usage_authority", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "user_printer_devices",
        sa.Column("native_last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE user_printer_devices SET native_last_seen_at = last_seen_at "
        "WHERE api_key IS NOT NULL AND last_seen_at IS NOT NULL"
    )
    # Existing deployments had exactly one deducting source per system; keep the
    # most recently heard active connector that can report consumption.
    op.execute(
        """
        UPDATE physical_printer_connectors c SET usage_authority = TRUE
        WHERE c.id IN (
            SELECT DISTINCT ON (material_system_id) id
            FROM physical_printer_connectors
            WHERE active AND material_system_id IS NOT NULL
              AND capabilities::text LIKE '%"consumption"%'
            ORDER BY material_system_id, last_seen_at DESC NULLS LAST, id DESC
        )
        """
    )
    op.create_index(
        "uq_connector_usage_authority",
        "physical_printer_connectors",
        ["material_system_id"],
        unique=True,
        postgresql_where=sa.text("usage_authority"),
    )


def downgrade() -> None:
    op.drop_index("uq_connector_usage_authority", table_name="physical_printer_connectors")
    op.drop_column("user_printer_devices", "native_last_seen_at")
    op.drop_column("physical_printer_connectors", "usage_authority")
    op.drop_column("physical_printer_connectors", "contact_interval_s")
    op.drop_column("physical_printer_connectors", "provider_reachable")
