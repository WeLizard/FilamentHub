"""Drop the unused user bio column

Revision ID: drop_user_bio
Revises: backfill_reported_feed
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "drop_user_bio"
down_revision = "backfill_reported_feed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "bio")


def downgrade() -> None:
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))
