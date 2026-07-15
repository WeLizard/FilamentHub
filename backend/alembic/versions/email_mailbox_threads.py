"""Extend administrative email threads into a mailbox.

Revision ID: email_mailbox_threads
Revises: active_brand_membership_only
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "email_mailbox_threads"
down_revision: Union[str, None] = "active_brand_membership_only"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_threads",
        sa.Column("reply_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "email_threads",
        sa.Column("sender_profile", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_email_threads_reply_token",
        "email_threads",
        ["reply_token"],
        unique=True,
    )
    op.add_column(
        "email_messages",
        sa.Column("delivery_status", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_messages", "delivery_status")
    op.drop_index("ix_email_threads_reply_token", table_name="email_threads")
    op.drop_column("email_threads", "sender_profile")
    op.drop_column("email_threads", "reply_token")
