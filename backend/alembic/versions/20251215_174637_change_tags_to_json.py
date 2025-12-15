"""Change tags to JSON

Revision ID: change_tags_to_json
Revises: 4d25fedc35e5
Create Date: 2025-12-15 17:46:37
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'change_tags_to_json'
down_revision = '4d25fedc35e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Change tags column from String to JSON."""
    # Convert existing JSON strings to JSONB
    # First, make it nullable if needed, then convert
    op.execute("""
        ALTER TABLE wiki_articles 
        ALTER COLUMN tags TYPE JSONB 
        USING CASE 
            WHEN tags IS NULL THEN NULL
            WHEN tags::text ~ '^\\[.*\\]$' THEN tags::jsonb
            ELSE '[]'::jsonb
        END
    """)


def downgrade() -> None:
    """Revert tags column from JSON to String."""
    op.execute("""
        ALTER TABLE wiki_articles 
        ALTER COLUMN tags TYPE VARCHAR(500) 
        USING tags::text
    """)


