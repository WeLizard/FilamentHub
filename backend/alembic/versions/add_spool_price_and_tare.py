"""Add price to user_spools and empty_spool_weight_g to filaments

Revision ID: add_spool_price_and_tare
Revises: add_extra_to_user_spools
Create Date: 2026-03-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_spool_price_and_tare"
down_revision: Union[str, None] = "add_extra_to_user_spools"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_spools", sa.Column("price", sa.Float(), nullable=True))
    op.add_column("filaments", sa.Column("empty_spool_weight_g", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("filaments", "empty_spool_weight_g")
    op.drop_column("user_spools", "price")
