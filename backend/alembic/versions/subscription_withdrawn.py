"""Waitlist withdrawal status.

Revision ID: subscription_withdrawn
Revises: subscription_interest

Forward-compatible: adds one PostgreSQL enum label. The label cannot be removed
again, and a downgrade with waitlist rows would make those rows unreadable by
older code, so the downgrade refuses while such rows exist.
"""

import sqlalchemy as sa

from alembic import op

revision = "subscription_withdrawn"
down_revision = "subscription_interest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'withdrawn'"
            )


def downgrade() -> None:
    rows = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM subscriptions "
            "WHERE CAST(status AS text) IN ('interested', 'withdrawn')"
        )
    ).scalar()
    if rows:
        raise RuntimeError(
            "Cannot downgrade subscription statuses while waitlist rows exist"
        )
    # PostgreSQL enum labels are not removed: another row may already use them.
