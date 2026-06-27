"""add_brand_profile_fields

Revision ID: add_brand_profile_fields
Revises: add_filament_availability
Create Date: 2026-06-26 00:00:00.000000

Adds brand profile fields: social_media_urls, shop_links, currency, price_hidden.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'add_brand_profile_fields'
down_revision: Union[str, None] = 'add_filament_availability'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add brand profile and pricing columns (backward-compatible defaults)."""
    op.add_column('brands', sa.Column('social_media_urls', sa.JSON(), nullable=True))
    op.add_column('brands', sa.Column('shop_links', sa.JSON(), nullable=True))
    op.add_column(
        'brands',
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='RUB'),
    )
    op.add_column(
        'brands',
        sa.Column('price_hidden', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    """Drop brand profile and pricing columns."""
    op.drop_column('brands', 'price_hidden')
    op.drop_column('brands', 'currency')
    op.drop_column('brands', 'shop_links')
    op.drop_column('brands', 'social_media_urls')
