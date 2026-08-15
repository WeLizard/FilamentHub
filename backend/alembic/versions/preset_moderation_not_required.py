"""add not_required value to presetmoderationstatus enum

A draft imported from OrcaSlicer has no material yet, so there is nothing to
moderate: without a filament there is no reference to compare its temperatures
against. Marking such a draft PENDING made every import look like a moderation
task that never reaches the admin queue (it filters on active presets) and
distorted the counters in the user's library. Drafts get a dedicated
NOT_REQUIRED status; real moderation runs when the draft becomes a preset.
"""

from typing import Union

from alembic import op

revision: str = "preset_moderation_not_required"
down_revision: Union[str, None] = "filament_handling_parameters"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # PG 9.6+ supports IF NOT EXISTS; PG 12+ allows ADD VALUE inside a transaction
    # as long as the new value is not used in the same transaction (it isn't here).
    op.execute("ALTER TYPE presetmoderationstatus ADD VALUE IF NOT EXISTS 'not_required'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it and
    # rewriting every dependent column — intentionally a no-op. The value is inert
    # unless a preset is set to it.
    pass
