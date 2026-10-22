"""Add quote verification verdicts and their coalesced job queue.

Revision ID: catalog_quote_checks
Revises: filament_additional_props
"""

import sqlalchemy as sa

from alembic import op

revision = "catalog_quote_checks"
down_revision = "filament_additional_props"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_curation_quote_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.Integer(),
            sa.ForeignKey("catalog_curation_proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("sheet", sa.String(32), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("field", sa.String(120), nullable=False),
        sa.Column("claim_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(64), nullable=True),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("page_sha256", sa.String(64), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "proposal_id", "scope", "sheet", "key", "field", name="uq_cc_quote_checks_fact"
        ),
    )
    op.create_table(
        "catalog_curation_quote_jobs",
        sa.Column(
            "proposal_id",
            sa.Integer(),
            sa.ForeignKey("catalog_curation_proposals.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_catalog_curation_quote_jobs_next_attempt_at",
        "catalog_curation_quote_jobs",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalog_curation_quote_jobs_next_attempt_at", table_name="catalog_curation_quote_jobs"
    )
    op.drop_table("catalog_curation_quote_jobs")
    op.drop_table("catalog_curation_quote_checks")
