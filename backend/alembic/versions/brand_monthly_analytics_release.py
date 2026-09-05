"""Persist privacy-gated monthly brand releases without personal records.

Revision ID: brand_monthly_analytics_release
Revises: adapter_topology_authority
"""

import sqlalchemy as sa

from alembic import op

revision = "brand_monthly_analytics_release"
down_revision = "adapter_topology_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brand_monthly_analytics_releases",
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spool_count", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "spool_count IS NULL OR spool_count >= 10",
            name="ck_brand_monthly_release_cohort",
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("brand_id", "month"),
    )


def downgrade() -> None:
    op.drop_table("brand_monthly_analytics_releases")
