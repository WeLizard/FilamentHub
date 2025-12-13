"""Add qr_code field to filaments

Revision ID: a1b2c3d4e5f7
Revises: 97585b264440
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = '878a4757f0b0'  # rename_printer_request_fields
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Добавляем колонку qr_code, используя прямой SQL для надежности
    op.execute("""
        ALTER TABLE filaments 
        ADD COLUMN IF NOT EXISTS qr_code VARCHAR(50);
    """)
    
    # Создаем уникальный индекс, если его еще нет
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_filaments_qr_code 
        ON filaments (qr_code) 
        WHERE qr_code IS NOT NULL;
    """)


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index(op.f('ix_filaments_qr_code'), table_name='filaments')
    op.drop_column('filaments', 'qr_code')

