"""add required_nozzle_hrc to filaments

Required nozzle hardness is a material property (abrasive fillers — carbon,
glass, glow, metal — need a hardened nozzle), not a print setting. Stored on
the filament; the exporter emits it as required_nozzle_HRC on every profile.
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "filament_required_nozzle_hrc"
down_revision: Union[str, None] = "drop_preset_process_fields"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("filaments", sa.Column("required_nozzle_hrc", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("filaments", "required_nozzle_hrc")
