"""Add unique constraint to prevent duplicate reviews per user/filament/preset.

Revision ID: add_review_unique
Revises: add_printer_hostname
Create Date: 2026-03-10
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_review_unique"
down_revision: Union[str, Sequence[str], None] = "add_printer_hostname"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_user_filament_preset_review",
        "filament_reviews",
        ["user_id", "filament_id", "preset_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_user_filament_preset_review",
        "filament_reviews",
        type_="unique",
    )
