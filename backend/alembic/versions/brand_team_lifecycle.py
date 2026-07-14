"""Add team invitation lifecycle fields.

Revision ID: brand_team_lifecycle
Revises: organization_brand_ownership
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "brand_team_lifecycle"
down_revision: Union[str, None] = "organization_brand_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "brand_invites",
        sa.Column(
            "purpose",
            sa.String(length=24),
            server_default="representative",
            nullable=False,
        ),
    )
    op.add_column(
        "brand_invites",
        sa.Column("all_brands", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "brand_invites",
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        op.f("ix_brand_invites_purpose"),
        "brand_invites",
        ["purpose"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_brand_invites_purpose"), table_name="brand_invites")
    op.drop_column("brand_invites", "revoked_at")
    op.drop_column("brand_invites", "all_brands")
    op.drop_column("brand_invites", "purpose")
