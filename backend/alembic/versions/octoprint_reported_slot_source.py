"""Record whether an OctoPrint slot report is declared, commanded or observed.

Revision ID: octoprint_reported_slot_source
Revises: calculator_economics_sources
"""

import sqlalchemy as sa

from alembic import op

revision = "octoprint_reported_slot_source"
down_revision = "calculator_economics_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "octoprint_bridge_connections",
        sa.Column("reported_slot_source", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("octoprint_bridge_connections", "reported_slot_source")
