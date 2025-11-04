"""add_visual_settings_to_filaments

Revision ID: 7d567a4a6107
Revises: 962108c85ee3
Create Date: 2025-11-03 16:54:13.857206

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d567a4a6107'
down_revision: Union[str, None] = '962108c85ee3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Проверяем, существует ли колонка visual_settings
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    columns = [col['name'] for col in inspector.get_columns('filaments')]
    
    # Добавляем поле visual_settings (JSON) для расширенных визуальных эффектов, если его еще нет
    if 'visual_settings' not in columns:
        op.add_column(
            'filaments',
            sa.Column('visual_settings', sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade database schema."""
    # Удаляем поле visual_settings
    op.drop_column('filaments', 'visual_settings')

