"""Add preset_locally_deleted to notificationtype enum

Revision ID: a5b6c7d8e9f0
Revises: f3e4d5c6b7a8
Create Date: 2025-01-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, None] = 'f3e4d5c6b7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Добавляем новое значение в enum notificationtype
    # В PostgreSQL нельзя удалить значение из enum, поэтому downgrade будет пустым
    # Используем IF NOT EXISTS через DO блок, так как ALTER TYPE ... ADD VALUE IF NOT EXISTS не поддерживается напрямую
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'preset_locally_deleted';
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade database schema."""
    # В PostgreSQL нельзя удалить значение из enum без пересоздания типа
    # Это сложная операция, которая требует временного переименования типа,
    # создания нового типа, обновления всех колонок и удаления старого типа
    # Для безопасности оставляем значение в enum
    # Если действительно нужно удалить, можно сделать это вручную через SQL
    pass

