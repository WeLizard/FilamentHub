"""preserve redirects for renamed brand slugs

Revision ID: brand_slug_redirects
Revises: brand_invite_batch_guard
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "brand_slug_redirects"
down_revision: str | None = "brand_invite_batch_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brand_slug_redirects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("old_slug", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("old_slug", name="uq_brand_slug_redirects_old_slug"),
    )
    op.create_index(
        op.f("ix_brand_slug_redirects_brand_id"),
        "brand_slug_redirects",
        ["brand_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_brand_slug_redirects_brand_id"), table_name="brand_slug_redirects")
    op.drop_table("brand_slug_redirects")
