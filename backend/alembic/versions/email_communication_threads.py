"""Add administrative email communication threads.

Revision ID: email_communication_threads
Revises: brand_team_lifecycle
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "email_communication_threads"
down_revision: Union[str, None] = "brand_team_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_threads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invite_id", sa.Integer(), nullable=True),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("participant_email", sa.String(length=255), nullable=False),
        sa.Column("participant_name", sa.String(length=200), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("unread_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invite_id"], ["brand_invites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_id"),
    )
    op.create_index("ix_email_threads_brand_id", "email_threads", ["brand_id"])
    op.create_index("ix_email_threads_id", "email_threads", ["id"])
    op.create_index("ix_email_threads_invite_id", "email_threads", ["invite_id"])
    op.create_index("ix_email_threads_last_message_at", "email_threads", ["last_message_at"])
    op.create_index("ix_email_threads_participant_email", "email_threads", ["participant_email"])
    op.create_index("ix_email_threads_status", "email_threads", ["status"])

    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("sender_email", sa.String(length=255), nullable=False),
        sa.Column("recipient_emails", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=100), nullable=True),
        sa.Column("provider_event_id", sa.String(length=100), nullable=True),
        sa.Column("internet_message_id", sa.String(length=500), nullable=True),
        sa.Column("in_reply_to", sa.String(length=500), nullable=True),
        sa.Column("attachment_metadata", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("sent_by_id", sa.Integer(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sent_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thread_id"], ["email_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_messages_created_at", "email_messages", ["created_at"])
    op.create_index("ix_email_messages_direction", "email_messages", ["direction"])
    op.create_index("ix_email_messages_id", "email_messages", ["id"])
    op.create_index(
        "ix_email_messages_provider_event_id",
        "email_messages",
        ["provider_event_id"],
        unique=True,
    )
    op.create_index(
        "ix_email_messages_provider_message_id",
        "email_messages",
        ["provider_message_id"],
        unique=True,
    )
    op.create_index("ix_email_messages_sent_by_id", "email_messages", ["sent_by_id"])
    op.create_index("ix_email_messages_thread_id", "email_messages", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_email_messages_thread_id", table_name="email_messages")
    op.drop_index("ix_email_messages_sent_by_id", table_name="email_messages")
    op.drop_index("ix_email_messages_provider_message_id", table_name="email_messages")
    op.drop_index("ix_email_messages_provider_event_id", table_name="email_messages")
    op.drop_index("ix_email_messages_id", table_name="email_messages")
    op.drop_index("ix_email_messages_direction", table_name="email_messages")
    op.drop_index("ix_email_messages_created_at", table_name="email_messages")
    op.drop_table("email_messages")

    op.drop_index("ix_email_threads_status", table_name="email_threads")
    op.drop_index("ix_email_threads_participant_email", table_name="email_threads")
    op.drop_index("ix_email_threads_last_message_at", table_name="email_threads")
    op.drop_index("ix_email_threads_invite_id", table_name="email_threads")
    op.drop_index("ix_email_threads_id", table_name="email_threads")
    op.drop_index("ix_email_threads_brand_id", table_name="email_threads")
    op.drop_table("email_threads")
