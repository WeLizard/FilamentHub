"""Waitlist interest on the existing subscription lifecycle.

Revision ID: subscription_interest
Revises: stock_alert_rules

Forward-compatible: one PostgreSQL enum label and two nullable columns. The
enum label cannot be removed again, so the downgrade leaves it in place. Rows
with waitlist statuses would be unreadable by older code, so downgrade refuses
while they exist.
"""

import sqlalchemy as sa

from alembic import op

revision = "subscription_interest"
down_revision = "stock_alert_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'interested'"
            )
    op.add_column(
        "subscriptions",
        sa.Column("interested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("interest_source", sa.String(length=32), nullable=True),
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
    op.drop_column("subscriptions", "interest_source")
    op.drop_column("subscriptions", "interested_at")
    # PostgreSQL enum labels are not removed: another row may already use it.
