"""Mark accounts a provider sign-in created before any document was accepted.

Revision ID: user_provisional_since
Revises: quote_market_details
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from alembic import op

revision = "user_provisional_since"
down_revision = "quote_market_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("provisional_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_provisional_since",
        "users",
        ["provisional_since"],
        unique=False,
        postgresql_where=sa.text("provisional_since IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_provisional_since", table_name="users")
    op.drop_column("users", "provisional_since")
