"""Merge all heads into single head

Revision ID: merge_all_heads_final
Revises: add_feedback_source, add_sync_device_and_history
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'merge_all_heads_final'
down_revision = (
    'add_feedback_source',
    'add_sync_device_and_history',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
