"""remove_presets_sync_enabled

Revision ID: 9536db2100dd
Revises: 15e8c75b2ab5
Create Date: 2025-11-23 22:34:58.754221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9536db2100dd'
down_revision: Union[str, None] = '15e8c75b2ab5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Удаляем колонку sync_enabled из таблицы presets
    # Теперь синхронизация управляется ТОЛЬКО через user_saved_presets.sync_enabled
    op.drop_column('presets', 'sync_enabled')


def downgrade() -> None:
    """Downgrade database schema."""
    # Восстанавливаем колонку sync_enabled (на случай отката)
    op.add_column('presets', sa.Column('sync_enabled', sa.Boolean(), nullable=False, server_default='true'))

