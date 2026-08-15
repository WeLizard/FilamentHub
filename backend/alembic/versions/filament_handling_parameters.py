"""add drying and heated chamber parameters

Revision ID: filament_handling_parameters
Revises: filament_handling_guidance
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "filament_handling_parameters"
down_revision: str | None = "filament_handling_guidance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "filaments",
        sa.Column("drying_temperature_c", sa.Float(), nullable=True),
    )
    op.add_column(
        "filaments",
        sa.Column("drying_duration_hours", sa.Float(), nullable=True),
    )
    op.add_column(
        "filaments",
        sa.Column("chamber_temperature_c", sa.Float(), nullable=True),
    )
    op.create_check_constraint(
        "ck_filaments_drying_temperature",
        "filaments",
        "drying_temperature_c IS NULL OR drying_temperature_c BETWEEN 0 AND 200",
    )
    op.create_check_constraint(
        "ck_filaments_drying_duration",
        "filaments",
        "drying_duration_hours IS NULL OR drying_duration_hours BETWEEN 0.25 AND 336",
    )
    op.create_check_constraint(
        "ck_filaments_chamber_temperature",
        "filaments",
        "chamber_temperature_c IS NULL OR chamber_temperature_c BETWEEN 0 AND 150",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_filaments_chamber_temperature",
        "filaments",
        type_="check",
    )
    op.drop_constraint(
        "ck_filaments_drying_duration",
        "filaments",
        type_="check",
    )
    op.drop_constraint(
        "ck_filaments_drying_temperature",
        "filaments",
        type_="check",
    )
    op.drop_column("filaments", "chamber_temperature_c")
    op.drop_column("filaments", "drying_duration_hours")
    op.drop_column("filaments", "drying_temperature_c")
