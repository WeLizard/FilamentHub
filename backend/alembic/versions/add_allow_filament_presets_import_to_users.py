"""Add allow_filament_presets_import to users table

Revision ID: b2c3d4e5f6a9
Revises: a1b2c3d4e5f8
Create Date: 2025-11-12 23:51:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a9'
down_revision: Union[str, None] = 'a1b2c3d4e5f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Добавляем поле allow_filament_presets_import в таблицу users
    # По умолчанию True (разрешено импортировать filament presets)
    op.add_column('users', sa.Column('allow_filament_presets_import', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    """Downgrade database schema."""
    # Удаляем колонку
    op.drop_column('users', 'allow_filament_presets_import')



