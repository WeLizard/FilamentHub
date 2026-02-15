"""add sync_device and sync_history tables

Revision ID: add_sync_device_and_history
Revises: f2b7c90864d4
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_sync_device_and_history'
down_revision: str = 'f2b7c90864d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sync_devices table
    op.create_table(
        'sync_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_fingerprint', sa.String(255), nullable=False),
        sa.Column('orcaslicer_version', sa.String(50), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sync_devices_id', 'sync_devices', ['id'])
    op.create_index('ix_sync_devices_user_id', 'sync_devices', ['user_id'])
    op.create_index(
        'ix_sync_devices_user_fingerprint',
        'sync_devices',
        ['user_id', 'device_fingerprint'],
        unique=True,
    )

    # Create enums via raw SQL (sa.Enum + asyncpg has checkfirst bugs)
    op.execute("DO $$ BEGIN CREATE TYPE syncpresettype AS ENUM ('filament', 'printer', 'print'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE syncoperation AS ENUM ('download', 'upload', 'delete'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE syncstatus AS ENUM ('success', 'error', 'conflict'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

    # Use postgresql.ENUM with create_type=False to reference already-created enums
    from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
    sync_preset_type = PG_ENUM('filament', 'printer', 'print', name='syncpresettype', create_type=False)
    sync_operation = PG_ENUM('download', 'upload', 'delete', name='syncoperation', create_type=False)
    sync_status = PG_ENUM('success', 'error', 'conflict', name='syncstatus', create_type=False)

    op.create_table(
        'sync_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('sync_version', sa.Integer(), nullable=False),
        sa.Column('preset_type', sync_preset_type, nullable=False),
        sa.Column('operation', sync_operation, nullable=False),
        sa.Column('preset_id', sa.Integer(), nullable=False),
        sa.Column('status', sync_status, nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['device_id'], ['sync_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sync_history_id', 'sync_history', ['id'])
    op.create_index('ix_sync_history_user_id', 'sync_history', ['user_id'])
    op.create_index('ix_sync_history_device_id', 'sync_history', ['device_id'])


def downgrade() -> None:
    op.drop_table('sync_history')
    op.drop_table('sync_devices')

    # Drop enums
    sa.Enum(name='syncpresettype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='syncoperation').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='syncstatus').drop(op.get_bind(), checkfirst=True)
