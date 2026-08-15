"""add product-specific filament handling guidance

Revision ID: filament_handling_guidance
Revises: orca_endpoint_blind_indexes
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "filament_handling_guidance"
down_revision: str | None = "orca_endpoint_blind_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "filaments",
        sa.Column("drying_required", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "filaments",
        sa.Column("enclosure_requirement", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "filaments",
        sa.Column("bed_adhesives", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "filaments",
        sa.Column(
            "post_processing_chemicals",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_filaments_enclosure_requirement",
        "filaments",
        "enclosure_requirement IS NULL OR enclosure_requirement IN ('none','passive','active')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_filaments_enclosure_requirement",
        "filaments",
        type_="check",
    )
    op.drop_column("filaments", "post_processing_chemicals")
    op.drop_column("filaments", "bed_adhesives")
    op.drop_column("filaments", "enclosure_requirement")
    op.drop_column("filaments", "drying_required")
