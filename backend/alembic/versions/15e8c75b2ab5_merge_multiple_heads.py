"""merge_multiple_heads

Revision ID: 15e8c75b2ab5
Revises: feedback_table_enum, add_last_sync_at_to_users, a1b2c3d4e5f9, c3d4e5f6a7b0, e01bc3b29297
Create Date: 2025-11-23 15:07:59.950446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15e8c75b2ab5'
down_revision: Union[str, None] = ('feedback_table_enum', 'add_last_sync_at_to_users', 'a1b2c3d4e5f9', 'c3d4e5f6a7b0', 'e01bc3b29297')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass

