"""Add preset_id to reviews and success_rate to presets

Revision ID: a2b3c4d5e6f7
Revises: 97585b264440
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = '5752bb11b46d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Проверяем существование колонки preset_id в filament_reviews
    filament_reviews_columns = [col['name'] for col in inspector.get_columns('filament_reviews')]
    
    if 'preset_id' not in filament_reviews_columns:
        # Добавляем preset_id в filament_reviews
        op.add_column('filament_reviews', sa.Column('preset_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_filament_reviews_preset_id'), 'filament_reviews', ['preset_id'], unique=False)
        op.create_foreign_key(
            'filament_reviews_preset_id_fkey',  # Используем стандартное имя для совместимости
            'filament_reviews', 'presets',
            ['preset_id'], ['id'],
            ondelete='SET NULL'
        )
    else:
        # Колонка уже существует, проверяем индекс и foreign key
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('filament_reviews')]
        if 'ix_filament_reviews_preset_id' not in existing_indexes:
            op.create_index(op.f('ix_filament_reviews_preset_id'), 'filament_reviews', ['preset_id'], unique=False)
        
        existing_fks = [fk['name'] for fk in inspector.get_foreign_keys('filament_reviews')]
        if 'filament_reviews_preset_id_fkey' not in existing_fks:
            op.create_foreign_key(
                'filament_reviews_preset_id_fkey',
                'filament_reviews', 'presets',
                ['preset_id'], ['id'],
                ondelete='SET NULL'
            )
    
    # Проверяем существование колонки success_rate в presets
    presets_columns = [col['name'] for col in inspector.get_columns('presets')]
    
    if 'success_rate' not in presets_columns:
        # Добавляем success_rate в presets
        op.add_column('presets', sa.Column('success_rate', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade database schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Удаляем success_rate из presets (если существует)
    presets_columns = [col['name'] for col in inspector.get_columns('presets')]
    if 'success_rate' in presets_columns:
        op.drop_column('presets', 'success_rate')
    
    # Удаляем preset_id из filament_reviews (если существует)
    filament_reviews_columns = [col['name'] for col in inspector.get_columns('filament_reviews')]
    if 'preset_id' in filament_reviews_columns:
        # Удаляем foreign key (пробуем оба возможных имени)
        existing_fks = [fk['name'] for fk in inspector.get_foreign_keys('filament_reviews')]
        if 'filament_reviews_preset_id_fkey' in existing_fks:
            op.drop_constraint('filament_reviews_preset_id_fkey', 'filament_reviews', type_='foreignkey')
        elif 'fk_filament_reviews_preset_id' in existing_fks:
            op.drop_constraint('fk_filament_reviews_preset_id', 'filament_reviews', type_='foreignkey')
        
        # Удаляем индекс
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('filament_reviews')]
        if 'ix_filament_reviews_preset_id' in existing_indexes:
            op.drop_index(op.f('ix_filament_reviews_preset_id'), table_name='filament_reviews')
        
        # Удаляем колонку
        op.drop_column('filament_reviews', 'preset_id')

