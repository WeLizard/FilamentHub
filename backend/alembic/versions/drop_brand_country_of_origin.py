"""Remove the brand country column added in error.

Revision ID: drop_brand_country
Revises: brand_country_of_origin
Create Date: 2026-08-07

A single country of origin was built while the actual requirement was the
opposite shape: one brand present in many countries, each with its own local
data and its own representative. The column never reached production; it is
dropped forward rather than by rewriting history, so a development database that
already applied it heals on the next start.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "drop_brand_country"
down_revision: Union[str, None] = "brand_country_of_origin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_brands_country", table_name="brands")
    op.drop_column("brands", "country")


def downgrade() -> None:
    op.add_column("brands", sa.Column("country", sa.String(length=2), nullable=True))
    op.create_index("ix_brands_country", "brands", ["country"])
