"""What a brand looks like on one market.

Revision ID: brand_cell_regional_profile
Revises: workspace_global_grants
Create Date: 2026-08-08

A representative describes the brand for their own market: its local wording,
and the social accounts people there actually use. The mark itself — name, logo —
stays global, and whether prices reach buyers is decided on the material.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "brand_cell_regional_profile"
down_revision: Union[str, None] = "workspace_global_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("brand_country_cells", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "brand_country_cells",
        sa.Column("social_media_urls", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("brand_country_cells", "social_media_urls")
    op.drop_column("brand_country_cells", "description")
