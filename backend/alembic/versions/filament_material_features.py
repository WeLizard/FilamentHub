"""Store structured filament additives and functional property claims.

Revision ID: filament_material_features
Revises: author_optional_delete
Create Date: 2026-07-29
"""

import sqlalchemy as sa

from alembic import op

revision = "filament_material_features"
down_revision = "author_optional_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "filaments",
        sa.Column("additives", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "filaments",
        sa.Column("property_claims", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("filaments", "property_claims")
    op.drop_column("filaments", "additives")
