"""Add preset_locally_deleted to notificationtype enum

Revision ID: add_preset_deleted_enum
Revises: add_revoked_tokens
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_preset_deleted_enum'
down_revision: Union[str, None] = 'add_revoked_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'preset_locally_deleted' value to notificationtype enum."""
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'preset_locally_deleted';
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)


def downgrade() -> None:
    """Cannot remove enum values in PostgreSQL — no-op."""
    pass
