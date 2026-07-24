"""add auto_import_local_presets to users

Revision ID: user_auto_import_presets
Revises: user_recommend_selection
Create Date: 2026-07-23

Tri-state consent for proactively importing unlinked local OrcaSlicer filament
presets as drafts: NULL = not asked yet, true/false = the user's decision.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "user_auto_import_presets"
down_revision: Union[str, None] = "user_recommend_selection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auto_import_local_presets", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "auto_import_local_presets")
