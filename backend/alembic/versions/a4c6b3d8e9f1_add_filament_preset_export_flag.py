"""Add filament preset export flag to users.

Revision ID: a4c6b3d8e9f1
Revises: add_review_unique
Create Date: 2026-03-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4c6b3d8e9f1"
down_revision: Union[str, Sequence[str], None] = "add_review_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "allow_filament_presets_export",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column(
        "users",
        "allow_filament_presets_export",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("users", "allow_filament_presets_export")
