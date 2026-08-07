"""The country an invitation offers.

Revision ID: brand_invite_country
Revises: brand_request_country
Create Date: 2026-08-08

An application already names the market it asks for. An invitation could not,
so the person accepting it arrived without a territory and could manage no
country at all. Empty keeps the old meaning: no territorial scope is offered,
and the invitation grants nothing beyond team membership.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "brand_invite_country"
down_revision: Union[str, None] = "brand_request_country"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("brand_invites", sa.Column("country", sa.String(length=2), nullable=True))


def downgrade() -> None:
    op.drop_column("brand_invites", "country")
