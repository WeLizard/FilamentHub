"""Add feedback table and admin_message to notificationtype enum

Revision ID: feedback_table_enum
Revises: sync_enabled_user_saved
Create Date: 2025-01-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'feedback_table_enum'
down_revision: Union[str, None] = 'sync_enabled_user_saved'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # 1. Добавляем новое значение 'admin_message' в enum notificationtype
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'admin_message';
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # 2. Создаем enum для FeedbackType
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE feedbacktype AS ENUM ('bug', 'feature', 'question', 'other');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # 3. Создаем enum для FeedbackStatus
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE feedbackstatus AS ENUM ('open', 'in_progress', 'resolved', 'closed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # 4. Создаем таблицу feedback через SQL напрямую, чтобы избежать проблем с ENUM
    # SQLAlchemy не видит ENUM, созданный через op.execute() в той же транзакции
    op.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            type feedbacktype NOT NULL,
            subject VARCHAR(200) NOT NULL,
            message TEXT NOT NULL,
            email VARCHAR(255),
            status feedbackstatus NOT NULL DEFAULT 'open',
            admin_response TEXT,
            admin_response_at TIMESTAMP WITH TIME ZONE,
            responded_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    """)
    
    # 5. Создаем индексы
    op.create_index('ix_feedback_id', 'feedback', ['id'])
    op.create_index('ix_feedback_user_id', 'feedback', ['user_id'])
    op.create_index('ix_feedback_type', 'feedback', ['type'])
    op.create_index('ix_feedback_status', 'feedback', ['status'])
    op.create_index('ix_feedback_created_at', 'feedback', ['created_at'])


def downgrade() -> None:
    """Downgrade database schema."""
    # Удаляем индексы
    op.drop_index('ix_feedback_created_at', table_name='feedback')
    op.drop_index('ix_feedback_status', table_name='feedback')
    op.drop_index('ix_feedback_type', table_name='feedback')
    op.drop_index('ix_feedback_user_id', table_name='feedback')
    op.drop_index('ix_feedback_id', table_name='feedback')
    
    # Удаляем таблицу
    op.drop_table('feedback')
    
    # Удаляем enums (опционально, т.к. может использоваться другими таблицами)
    # В PostgreSQL нельзя удалить значение из enum без пересоздания типа
    # Оставляем 'admin_message' в enum для безопасности
    op.execute("DROP TYPE IF EXISTS feedbackstatus")
    op.execute("DROP TYPE IF EXISTS feedbacktype")

