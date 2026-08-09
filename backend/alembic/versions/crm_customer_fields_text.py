"""Widen encrypted CRM customer fields to text.

Revision ID: crm_customer_fields_text
Revises: wiki_media_assets
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "crm_customer_fields_text"
down_revision: str | None = "wiki_media_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENCRYPTED_FIELDS = (
    "name",
    "contact_name",
    "email",
    "phone",
    "inn",
    "address",
    "note",
)


def upgrade() -> None:
    for column in ENCRYPTED_FIELDS:
        op.alter_column(
            "crm_customers",
            column,
            type_=sa.Text(),
            existing_nullable=column != "name",
        )


def downgrade() -> None:
    # Ciphertext written after this migration may exceed the original VARCHAR
    # limits. Narrowing the columns would risk truncating customer data, so the
    # storage-safe TEXT representation is intentionally retained on rollback.
    pass
