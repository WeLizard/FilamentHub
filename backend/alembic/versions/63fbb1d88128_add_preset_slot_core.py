"""add_preset_slot_core

Revision ID: 63fbb1d88128
Revises: e01bc3b29297
Create Date: 2026-02-27 00:00:00.000000

Adds tables for Happy Hare / preset-slot integration:
  - user_printer_devices  — user's physical printer with HH support
  - preset_gate_states    — current preset assigned to each gate/slot
  - preset_usage_events   — filament usage history
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '63fbb1d88128'
down_revision: Union[str, None] = 'e01bc3b29297'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create preset slot core tables."""
    # 1. user_printer_devices
    op.create_table(
        'user_printer_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('printer_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('device_fingerprint', sa.String(length=200), nullable=False),
        sa.Column('supports_hh', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('gate_count', sa.Integer(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['printer_id'], ['printers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'device_fingerprint', name='uq_user_device_fingerprint'),
    )
    op.create_index('ix_user_printer_devices_id', 'user_printer_devices', ['id'])
    op.create_index('ix_user_printer_devices_user_id', 'user_printer_devices', ['user_id'])
    op.create_index('ix_user_printer_devices_printer_id', 'user_printer_devices', ['printer_id'])

    # 2. preset_gate_states
    op.create_table(
        'preset_gate_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('gate_index', sa.Integer(), nullable=False),
        sa.Column('preset_id', sa.Integer(), nullable=True),
        sa.Column('spool_id', sa.Integer(), nullable=True),
        sa.Column('hh_material', sa.String(length=50), nullable=True),
        sa.Column('hh_color_hex', sa.String(length=7), nullable=True),
        sa.Column('hh_status', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('source_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['device_id'], ['user_printer_devices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['preset_id'], ['presets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id', 'gate_index', name='uq_device_gate_index'),
    )
    op.create_index('ix_preset_gate_states_id', 'preset_gate_states', ['id'])
    op.create_index('ix_preset_gate_states_user_id', 'preset_gate_states', ['user_id'])
    op.create_index('ix_preset_gate_states_device_id', 'preset_gate_states', ['device_id'])
    op.create_index('ix_preset_gate_states_preset_id', 'preset_gate_states', ['preset_id'])

    # 3. preset_usage_events
    op.create_table(
        'preset_usage_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('preset_id', sa.Integer(), nullable=True),
        sa.Column('spool_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('delta_weight_g', sa.Float(), nullable=True),
        sa.Column('job_ref', sa.String(length=200), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['device_id'], ['user_printer_devices.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['preset_id'], ['presets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_preset_usage_events_id', 'preset_usage_events', ['id'])
    op.create_index('ix_preset_usage_events_user_id', 'preset_usage_events', ['user_id'])
    op.create_index('ix_preset_usage_events_device_id', 'preset_usage_events', ['device_id'])
    op.create_index('ix_preset_usage_events_preset_id', 'preset_usage_events', ['preset_id'])


def downgrade() -> None:
    """Drop preset slot core tables."""
    op.drop_table('preset_usage_events')
    op.drop_table('preset_gate_states')
    op.drop_table('user_printer_devices')
