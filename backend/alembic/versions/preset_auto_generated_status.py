"""add auto_generated value to presetmoderationstatus enum

Weighted (generative) presets must not be auto-stamped as human-APPROVED.
They get a dedicated AUTO_GENERATED status that stays publicly visible
(PUBLIC_PRESET_STATUSES) but is not "approved". Adds the enum value.
"""

from typing import Union

from alembic import op

revision: str = "preset_auto_generated_status"
down_revision: Union[str, None] = "filament_rec_temps"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # PG 9.6+ supports IF NOT EXISTS; PG 12+ allows ADD VALUE inside a transaction
    # as long as the new value is not used in the same transaction (it isn't here).
    op.execute("ALTER TYPE presetmoderationstatus ADD VALUE IF NOT EXISTS 'auto_generated'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it and
    # rewriting every dependent column — intentionally a no-op. The value is inert
    # unless a preset is set to it.
    pass
