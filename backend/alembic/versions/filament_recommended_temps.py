"""add vendor recommended temperature ranges to filaments

Vendor-set material spec: recommended nozzle/bed temperature ranges live on the
material (Filament), not baked into a specific preset. Presets pull them as a
starting default when created. All nullable — community materials may lack them.
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "filament_rec_temps"
down_revision: Union[str, None] = "drop_profile_hash_uq"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("filaments", sa.Column("recommended_nozzle_temp_min", sa.Integer(), nullable=True))
    op.add_column("filaments", sa.Column("recommended_nozzle_temp_max", sa.Integer(), nullable=True))
    op.add_column("filaments", sa.Column("recommended_bed_temp_min", sa.Integer(), nullable=True))
    op.add_column("filaments", sa.Column("recommended_bed_temp_max", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("filaments", "recommended_bed_temp_max")
    op.drop_column("filaments", "recommended_bed_temp_min")
    op.drop_column("filaments", "recommended_nozzle_temp_max")
    op.drop_column("filaments", "recommended_nozzle_temp_min")
