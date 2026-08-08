"""In which currency a brand prices on one market.

Revision ID: brand_cell_currency
Revises: active_organization
Create Date: 2026-08-08

The currency of a country can be derived from the country itself, so storing it
would be a copy — except that a brand does not always price in local money: a
Kazakh market may be quoted in dollars, a Serbian one in euro. That is a fact
about the market, not about the country, and only the brand knows it.

Each price keeps its own currency; this is the default the editor offers.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "brand_cell_currency"
down_revision: Union[str, None] = "active_organization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("brand_country_cells", sa.Column("currency", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("brand_country_cells", "currency")
