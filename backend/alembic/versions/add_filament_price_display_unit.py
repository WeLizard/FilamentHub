"""add_filament_price_display_unit

Revision ID: add_filament_price_display_unit
Revises: add_brand_profile_fields
Create Date: 2026-06-27 00:00:00.000000

Adds filaments.price_display_unit so the brand's chosen price unit
(per_kg / per_spool) is preserved and shown as the primary price.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'add_filament_price_display_unit'
down_revision: Union[str, None] = 'add_brand_profile_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add price_display_unit column (backward-compatible default per_kg)."""
    op.add_column(
        'filaments',
        sa.Column(
            'price_display_unit',
            sa.String(length=10),
            nullable=False,
            server_default='per_kg',
        ),
    )


def downgrade() -> None:
    """Drop price_display_unit column."""
    op.drop_column('filaments', 'price_display_unit')
