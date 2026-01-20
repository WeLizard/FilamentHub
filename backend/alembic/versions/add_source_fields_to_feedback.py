"""Add source fields to feedback table

Revision ID: add_feedback_source
Revises: add_wiki_feedback
Create Date: 2025-01-20 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_feedback_source'
down_revision: Union[str, None] = 'add_wiki_feedback'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add source, source_url, source_id fields to feedback table."""
    # Проверяем существование колонок перед добавлением
    conn = op.get_bind()

    # Проверяем source
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'feedback' AND column_name = 'source')"
    ))
    if not result.scalar():
        op.add_column('feedback', sa.Column('source', sa.String(50), nullable=True))
        op.create_index('ix_feedback_source', 'feedback', ['source'])

    # Проверяем source_url
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'feedback' AND column_name = 'source_url')"
    ))
    if not result.scalar():
        op.add_column('feedback', sa.Column('source_url', sa.String(500), nullable=True))

    # Проверяем source_id
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'feedback' AND column_name = 'source_id')"
    ))
    if not result.scalar():
        op.add_column('feedback', sa.Column('source_id', sa.Integer(), nullable=True))
        op.create_index('ix_feedback_source_id', 'feedback', ['source_id'])


def downgrade() -> None:
    """Remove source fields from feedback table."""
    op.drop_index('ix_feedback_source_id', table_name='feedback')
    op.drop_index('ix_feedback_source', table_name='feedback')
    op.drop_column('feedback', 'source_id')
    op.drop_column('feedback', 'source_url')
    op.drop_column('feedback', 'source')
