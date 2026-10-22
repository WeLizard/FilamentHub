"""Add administrator confirmations for claims proven only by an image.

Revision ID: catalog_image_confirms
Revises: catalog_quote_checks
"""

import sqlalchemy as sa

from alembic import op

revision = "catalog_image_confirms"
down_revision = "catalog_quote_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_curation_image_confirmations",
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
        sa.Column(
            "confirmed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "proposal_id", "scope", "sheet", "key", "field", name="uq_cc_image_confirm_fact"
        ),
    )


def downgrade() -> None:
    op.drop_table("catalog_curation_image_confirmations")
