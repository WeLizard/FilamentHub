"""Add composite indexes for filaments and presets

Revision ID: cf5f5c9bd1d2
Revises: add_bad_words
Create Date: 2025-11-07 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "cf5f5c9bd1d2"
down_revision: Union[str, None] = "add_bad_words"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create composite indexes to speed up common catalogue queries."""
    op.create_index(
        "ix_filaments_brand_active",
        "filaments",
        ["brand_id", "active"],
        unique=False,
    )
    op.create_index(
        "ix_filaments_material_type_active",
        "filaments",
        ["material_type", "active"],
        unique=False,
    )
    op.create_index(
        "ix_presets_filament_status_active",
        "presets",
        ["filament_id", "moderation_status", "active"],
        unique=False,
    )
    op.create_index(
        "ix_presets_official_active",
        "presets",
        ["is_official", "active"],
        unique=False,
    )


def downgrade() -> None:
    """Drop composite indexes."""
    op.drop_index("ix_presets_official_active", table_name="presets")
    op.drop_index("ix_presets_filament_status_active", table_name="presets")
    op.drop_index("ix_filaments_material_type_active", table_name="filaments")
    op.drop_index("ix_filaments_brand_active", table_name="filaments")


