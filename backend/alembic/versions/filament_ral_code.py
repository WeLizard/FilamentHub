"""Add an optional normalized RAL Classic code to catalog filaments.

Revision ID: filament_ral_code
Revises: filament_material_features
Create Date: 2026-07-29
"""

import sqlalchemy as sa

from alembic import op

revision = "filament_ral_code"
down_revision = "filament_material_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filaments", sa.Column("ral_code", sa.String(length=4), nullable=True))
    op.create_index("ix_filaments_ral_code", "filaments", ["ral_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_filaments_ral_code", table_name="filaments")
    op.drop_column("filaments", "ral_code")
