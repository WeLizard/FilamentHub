"""add_sync_enabled_to_user_saved_presets

Revision ID: add_sync_enabled_to_user_saved_presets
Revises: add_sync_enabled_to_presets
Create Date: 2024-01-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'sync_enabled_user_saved'  # Сокращено до 23 символов (лимит 32)
down_revision: Union[str, None] = 'add_sync_enabled_to_presets'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле sync_enabled в таблицу user_saved_presets
    op.add_column(
        'user_saved_presets',
        sa.Column('sync_enabled', sa.Boolean(), nullable=False, server_default='true')
    )
    
    # Создаем индекс для sync_enabled (для быстрой фильтрации при синхронизации)
    op.create_index('ix_user_saved_presets_sync_enabled', 'user_saved_presets', ['sync_enabled'], unique=False)
    
    # Создаем записи в user_saved_presets для всех существующих созданных пресетов
    # Это нужно для миграции данных - все созданные пресеты должны быть в user_saved_presets
    connection = op.get_bind()
    
    # SQL запрос для создания записей в user_saved_presets для всех пресетов, где preset.user_id != NULL
    # и еще нет записи в user_saved_presets
    connection.execute(sa.text("""
        INSERT INTO user_saved_presets (user_id, preset_id, saved_at, sync_enabled)
        SELECT p.user_id, p.id, p.created_at, true
        FROM presets p
        WHERE p.user_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM user_saved_presets usp
            WHERE usp.user_id = p.user_id AND usp.preset_id = p.id
        )
    """))


def downgrade() -> None:
    # Удаляем индекс
    op.drop_index('ix_user_saved_presets_sync_enabled', table_name='user_saved_presets')
    
    # Удаляем поле sync_enabled из таблицы user_saved_presets
    op.drop_column('user_saved_presets', 'sync_enabled')

