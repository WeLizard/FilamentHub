"""Keep the latest bounded JSON value for unknown Orca preset fields.

Revision ID: orca_schema_sample_value
Revises: filament_qr_aliases
"""

import sqlalchemy as sa

from alembic import op

revision = "orca_schema_sample_value"
down_revision = "filament_qr_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orca_schema_observations",
        sa.Column("sample_value", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orca_schema_observations", "sample_value")
