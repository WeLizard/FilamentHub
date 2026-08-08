"""Whose work a catalogue record is.

Revision ID: filament_contributor
Revises: filament_cell_color_name
Create Date: 2026-08-08

A record added by the Iranian organization stays theirs after the person who
typed it leaves, and the Korean organization sees somebody else's record rather
than somebody's personal one — the same grain territory already has.

Empty means the community added it.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "filament_contributor"
down_revision: Union[str, None] = "filament_cell_color_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "filaments",
        sa.Column("contributed_by_organization_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_filaments_contributor",
        "filaments",
        "organizations",
        ["contributed_by_organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_filaments_contributor", "filaments", ["contributed_by_organization_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_filaments_contributor", table_name="filaments")
    op.drop_constraint("fk_filaments_contributor", "filaments", type_="foreignkey")
    op.drop_column("filaments", "contributed_by_organization_id")
