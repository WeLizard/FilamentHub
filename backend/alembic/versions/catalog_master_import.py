"""Audit confirmed administrative catalog master-imports.

Revision ID: catalog_master_import
Revises: feedback_admin_unread_counter
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "catalog_master_import"
down_revision = "feedback_admin_unread_counter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("applied_by_user_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("plan_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_catalog_import_batches_source_sha256",
        "catalog_import_batches",
        ["source_sha256"],
    )
    op.create_index(
        "ix_catalog_import_batches_applied_by_user_id",
        "catalog_import_batches",
        ["applied_by_user_id"],
    )
    op.create_index(
        "ix_catalog_import_batches_applied_at",
        "catalog_import_batches",
        ["applied_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_import_batches_applied_at", table_name="catalog_import_batches")
    op.drop_index(
        "ix_catalog_import_batches_applied_by_user_id",
        table_name="catalog_import_batches",
    )
    op.drop_index(
        "ix_catalog_import_batches_source_sha256",
        table_name="catalog_import_batches",
    )
    op.drop_table("catalog_import_batches")
