"""add_user_avatar

Revision ID: add_user_avatar
Revises: add_filament_lines
Create Date: 2026-06-29 00:00:00.000000

Adds users.avatar_url for a user-uploaded profile avatar.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'add_user_avatar'
down_revision: Union[str, None] = 'add_filament_lines'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable avatar_url column."""
    op.add_column('users', sa.Column('avatar_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Drop avatar_url column."""
    op.drop_column('users', 'avatar_url')
