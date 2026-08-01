"""Add Wiki content spaces, revisions, and peer reviews.

Revision ID: wiki_spaces_revisions
Revises: orca_unique_external_id
Create Date: 2026-08-01
"""

import sqlalchemy as sa

from alembic import op

revision = "wiki_spaces_revisions"
down_revision = "orca_unique_external_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wiki_spaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "allows_community_authors",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_wiki_spaces_key"),
    )
    op.create_index("ix_wiki_spaces_key", "wiki_spaces", ["key"])
    spaces = sa.table(
        "wiki_spaces",
        sa.column("id", sa.Integer()),
        sa.column("key", sa.String()),
        sa.column("order", sa.Integer()),
        sa.column("allows_community_authors", sa.Boolean()),
    )
    op.bulk_insert(
        spaces,
        [
            {"id": 1, "key": "guides", "order": 0, "allows_community_authors": False},
            {"id": 2, "key": "knowledge", "order": 10, "allows_community_authors": True},
        ],
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "SELECT setval(pg_get_serial_sequence('wiki_spaces', 'id'), 2, true)"
        )

    op.add_column(
        "wiki_articles",
        sa.Column("space_id", sa.Integer(), server_default="2", nullable=True),
    )
    op.add_column(
        "wiki_articles",
        sa.Column("language", sa.String(length=8), server_default="ru", nullable=False),
    )
    op.add_column(
        "wiki_articles",
        sa.Column(
            "provenance", sa.String(length=32), server_default="editorial", nullable=False
        ),
    )
    op.create_foreign_key(
        "fk_wiki_articles_space",
        "wiki_articles",
        "wiki_spaces",
        ["space_id"],
        ["id"],
    )
    op.create_index("ix_wiki_articles_space", "wiki_articles", ["space_id"])
    op.create_index("ix_wiki_articles_language", "wiki_articles", ["language"])
    op.create_index("ix_wiki_articles_provenance", "wiki_articles", ["provenance"])
    op.execute("UPDATE wiki_articles SET space_id = 2 WHERE space_id IS NULL")
    op.alter_column("wiki_articles", "space_id", nullable=False, server_default="2")

    op.create_table(
        "wiki_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("base_revision_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column(
            "authorship", sa.String(length=32), server_default="editorial", nullable=False
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("edit_summary", sa.Text(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_review', 'published', 'rejected', 'withdrawn')",
            name="ck_wiki_revision_status",
        ),
        sa.CheckConstraint(
            "authorship IN ('editorial', 'community')",
            name="ck_wiki_revision_authorship",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"], ["wiki_articles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["base_revision_id"], ["wiki_revisions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "article_id", "revision_number", name="uq_wiki_revision_number"
        ),
    )
    op.create_index("ix_wiki_revision_article", "wiki_revisions", ["article_id"])
    op.create_index("ix_wiki_revision_author", "wiki_revisions", ["created_by_id"])
    op.create_index("ix_wiki_revision_status", "wiki_revisions", ["status"])
    op.create_index("ix_wiki_revision_authorship", "wiki_revisions", ["authorship"])

    op.add_column(
        "wiki_articles",
        sa.Column("published_revision_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_wiki_article_published_revision",
        "wiki_articles",
        "wiki_revisions",
        ["published_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_wiki_article_published_rev", "wiki_articles", ["published_revision_id"]
    )

    op.execute(
        """
        INSERT INTO wiki_revisions (
            article_id,
            revision_number,
            created_by_id,
            reviewed_by_id,
            status,
            authorship,
            title,
            summary,
            content,
            tags,
            review_note,
            reviewed_at,
            submitted_at,
            published_at,
            created_at,
            updated_at
        )
        SELECT
            id,
            1,
            created_by_id,
            reviewed_by_id,
            CASE
                WHEN status = 'published' THEN 'published'
                WHEN status = 'pending_review' THEN 'pending_review'
                WHEN status = 'rejected' THEN 'rejected'
                ELSE 'draft'
            END,
            'editorial',
            title,
            summary,
            content,
            tags,
            rejection_reason,
            reviewed_at,
            CASE WHEN status = 'pending_review' THEN updated_at ELSE NULL END,
            CASE WHEN status = 'published' THEN updated_at ELSE NULL END,
            created_at,
            updated_at
        FROM wiki_articles
        """
    )
    op.execute(
        """
        UPDATE wiki_articles
        SET published_revision_id = (
            SELECT wiki_revisions.id
            FROM wiki_revisions
            WHERE wiki_revisions.article_id = wiki_articles.id
              AND wiki_revisions.revision_number = 1
        )
        WHERE status = 'published'
        """
    )

    op.create_table(
        "wiki_revision_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("evidence_url", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "verdict IN ('support', 'needs_changes')",
            name="ck_wiki_review_verdict",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["wiki_revisions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "revision_id", "reviewer_id", name="uq_wiki_revision_reviewer"
        ),
    )
    op.create_index(
        "ix_wiki_revision_review_revision", "wiki_revision_reviews", ["revision_id"]
    )
    op.create_index(
        "ix_wiki_revision_review_user", "wiki_revision_reviews", ["reviewer_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_wiki_revision_review_user", table_name="wiki_revision_reviews")
    op.drop_index("ix_wiki_revision_review_revision", table_name="wiki_revision_reviews")
    op.drop_table("wiki_revision_reviews")

    op.drop_index("ix_wiki_article_published_rev", table_name="wiki_articles")
    op.drop_constraint(
        "fk_wiki_article_published_revision", "wiki_articles", type_="foreignkey"
    )
    op.drop_column("wiki_articles", "published_revision_id")

    op.drop_index("ix_wiki_revision_status", table_name="wiki_revisions")
    op.drop_index("ix_wiki_revision_authorship", table_name="wiki_revisions")
    op.drop_index("ix_wiki_revision_author", table_name="wiki_revisions")
    op.drop_index("ix_wiki_revision_article", table_name="wiki_revisions")
    op.drop_table("wiki_revisions")

    op.drop_index("ix_wiki_articles_provenance", table_name="wiki_articles")
    op.drop_index("ix_wiki_articles_language", table_name="wiki_articles")
    op.drop_index("ix_wiki_articles_space", table_name="wiki_articles")
    op.drop_constraint("fk_wiki_articles_space", "wiki_articles", type_="foreignkey")
    op.drop_column("wiki_articles", "provenance")
    op.drop_column("wiki_articles", "language")
    op.drop_column("wiki_articles", "space_id")

    op.drop_index("ix_wiki_spaces_key", table_name="wiki_spaces")
    op.drop_table("wiki_spaces")
