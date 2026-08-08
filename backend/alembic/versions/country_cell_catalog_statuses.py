"""Add regional catalog statuses to filament country cells.

Revision ID: country_cell_catalog_statuses
Revises: filament_analytics_events
Create Date: 2026-08-08
"""

from typing import Sequence, Union

from alembic import op


revision: str = "country_cell_catalog_statuses"
down_revision: Union[str, None] = "filament_analytics_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL enum additions are intentionally additive. Existing
    # available/unavailable/unknown rows remain readable.
    op.execute("ALTER TYPE country_availability ADD VALUE IF NOT EXISTS 'coming_soon'")
    op.execute("ALTER TYPE country_availability ADD VALUE IF NOT EXISTS 'discontinued'")


def downgrade() -> None:
    # PostgreSQL cannot safely remove enum values in-place. Leaving the values
    # is data-safe and keeps a downgrade from rewriting the whole table.
    pass
