"""add compat_context to presets

Hardware provenance bag: the extensible set of ways a user's printer differs
from the factory default (nozzle type, kinematics, plate, cooling, ...). Kept
schemaless so it grows without migrations; exported as provenance, not as
blocking compatibility.
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "preset_compat_context"
down_revision: Union[str, None] = "crm_lite_workspace"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("presets", sa.Column("compat_context", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("presets", "compat_context")
