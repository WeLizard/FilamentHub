"""remember what a create request claims

Revision ID: brand_request_claim_scope
Revises: color_groups_muted
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "brand_request_claim_scope"
down_revision: str | None = "color_groups_muted"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "brand_requests",
        sa.Column("claim_scope", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("brand_requests", "claim_scope")
