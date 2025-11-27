"""Add badges to users

Revision ID: add_badges_to_users
Revises: f2b7c90864d4
Create Date: 2025-11-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision: str = 'add_badges_to_users'
down_revision: Union[str, None] = 'f2b7c90864d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Добавляем колонку badges в таблицу users
    op.add_column('users', sa.Column('badges', JSON, nullable=True))


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column('users', 'badges')



