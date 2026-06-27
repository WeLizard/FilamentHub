"""add_filament_availability

Revision ID: add_filament_availability
Revises: add_preset_versions
Create Date: 2026-06-26 00:00:00.000000

Adds filaments.availability — sale status of a filament for its brand.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'add_filament_availability'
down_revision: Union[str, None] = 'add_preset_versions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add availability column with a backward-compatible default."""
    op.add_column(
        'filaments',
        sa.Column(
            'availability',
            sa.String(length=20),
            nullable=False,
            server_default='available',
        ),
    )
    op.create_index('ix_filaments_availability', 'filaments', ['availability'])


def downgrade() -> None:
    """Drop availability column."""
    op.drop_index('ix_filaments_availability', table_name='filaments')
    op.drop_column('filaments', 'availability')
