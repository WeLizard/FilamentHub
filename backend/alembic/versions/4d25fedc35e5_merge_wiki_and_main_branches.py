"""merge wiki and main branches

Revision ID: 4d25fedc35e5
Revises: 0de996edecbd, add_wiki_complete
Create Date: 2025-12-15 14:16:56.916143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d25fedc35e5'
down_revision: Union[str, None] = ('0de996edecbd', 'add_wiki_complete')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass

