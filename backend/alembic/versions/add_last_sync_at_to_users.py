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
    # Добавляем колонку last_sync_at в таблицу users, используя прямой SQL
    # Разделяем на отдельные команды, т.к. asyncpg не поддерживает множественные команды в одном prepared statement
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMP WITH TIME ZONE;
    """)
    
    # Добавляем комментарий отдельной командой
    op.execute("""
        COMMENT ON COLUMN users.last_sync_at IS 'Время последней синхронизации с OrcaSlicer';
    """)


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column('users', 'last_sync_at')

