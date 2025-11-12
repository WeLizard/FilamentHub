"""add_user_sync_settings_fields

Revision ID: 4de32f3e4fc1
Revises: 9c0a8d1ab3ab
Create Date: 2025-11-12 11:03:05.009259

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4de32f3e4fc1'
down_revision: Union[str, None] = '9c0a8d1ab3ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Добавляем поля настроек синхронизации в таблицу users
    op.add_column('users', sa.Column('allow_printer_profiles_import', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('allow_printer_profiles_export', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('allow_print_profiles_import', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('allow_print_profiles_export', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    """Downgrade database schema."""
    # Удаляем поля настроек синхронизации
    op.drop_column('users', 'allow_print_profiles_export')
    op.drop_column('users', 'allow_print_profiles_import')
    op.drop_column('users', 'allow_printer_profiles_export')
    op.drop_column('users', 'allow_printer_profiles_import')

