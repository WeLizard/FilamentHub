"""add_user_spools

Revision ID: 042335145290
Revises: 63fbb1d88128
Create Date: 2026-02-27 00:01:00.000000

Adds user_spools table — physical filament spool inventory per user.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '042335145290'
down_revision: Union[str, None] = '63fbb1d88128'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create user_spools table."""
    op.create_table(
        'user_spools',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('filament_id', sa.Integer(), nullable=True),
        sa.Column('initial_weight_g', sa.Float(), nullable=False),
        sa.Column('used_weight_g', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('state', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('source', sa.String(length=30), nullable=False, server_default='manual'),
        sa.Column('lot_nr', sa.String(length=100), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['filament_id'], ['filaments.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_spools_id', 'user_spools', ['id'])
    op.create_index('ix_user_spools_user_id', 'user_spools', ['user_id'])
    op.create_index('ix_user_spools_filament_id', 'user_spools', ['filament_id'])
    op.create_index('ix_user_spools_state', 'user_spools', ['state'])


def downgrade() -> None:
    """Drop user_spools table."""
    op.drop_table('user_spools')
