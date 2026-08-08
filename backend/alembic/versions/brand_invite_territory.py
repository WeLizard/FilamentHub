"""The organization a territory invitation proposes to create.

Revision ID: brand_invite_territory
Revises: brand_invite_country
Create Date: 2026-08-08

A regional representative is a separate company, not an employee of the head
office: Creality Kazakhstan is its own organization with its own grant. The
invitation therefore has to name that organization before it exists.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "brand_invite_territory"
down_revision: Union[str, None] = "brand_invite_country"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "brand_invites", sa.Column("organization_name", sa.String(length=200), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("brand_invites", "organization_name")
