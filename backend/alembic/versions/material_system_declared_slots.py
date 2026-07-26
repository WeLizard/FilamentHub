"""Record the slot count a person confirmed for a material system

Revision ID: material_system_declared_slots
Revises: user_legal_acceptance
Create Date: 2026-07-25

"""
from alembic import op
import sqlalchemy as sa


revision = "material_system_declared_slots"
down_revision = "user_legal_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "material_systems",
        sa.Column("declared_slot_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("material_systems", "declared_slot_count")
