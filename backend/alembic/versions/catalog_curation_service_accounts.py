"""Add revocable service credentials for draft-only catalog curation.

Revision ID: catalog_cur_svc_accounts
Revises: catalog_curation_unmapped_facts
"""

import sqlalchemy as sa

from alembic import op

revision = "catalog_cur_svc_accounts"
down_revision = "catalog_curation_unmapped_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_curation_service_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_cat_cur_svc_account_key_hash",
        "catalog_curation_service_accounts",
        ["key_hash"],
        unique=True,
    )
    op.add_column(
        "catalog_curation_proposals",
        sa.Column(
            "created_by_service_account_id",
            sa.Integer(),
            sa.ForeignKey("catalog_curation_service_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "catalog_curation_proposals",
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "catalog_curation_proposals",
        sa.Column(
            "updated_by_service_account_id",
            sa.Integer(),
            sa.ForeignKey("catalog_curation_service_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_cat_cur_proposal_svc_id",
        "catalog_curation_proposals",
        ["created_by_service_account_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cat_cur_proposal_svc_id", table_name="catalog_curation_proposals")
    op.drop_column("catalog_curation_proposals", "updated_by_service_account_id")
    op.drop_column("catalog_curation_proposals", "updated_by_user_id")
    op.drop_column("catalog_curation_proposals", "created_by_service_account_id")
    op.drop_index(
        "ix_cat_cur_svc_account_key_hash", table_name="catalog_curation_service_accounts"
    )
    op.drop_table("catalog_curation_service_accounts")
