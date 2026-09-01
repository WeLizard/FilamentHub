"""Add private personal label-layout presets.

Revision ID: personal_label_preset
Revises: spool_tag_identity
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "personal_label_preset"
down_revision = "spool_tag_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_label_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "name", name="uq_user_label_preset_name"),
    )


def downgrade() -> None:
    op.drop_table("user_label_presets")
