"""add stable multilingual identity to Wiki articles

Revision ID: wiki_article_identity
Revises: user_username_ci
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "wiki_article_identity"
down_revision: str | None = "user_username_ci"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wiki_articles",
        sa.Column("content_key", sa.String(length=200), nullable=True),
    )
    op.execute("UPDATE wiki_articles SET content_key = slug")
    op.execute(
        "UPDATE wiki_articles "
        "SET content_key = 'from-spool-to-print' "
        "WHERE slug IN ('from-spool-to-print', 'from-spool-to-print-en', 'from-spool-to-print-zh')"
    )
    op.alter_column("wiki_articles", "content_key", nullable=False)
    op.create_index(
        "ix_wiki_articles_content_key",
        "wiki_articles",
        ["content_key"],
    )
    op.create_unique_constraint(
        "uq_wiki_article_content_key_language",
        "wiki_articles",
        ["content_key", "language"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_wiki_article_content_key_language",
        "wiki_articles",
        type_="unique",
    )
    op.drop_index("ix_wiki_articles_content_key", table_name="wiki_articles")
    op.drop_column("wiki_articles", "content_key")
