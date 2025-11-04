"""Rename printer_request fields to match schema

Revision ID: 878a4757f0b0
Revises: 7d567a4a6107
Create Date: 2025-11-04 00:00:56.358948

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '878a4757f0b0'
down_revision: Union[str, None] = '7d567a4a6107'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Create ENUM type for printer request status (check if it exists first)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE printerrequeststatus AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Check if table exists before creating it
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'printer_requests' not in inspector.get_table_names():
        op.create_table('printer_requests',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            
            # Printer data (without new_printer_ prefix)
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('manufacturer', sa.String(length=100), nullable=False),
            sa.Column('model', sa.String(length=100), nullable=False),
            sa.Column('slug', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            
            # Optional printer specs
            sa.Column('build_volume_x', sa.Float(), nullable=True),
            sa.Column('build_volume_y', sa.Float(), nullable=True),
            sa.Column('build_volume_z', sa.Float(), nullable=True),
            sa.Column('nozzle_diameter', sa.Float(), nullable=True),
            sa.Column('max_extruder_temp', sa.Integer(), nullable=True),
            sa.Column('max_bed_temp', sa.Integer(), nullable=True),
            sa.Column('image_url', sa.String(length=500), nullable=True),
            
            # Request message
            sa.Column('message', sa.Text(), nullable=True),
            
            # Status
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            
            # Admin who processed the request
            sa.Column('processed_by_id', sa.Integer(), nullable=True),
            sa.Column('processed_at', sa.DateTime(), nullable=True),
            
            # Rejection reason
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            
            # Timestamps
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['processed_by_id'], ['users.id'], ),
        )
        op.create_index(op.f('ix_printer_requests_id'), 'printer_requests', ['id'], unique=False)
        op.create_index(op.f('ix_printer_requests_user_id'), 'printer_requests', ['user_id'], unique=False)
        op.create_index(op.f('ix_printer_requests_status'), 'printer_requests', ['status'], unique=False)
        op.create_index(op.f('ix_printer_requests_slug'), 'printer_requests', ['slug'], unique=False)


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index(op.f('ix_printer_requests_slug'), table_name='printer_requests')
    op.drop_index(op.f('ix_printer_requests_status'), table_name='printer_requests')
    op.drop_index(op.f('ix_printer_requests_user_id'), table_name='printer_requests')
    op.drop_index(op.f('ix_printer_requests_id'), table_name='printer_requests')
    op.drop_table('printer_requests')
    
    # Drop ENUM type
    op.execute("DROP TYPE IF EXISTS printerrequeststatus")

