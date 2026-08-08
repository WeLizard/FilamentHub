"""On whose behalf a person is working right now.

Revision ID: active_organization
Revises: filament_contributor
Create Date: 2026-08-08

One brand may be reachable through several organizations at once — the one that
holds the global grant and the ones that hold single countries. A pointer to the
brand alone cannot say which of them a person is acting as, so the workspace is
a pair: the organization and the brand.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "active_organization"
down_revision: Union[str, None] = "filament_contributor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("active_organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_active_organization",
        "users",
        "organizations",
        ["active_organization_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_active_organization", "users", type_="foreignkey")
    op.drop_column("users", "active_organization_id")
