"""Add images attached to feedback messages.

Revision ID: feedback_attachments
Revises: filament_duplicate_reviews
"""

import sqlalchemy as sa

from alembic import op

revision = "feedback_attachments"
down_revision = "filament_duplicate_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_message_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey(
                "feedback_messages.id",
                ondelete="CASCADE",
                name="fk_fb_attach_message",
            ),
            nullable=False,
        ),
        sa.Column("public_id", sa.String(32), nullable=False),
        sa.Column("storage_path", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(32), nullable=False, server_default="image/webp"),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("public_id", name="uq_fb_attach_public_id"),
    )
    op.create_index("ix_fb_attach_message", "feedback_message_attachments", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_fb_attach_message", table_name="feedback_message_attachments")
    op.drop_table("feedback_message_attachments")
