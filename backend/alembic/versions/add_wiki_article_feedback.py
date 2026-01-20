"""Add wiki_article_feedback table

Revision ID: add_wiki_feedback
Revises: change_tags_to_json
Create Date: 2025-01-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_wiki_feedback'
down_revision: Union[str, None] = 'change_tags_to_json'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add wiki_article_feedback table."""

    # 1. Создаем enum для WikiFeedbackType
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE wikifeedbacktype AS ENUM ('helpful', 'feedback');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # 2. Создаем таблицу wiki_article_feedback
    op.create_table(
        'wiki_article_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('feedback_type', sa.Enum('helpful', 'feedback', name='wikifeedbacktype'), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('anonymous_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['wiki_articles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('article_id', 'user_id', 'feedback_type', name='uq_wiki_feedback_user_article_type')
    )

    # 3. Создаем индексы
    op.create_index(op.f('ix_wiki_article_feedback_article_id'), 'wiki_article_feedback', ['article_id'], unique=False)
    op.create_index(op.f('ix_wiki_article_feedback_user_id'), 'wiki_article_feedback', ['user_id'], unique=False)
    op.create_index(op.f('ix_wiki_article_feedback_feedback_type'), 'wiki_article_feedback', ['feedback_type'], unique=False)
    op.create_index(op.f('ix_wiki_article_feedback_anonymous_id'), 'wiki_article_feedback', ['anonymous_id'], unique=False)
    op.create_index(op.f('ix_wiki_article_feedback_id'), 'wiki_article_feedback', ['id'], unique=False)


def downgrade() -> None:
    """Remove wiki_article_feedback table."""

    # Удаляем индексы
    op.drop_index(op.f('ix_wiki_article_feedback_id'), table_name='wiki_article_feedback')
    op.drop_index(op.f('ix_wiki_article_feedback_anonymous_id'), table_name='wiki_article_feedback')
    op.drop_index(op.f('ix_wiki_article_feedback_feedback_type'), table_name='wiki_article_feedback')
    op.drop_index(op.f('ix_wiki_article_feedback_user_id'), table_name='wiki_article_feedback')
    op.drop_index(op.f('ix_wiki_article_feedback_article_id'), table_name='wiki_article_feedback')

    # Удаляем таблицу
    op.drop_table('wiki_article_feedback')

    # Удаляем enum
    op.execute("DROP TYPE IF EXISTS wikifeedbacktype")
