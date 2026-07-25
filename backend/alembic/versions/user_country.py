"""add country to users

Revision ID: user_country
Revises: user_auto_import_presets
Create Date: 2026-07-25

Declared country as an ISO 3166-1 alpha-2 code. NULL means the person has not
said, which stays a valid state: the country is asked for, never guessed from an
address.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "user_country"
down_revision: Union[str, None] = "user_auto_import_presets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("country", sa.String(length=2), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "country")
