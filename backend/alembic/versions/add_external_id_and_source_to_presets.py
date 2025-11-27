"""Add external_id and source to presets table

Revision ID: a1b2c3d4e5f8
Revises: a5b6c7d8e9f0
Create Date: 2025-11-12 23:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f8'
down_revision: Union[str, None] = 'f2b7c90864d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Добавляем поля external_id и source в таблицу presets
    op.add_column('presets', sa.Column('external_id', sa.String(length=200), nullable=True))
    op.add_column('presets', sa.Column('source', sa.String(length=50), nullable=True, server_default='user'))
    
    # Создаем индекс для external_id (для быстрого поиска по external_id)
    op.create_index('ix_presets_external_id', 'presets', ['external_id'], unique=False)
    
    # Создаем индекс для source (для фильтрации по источнику)
    op.create_index('ix_presets_source', 'presets', ['source'], unique=False)
    
    # Создаем составной индекс для поиска по external_id и user_id (для маппинга)
    op.create_index('ix_presets_external_id_user_id', 'presets', ['external_id', 'user_id'], unique=False)


def downgrade() -> None:
    """Downgrade database schema."""
    # Удаляем индексы
    op.drop_index('ix_presets_external_id_user_id', table_name='presets')
    op.drop_index('ix_presets_source', table_name='presets')
    op.drop_index('ix_presets_external_id', table_name='presets')
    
    # Удаляем колонки
    op.drop_column('presets', 'source')
    op.drop_column('presets', 'external_id')

