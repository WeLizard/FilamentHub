"""add_brand_invites

Revision ID: add_brand_invites
Revises: add_user_avatar
Create Date: 2026-06-29 00:00:00.000000

Adds the brand_invites table for admin pre-verified manufacturer invitations.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'add_brand_invites'
down_revision: Union[str, None] = 'add_user_avatar'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create brand_invites table."""
    op.create_table(
        'brand_invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('brand_name', sa.String(length=100), nullable=True),
        sa.Column('pre_verified', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('invited_by_id', sa.Integer(), nullable=True),
        sa.Column('accepted_by_id', sa.Integer(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['accepted_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_brand_invites_id', 'brand_invites', ['id'])
    op.create_index('ix_brand_invites_token', 'brand_invites', ['token'], unique=True)
    op.create_index('ix_brand_invites_email', 'brand_invites', ['email'])


def downgrade() -> None:
    """Drop brand_invites table."""
    op.drop_index('ix_brand_invites_email', table_name='brand_invites')
    op.drop_index('ix_brand_invites_token', table_name='brand_invites')
    op.drop_index('ix_brand_invites_id', table_name='brand_invites')
    op.drop_table('brand_invites')
