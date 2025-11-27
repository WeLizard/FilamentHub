"""add timezone to preset timestamps

Revision ID: a1b2c3d4e5f9
Revises: f2b7c90864d4
Create Date: 2025-11-21 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f9'
down_revision: Union[str, None] = 'f2b7c90864d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add timezone to preset timestamps
    op.alter_column('presets', 'created_at',
                    existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True),
                    existing_nullable=False,
                    existing_server_default=sa.text('now()'))
    op.alter_column('presets', 'updated_at',
                    existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True),
                    existing_nullable=False,
                    existing_server_default=sa.text('now()'),
                    existing_onupdate=sa.text('now()'))


def downgrade() -> None:
    # Remove timezone from preset timestamps
    op.alter_column('presets', 'created_at',
                    existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(),
                    existing_nullable=False,
                    existing_server_default=sa.text('now()'))
    op.alter_column('presets', 'updated_at',
                    existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(),
                    existing_nullable=False,
                    existing_server_default=sa.text('now()'),
                    existing_onupdate=sa.text('now()'))
