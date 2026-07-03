"""add user pro_access and pro_expires_at

Revision ID: add_user_pro_access
Revises: add_brand_invites
Create Date: 2026-07-03

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_user_pro_access"
down_revision: Union[str, None] = "add_brand_invites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column(
        "users",
        sa.Column("pro_access", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("pro_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("users", "pro_expires_at")
    op.drop_column("users", "pro_access")
