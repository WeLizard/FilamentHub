"""Filament technical properties: measured data-sheet values.

Revision ID: filament_tech_properties
Revises: filament_packagings

Additive JSON list of manufacturer measurements (code, value or range, unit,
standard, conditions); codes come from app.services.technical_properties.
"""

import sqlalchemy as sa

from alembic import op

revision = "filament_tech_properties"
down_revision = "filament_packagings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "filaments",
        sa.Column("technical_properties", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("filaments", "technical_properties")
