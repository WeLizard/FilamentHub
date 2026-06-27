"""add_brand_logo_bg

Revision ID: add_brand_logo_bg
Revises: add_filament_price_display_unit
Create Date: 2026-06-27 00:00:00.000000

Adds brands.logo_bg so a brand can set a background colour behind its logo
(prevents transparent PNG/SVG logos from disappearing on the dark theme).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'add_brand_logo_bg'
down_revision: Union[str, None] = 'add_filament_price_display_unit'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable logo_bg column."""
    op.add_column('brands', sa.Column('logo_bg', sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Drop logo_bg column."""
    op.drop_column('brands', 'logo_bg')
