"""Add is_weighted to presets

Revision ID: add_is_weighted
Revises: a2b3c4d5e6f7
Create Date: 2025-11-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_is_weighted'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Добавляем колонку is_weighted в таблицу presets
    op.add_column('presets', sa.Column('is_weighted', sa.Boolean(), nullable=False, server_default='false'))
    # Создаем индекс для быстрого поиска
    op.create_index('ix_presets_is_weighted', 'presets', ['is_weighted'])


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index('ix_presets_is_weighted', table_name='presets')
    op.drop_column('presets', 'is_weighted')

