"""Add OAuth fields to users table

Revision ID: c5d3a7b92e04
Revises: b4e2f9a71c03
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5d3a7b92e04"
down_revision: Union[str, None] = "b4e2f9a71c03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oauth_provider", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("oauth_provider_id", sa.String(255), nullable=True))
    # Make password_hash nullable (OAuth users don't have passwords)
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
    op.drop_column("users", "oauth_provider_id")
    op.drop_column("users", "oauth_provider")
