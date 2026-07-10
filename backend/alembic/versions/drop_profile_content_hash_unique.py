"""drop unique index on print/printer profile content_hash

content_hash is a change-detection value, not an identity key. Canonical
per-vendor Orca profiles legitimately share identical settings under different
names, so a global unique index rejects valid catalog imports. The models
declare content_hash as a plain (non-unique) index; align the DB with that.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "drop_profile_hash_uq"
down_revision: Union[str, None] = "add_subscriptions_settings"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.drop_index("uq_print_profiles_content_hash", table_name="print_profiles")
    op.create_index(
        "ix_print_profiles_content_hash", "print_profiles", ["content_hash"]
    )
    op.drop_index("uq_printer_profiles_content_hash", table_name="printer_profiles")
    op.create_index(
        "ix_printer_profiles_content_hash", "printer_profiles", ["content_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_printer_profiles_content_hash", table_name="printer_profiles")
    op.create_index(
        "uq_printer_profiles_content_hash",
        "printer_profiles",
        ["content_hash"],
        unique=True,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )
    op.drop_index("ix_print_profiles_content_hash", table_name="print_profiles")
    op.create_index(
        "uq_print_profiles_content_hash",
        "print_profiles",
        ["content_hash"],
        unique=True,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )
