"""add_sync_enabled_to_presets

Revision ID: add_sync_enabled_to_presets
Revises: add_external_id_and_source_to_presets
Create Date: 2024-01-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_sync_enabled_to_presets'
down_revision: Union[str, None] = 'a1b2c3d4e5f8'  # add_external_id_and_source_to_presets
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле sync_enabled в таблицу presets
    op.add_column(
        'presets',
        sa.Column('sync_enabled', sa.Boolean(), nullable=False, server_default='true')
    )
    
    # Создаем индекс для sync_enabled (для быстрой фильтрации при синхронизации)
    op.create_index('ix_presets_sync_enabled', 'presets', ['sync_enabled'], unique=False)


def downgrade() -> None:
    # Удаляем индекс
    op.drop_index('ix_presets_sync_enabled', table_name='presets')
    
    # Удаляем поле sync_enabled из таблицы presets
    op.drop_column('presets', 'sync_enabled')

