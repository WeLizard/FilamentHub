"""Country cells for brands and filaments.

Revision ID: country_cells
Revises: drop_brand_country
Create Date: 2026-08-08

One global record still describes one physical product; a country never creates a
copy of it. These tables carry only what actually differs by market: where a
brand is present, and on what terms a filament is sold there.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "country_cells"
down_revision: Union[str, None] = "drop_brand_country"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand_country_cells",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("shop_links", sa.JSON(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "country", name="uq_brand_country_cell"),
    )
    op.create_index("ix_brand_cells_brand", "brand_country_cells", ["brand_id"])
    op.create_index("ix_brand_cells_country", "brand_country_cells", ["country"])
    op.create_index("ix_brand_cells_published", "brand_country_cells", ["published"])

    availability = sa.Enum(
        "available", "unavailable", "unknown", name="country_availability"
    )
    availability.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "filament_country_cells",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filament_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("availability", availability, nullable=False, server_default="unknown"),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("price_display_unit", sa.String(length=16), nullable=True),
        sa.Column("product_url", sa.String(length=500), nullable=True),
        sa.Column("purchase_links", sa.JSON(), nullable=True),
        sa.Column("market_note", sa.Text(), nullable=True),
        sa.Column("market_display_name", sa.String(length=200), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("price_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["filament_id"], ["filaments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["price_updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filament_id", "country", name="uq_filament_country_cell"),
        # Цена без валюты унаследовала бы валюту бренда: сербская цена в рублях.
        sa.CheckConstraint(
            "(price IS NULL) = (currency IS NULL)", name="ck_filament_cell_price_currency_pair"
        ),
    )
    op.create_index("ix_filament_cells_filament", "filament_country_cells", ["filament_id"])
    op.create_index("ix_filament_cells_country", "filament_country_cells", ["country"])
    op.create_index("ix_filament_cells_published", "filament_country_cells", ["published"])


def downgrade() -> None:
    op.drop_table("filament_country_cells")
    sa.Enum(name="country_availability").drop(op.get_bind(), checkfirst=True)
    op.drop_table("brand_country_cells")
