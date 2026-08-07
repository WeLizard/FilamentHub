"""Where a brand is from.

Revision ID: brand_country_of_origin
Revises: timestamps_carry_timezone
Create Date: 2026-08-07

Origin only, and deliberately a single value: Creality is from China and sells in
the CIS, Europe and the United States all the same. Where a brand is present, on
what terms and at what price is a different model that does not exist yet, and
this column must not be mistaken for it.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "brand_country_of_origin"
down_revision: Union[str, None] = "timestamps_carry_timezone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("country", sa.String(length=2), nullable=True))
    op.create_index("ix_brands_country", "brands", ["country"])


def downgrade() -> None:
    op.drop_index("ix_brands_country", table_name="brands")
    op.drop_column("brands", "country")
