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
    
    # 4. Создаем таблицу feedback
    op.create_table(
        'feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.Enum('bug', 'feature', 'question', 'other', name='feedbacktype'), nullable=False),
        sa.Column('subject', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('status', sa.Enum('open', 'in_progress', 'resolved', 'closed', name='feedbackstatus'), nullable=False, server_default='open'),
        sa.Column('admin_response', sa.Text(), nullable=True),
        sa.Column('admin_response_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('responded_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['responded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
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

