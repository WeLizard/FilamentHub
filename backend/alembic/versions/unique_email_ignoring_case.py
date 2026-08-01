"""One mailbox is one account, whatever case the address was typed in.

Revision ID: unique_email_ignoring_case
Revises: legal_document_pack
Create Date: 2026-08-01
"""

import sqlalchemy as sa

from alembic import op

revision = "unique_email_ignoring_case"
down_revision = "legal_document_pack"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The plain unique index on email only stops byte-identical duplicates, so the
    # same mailbox could be registered twice in different case. Addresses stay
    # stored as typed; only uniqueness and lookups ignore case.
    op.create_index(
        "ix_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_email_lower", table_name="users")
