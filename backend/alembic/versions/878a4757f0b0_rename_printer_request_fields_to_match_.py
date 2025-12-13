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
    
    # Создаем таблицу через SQL для надежности (как в статье на Хабре)
    # Используем DO блок для проверки существования таблицы
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'printer_requests'
            ) THEN
                CREATE TABLE printer_requests (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    name VARCHAR(200) NOT NULL,
                    manufacturer VARCHAR(100) NOT NULL,
                    model VARCHAR(100) NOT NULL,
                    slug VARCHAR(200) NOT NULL,
                    description TEXT,
                    build_volume_x DOUBLE PRECISION,
                    build_volume_y DOUBLE PRECISION,
                    build_volume_z DOUBLE PRECISION,
                    nozzle_diameter DOUBLE PRECISION,
                    max_extruder_temp INTEGER,
                    max_bed_temp INTEGER,
                    image_url VARCHAR(500),
                    message TEXT,
                    proof_files TEXT,
                    status printerrequeststatus NOT NULL DEFAULT 'pending',
                    processed_by_id INTEGER REFERENCES users(id),
                    processed_at TIMESTAMP,
                    rejection_reason TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT now(),
                    updated_at TIMESTAMP NOT NULL DEFAULT now()
                );
                
                CREATE INDEX IF NOT EXISTS ix_printer_requests_id ON printer_requests(id);
                CREATE INDEX IF NOT EXISTS ix_printer_requests_user_id ON printer_requests(user_id);
                CREATE INDEX IF NOT EXISTS ix_printer_requests_status ON printer_requests(status);
                CREATE INDEX IF NOT EXISTS ix_printer_requests_slug ON printer_requests(slug);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index(op.f('ix_printer_requests_slug'), table_name='printer_requests')
    op.drop_index(op.f('ix_printer_requests_status'), table_name='printer_requests')
    op.drop_index(op.f('ix_printer_requests_user_id'), table_name='printer_requests')
    op.drop_index(op.f('ix_printer_requests_id'), table_name='printer_requests')
    op.drop_table('printer_requests')
    
    # Drop ENUM type
    op.execute("DROP TYPE IF EXISTS printerrequeststatus")

