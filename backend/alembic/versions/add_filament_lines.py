"""add_filament_lines

Revision ID: add_filament_lines
Revises: add_brand_logo_bg
Create Date: 2026-06-28 00:00:00.000000

Adds filament_lines table and filaments.line_id so a brand can group colour
variants under a product line (grouping only — each colour stays its own
Filament). Backward-compatible: line_id is nullable, existing rows stay NULL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'add_filament_lines'
down_revision: Union[str, None] = 'add_brand_logo_bg'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create filament_lines and add filaments.line_id (nullable FK)."""
    op.create_table(
        'filament_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('brand_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_filament_lines_id', 'filament_lines', ['id'])
    op.create_index('ix_filament_lines_brand_id', 'filament_lines', ['brand_id'])

    op.add_column('filaments', sa.Column('line_id', sa.Integer(), nullable=True))
    op.create_index('ix_filaments_line_id', 'filaments', ['line_id'])
    op.create_foreign_key(
        'fk_filaments_line_id', 'filaments', 'filament_lines',
        ['line_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    """Drop filaments.line_id and filament_lines."""
    op.drop_constraint('fk_filaments_line_id', 'filaments', type_='foreignkey')
    op.drop_index('ix_filaments_line_id', table_name='filaments')
    op.drop_column('filaments', 'line_id')
    op.drop_index('ix_filament_lines_brand_id', table_name='filament_lines')
    op.drop_index('ix_filament_lines_id', table_name='filament_lines')
    op.drop_table('filament_lines')
