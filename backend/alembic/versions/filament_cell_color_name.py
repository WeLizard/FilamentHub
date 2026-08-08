"""The colour is what a buyer in another country has to read.

Revision ID: filament_cell_color_name
Revises: brand_cell_regional_profile
Create Date: 2026-08-08

Manufacturers do not translate the name of a product: "Jade White" is a name,
and it stays the same everywhere. What our catalogue holds in the colour field
is not a name but a plain word — "Красный", "Синий" — and that is exactly what
somebody in Germany needs to read in their own language.

So the country layer stops overriding the product name and overrides the colour
instead.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "filament_cell_color_name"
down_revision: Union[str, None] = "brand_cell_regional_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "filament_country_cells", "market_display_name", new_column_name="market_color_name"
    )


def downgrade() -> None:
    op.alter_column(
        "filament_country_cells", "market_color_name", new_column_name="market_display_name"
    )
