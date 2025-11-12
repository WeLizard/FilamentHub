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
    op.add_column('users', sa.Column('deleted_preset_rule', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column('users', 'deleted_preset_rule')



