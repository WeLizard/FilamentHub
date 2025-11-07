"""Add bad_words table

Revision ID: add_bad_words
Revises: add_notifications
Create Date: 2025-01-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_bad_words'
down_revision: Union[str, None] = 'add_notifications'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Создаем таблицу bad_words
    op.create_table(
        'bad_words',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('word', sa.String(length=100), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False, server_default='ru'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Создаем индексы
    op.create_index('ix_bad_words_id', 'bad_words', ['id'])
    op.create_index('ix_bad_words_word', 'bad_words', ['word'], unique=True)
    op.create_index('ix_bad_words_language', 'bad_words', ['language'])


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index('ix_bad_words_language', table_name='bad_words')
    op.drop_index('ix_bad_words_word', table_name='bad_words')
    op.drop_index('ix_bad_words_id', table_name='bad_words')
    op.drop_table('bad_words')

