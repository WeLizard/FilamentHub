"""store Wiki guide completion in the user account

Revision ID: wiki_guide_progress
Revises: wiki_article_identity
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "wiki_guide_progress"
down_revision: str | None = "wiki_article_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wiki_guide_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("guide_id", sa.String(length=96), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "guide_id",
            name="uq_wiki_guide_progress_user_guide",
        ),
    )
    op.create_index(
        "ix_wiki_guide_progress_user_id",
        "wiki_guide_progress",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wiki_guide_progress_user_id",
        table_name="wiki_guide_progress",
    )
    op.drop_table("wiki_guide_progress")
