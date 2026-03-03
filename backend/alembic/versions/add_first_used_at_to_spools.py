"""Add first_used_at column to user_spools

Revision ID: add_first_used_at
Revises: add_spool_price_and_tare
Create Date: 2026-03-03

Spoolman compatibility: track when a spool was first used separately
from last_used_at. Data migration sets first_used_at = created_at
for spools that have already been used.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_first_used_at'
down_revision: Union[str, None] = 'add_spool_price_and_tare'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_spools',
        sa.Column('first_used_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Data migration: for spools that have been used, set first_used_at to created_at
    op.execute(
        "UPDATE user_spools SET first_used_at = created_at WHERE last_used_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column('user_spools', 'first_used_at')
