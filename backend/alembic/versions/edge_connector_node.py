"""Identify the local node independently of a connector event stream.

Revision ID: edge_connector_node
Revises: printer_identity_evidence
"""

import sqlalchemy as sa

from alembic import op

revision = "edge_connector_node"
down_revision = "printer_identity_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "physical_printer_connectors", sa.Column("node_instance_id", sa.String(100), nullable=True)
    )


def downgrade():
    op.drop_column("physical_printer_connectors", "node_instance_id")
