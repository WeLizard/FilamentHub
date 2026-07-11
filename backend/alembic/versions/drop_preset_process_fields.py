"""drop process-scope columns from presets

print_speed / travel_speed / layer_height / first_layer_height are process
(print profile) settings in OrcaSlicer (s_Preset_print_options), not filament
properties. A filament preset must not carry them, so they are removed from the
model and dropped here.

Apply BEFORE deploying the code: print_speed was NOT NULL, and the new code no
longer supplies it on insert.
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "drop_preset_process_fields"
down_revision: Union[str, None] = "preset_auto_generated_status"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.drop_column("presets", "print_speed")
    op.drop_column("presets", "travel_speed")
    op.drop_column("presets", "layer_height")
    op.drop_column("presets", "first_layer_height")


def downgrade() -> None:
    # Re-add as nullable (original NOT NULL on print_speed cannot be restored
    # without data). The columns are inert unless code repopulates them.
    op.add_column("presets", sa.Column("first_layer_height", sa.Float(), nullable=True))
    op.add_column("presets", sa.Column("layer_height", sa.Float(), nullable=True))
    op.add_column("presets", sa.Column("travel_speed", sa.Float(), nullable=True))
    op.add_column("presets", sa.Column("print_speed", sa.Float(), nullable=True))
