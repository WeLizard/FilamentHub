"""The country an applicant is asking for.

Revision ID: brand_request_country
Revises: brand_grants
Create Date: 2026-08-08

Both entrances to a territorial grant now carry a country: an application says
which market it is asking for, and approval turns that into the grant itself.
Empty means the applicant is asking for the global scope, which is still only
ever given by a separate decision.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "brand_request_country"
down_revision: Union[str, None] = "brand_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("brand_requests", sa.Column("country", sa.String(length=2), nullable=True))
    op.create_index("ix_brand_requests_country", "brand_requests", ["country"])


def downgrade() -> None:
    op.drop_index("ix_brand_requests_country", table_name="brand_requests")
    op.drop_column("brand_requests", "country")
