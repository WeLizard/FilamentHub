"""fix_user_role_enum

Revision ID: d1b87bd1b8f7
Revises: 0b9a467f6918
Create Date: 2025-10-31 21:45:13.166767

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1b87bd1b8f7'
down_revision: Union[str, None] = '9736e0b184e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Check if ENUM type exists, create if not
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE userrole AS ENUM ('user', 'brand', 'admin');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Change role column from String to ENUM
    # First, update any invalid values to 'user' (default)
    op.execute("""
        UPDATE users 
        SET role = 'user' 
        WHERE role NOT IN ('user', 'brand', 'admin');
    """)
    
    # Alter column type
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN role TYPE userrole 
        USING role::userrole;
    """)
    
    # Set default
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN role SET DEFAULT 'user';
    """)


def downgrade() -> None:
    """Downgrade database schema."""
    # Change role column from ENUM to String
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN role TYPE VARCHAR(20) 
        USING role::text;
    """)
    
    # Remove default
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN role DROP DEFAULT;
    """)
    
    # Drop ENUM type (only if no other tables use it)
    op.execute("DROP TYPE IF EXISTS userrole")

