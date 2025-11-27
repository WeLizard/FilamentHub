"""rename_sync_enabled_to_sync

Revision ID: 0de996edecbd
Revises: 9536db2100dd
Create Date: 2025-11-23 22:35:52.266178

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0de996edecbd'
down_revision: Union[str, None] = '9536db2100dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Переименовываем sync_enabled → sync в таблице user_saved_presets
    op.alter_column('user_saved_presets', 'sync_enabled', new_column_name='sync')


def downgrade() -> None:
    """Downgrade database schema."""
    # Откат: переименовываем обратно sync → sync_enabled
    op.alter_column('user_saved_presets', 'sync', new_column_name='sync_enabled')

