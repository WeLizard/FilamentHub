"""Record what a spool had left right after a usage event

Revision ID: usage_remaining
Revises: merge_dup_profiles
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "usage_remaining"
down_revision = "merge_dup_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "preset_usage_events",
        sa.Column("remaining_weight_g", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("preset_usage_events", "remaining_weight_g")
