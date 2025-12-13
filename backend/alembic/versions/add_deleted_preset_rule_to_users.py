"""Add deleted_preset_rule to users

Revision ID: f3e4d5c6b7a8
Revises: 4de32f3e4fc1
Create Date: 2025-01-27 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3e4d5c6b7a8'
down_revision: Union[str, None] = '4de32f3e4fc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Добавляем колонку deleted_preset_rule, используя прямой SQL
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS deleted_preset_rule VARCHAR(50);
    """)


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column('users', 'deleted_preset_rule')



