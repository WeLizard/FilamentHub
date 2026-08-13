"""enforce case-insensitive username identity

Revision ID: user_username_ci
Revises: orca_profile_identity
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "user_username_ci"
down_revision: str | None = "orca_profile_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_users_username_lower",
        "users",
        [sa.text("lower(username)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_username_lower", table_name="users")
