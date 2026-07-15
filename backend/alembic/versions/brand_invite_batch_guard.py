"""Prevent duplicate recipients inside one brand invitation batch.

Revision ID: brand_invite_batch_guard
Revises: email_mailbox_threads
Create Date: 2026-07-15
"""

from typing import Sequence, Union

from alembic import op

revision: str = "brand_invite_batch_guard"
down_revision: Union[str, None] = "email_mailbox_threads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_brand_invites_batch_email",
        "brand_invites",
        ["batch_id", "email"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_brand_invites_batch_email",
        "brand_invites",
        type_="unique",
    )
