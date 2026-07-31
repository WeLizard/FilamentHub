"""Add ordered messages to feedback conversations.

Revision ID: feedback_thread_messages
Revises: filament_ral_code
Create Date: 2026-07-31
"""

import sqlalchemy as sa

from alembic import op

revision = "feedback_thread_messages"
down_revision = "filament_ral_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_feedback_updated_at",
        "feedback",
        ["updated_at"],
        unique=False,
    )
    op.create_table(
        "feedback_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feedback_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column("author_type", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id"],
            ["feedback.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feedback_id",
            "author_user_id",
            "idempotency_key",
            name="uq_fb_msg_idempotency",
        ),
    )
    op.create_index(
        "ix_fb_msg_thread",
        "feedback_messages",
        ["feedback_id", "created_at", "id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO feedback_messages (
            feedback_id,
            author_user_id,
            author_type,
            message,
            idempotency_key,
            created_at
        )
        SELECT
            id,
            user_id,
            'user',
            message,
            NULL,
            created_at
        FROM feedback
        """
    )
    op.execute(
        """
        INSERT INTO feedback_messages (
            feedback_id,
            author_user_id,
            author_type,
            message,
            idempotency_key,
            created_at
        )
        SELECT
            id,
            responded_by,
            'admin',
            admin_response,
            NULL,
            COALESCE(admin_response_at, updated_at, created_at)
        FROM feedback
        WHERE admin_response IS NOT NULL
          AND TRIM(admin_response) <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("ix_fb_msg_thread", table_name="feedback_messages")
    op.drop_table("feedback_messages")
    op.drop_index("ix_feedback_updated_at", table_name="feedback")
