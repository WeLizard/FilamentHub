"""Keep pre-release Edge credentials compatible with multi-connector nodes.

Revision ID: edge_binding_index_repair
Revises: edge_active_source_binding
"""

from __future__ import annotations

from alembic import op

revision = "edge_binding_index_repair"
down_revision = "edge_active_source_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One Edge node may legitimately host several connectors, so source identity
    # is scoped by the connector contract rather than globally unique.
    op.execute("DROP INDEX IF EXISTS uq_active_bridge_source")
    # These guards preserve forward-only upgrades for databases that already
    # executed the pre-release revision before its canonical columns settled.
    op.execute(
        """
        ALTER TABLE printer_bridge_credentials
        ADD COLUMN IF NOT EXISTS credential_generation INTEGER NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        ALTER TABLE printer_bridge_credentials
        ADD COLUMN IF NOT EXISTS rotated_at TIMESTAMPTZ NULL
        """
    )


def downgrade() -> None:
    # The preceding canonical revision owns these columns. There is no product
    # index to recreate when stepping back across this compatibility marker.
    pass
