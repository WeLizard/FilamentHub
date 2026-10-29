"""A person's own show/hide choice for a material slot.

Revision ID: material_slot_visibility
Revises: material_abs_hf

Hiding an extra holder (external spool, bypass) used to delete its row, so the
next provider snapshot recreated it. The choice now lives beside the row.
"""

import sqlalchemy as sa

from alembic import op

revision = "material_slot_visibility"
down_revision = "material_abs_hf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("material_slots", sa.Column("user_visibility", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("material_slots", "user_visibility")
