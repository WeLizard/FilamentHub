"""add_extra_to_user_spools

Revision ID: add_extra_to_user_spools
Revises: b9f3d6e2a1c4
Create Date: 2026-02-28 00:00:00.000000

Add JSON extra column to user_spools for Spoolman compatibility.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "add_extra_to_user_spools"
down_revision: Union[str, None] = "b9f3d6e2a1c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_spools",
        sa.Column("extra", sa.JSON(), nullable=True, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("user_spools", "extra")
