"""prove access to the brand site instead of trusting a scan

Revision ID: brand_request_site_check
Revises: brand_request_claim_scope
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "brand_request_site_check"
down_revision: str | None = "brand_request_claim_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "brand_requests",
        sa.Column("site_verification_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "brand_requests",
        sa.Column("site_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "brand_requests",
        sa.Column("site_verified_domain", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("brand_requests", "site_verified_domain")
    op.drop_column("brand_requests", "site_verified_at")
    op.drop_column("brand_requests", "site_verification_token")
