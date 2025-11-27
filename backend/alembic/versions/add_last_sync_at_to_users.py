"""Add last_sync_at to users

Revision ID: add_last_sync_at_to_users
Revises: add_badges_to_users
Create Date: 2025-11-22 08:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_last_sync_at_to_users'
down_revision: Union[str, None] = 'add_badges_to_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Добавляем колонку last_sync_at в таблицу users
    op.add_column(
        'users',
        sa.Column(
            'last_sync_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Время последней синхронизации с OrcaSlicer'
        )
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column('users', 'last_sync_at')

