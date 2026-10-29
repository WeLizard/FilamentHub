"""One connector per source: several workstations or Edges per printer.

Revision ID: connector_per_source
Revises: device_pending_api_key

The unique key (printer, provider, transport) becomes (printer, provider,
transport, source). It only relaxes the constraint, so existing rows stay valid.
"""

from alembic import op

revision = "connector_per_source"
down_revision = "device_pending_api_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_physical_printer_connector", "physical_printer_connectors", type_="unique")
    op.execute(
        "CREATE UNIQUE INDEX uq_physical_printer_connector_source ON physical_printer_connectors "
        "(physical_printer_id, provider, transport, (coalesce(source_instance_id, '')))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_physical_printer_connector_source")
    op.create_unique_constraint(
        "uq_physical_printer_connector",
        "physical_printer_connectors",
        ["physical_printer_id", "provider", "transport"],
    )
