"""Add per-account operational limits.

Revision ID: user_limits
Revises: spool_batch_receipts
"""

import sqlalchemy as sa

from alembic import op

revision = "user_limits"
down_revision = "spool_batch_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_limits",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_limits_user"),
            primary_key=True,
        ),
        sa.Column("spool_batch_limit", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_limits")
