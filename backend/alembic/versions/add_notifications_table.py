"""Add notifications table

Revision ID: add_notifications
Revises: add_is_weighted
Create Date: 2025-11-06 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_notifications'
down_revision: Union[str, None] = 'add_is_weighted'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Создаем enum notificationtype с проверкой существования
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE notificationtype AS ENUM (
                'preset_updated',
                'preset_deleted',
                'brand_verified',
                'brand_request_approved',
                'brand_request_rejected'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Создаем таблицу notifications через SQL напрямую, чтобы избежать проблем с ENUM
    # SQLAlchemy не видит ENUM, созданный через op.execute() в той же транзакции
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            type notificationtype NOT NULL,
            title VARCHAR(200) NOT NULL,
            message TEXT NOT NULL,
            link VARCHAR(500),
            extra_data JSONB,
            read BOOLEAN NOT NULL DEFAULT false,
            read_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    """)
    
    # Создаем индексы
    op.create_index('ix_notifications_id', 'notifications', ['id'])
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_type', 'notifications', ['type'])
    op.create_index('ix_notifications_read', 'notifications', ['read'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_index('ix_notifications_read', table_name='notifications')
    op.drop_index('ix_notifications_type', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_index('ix_notifications_id', table_name='notifications')
    op.drop_table('notifications')
    
    # Удаляем enum (только если не используется другими таблицами)
    op.execute("DROP TYPE IF EXISTS notificationtype")

