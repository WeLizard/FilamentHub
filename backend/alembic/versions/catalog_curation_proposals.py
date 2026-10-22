"""Persist reviewable catalog curation proposals.

Revision ID: catalog_curation_proposals
Revises: spool_compat_resources
"""

import sqlalchemy as sa

from alembic import op

revision = "catalog_curation_proposals"
down_revision = "spool_compat_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_curation_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("coverage_note", sa.Text(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "applied_batch_id",
            sa.Integer(),
            sa.ForeignKey("catalog_import_batches.id", ondelete="RESTRICT"),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("catalog_curation_proposals")
