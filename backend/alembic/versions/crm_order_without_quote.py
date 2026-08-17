"""an order no longer requires a quote

Revision ID: crm_order_no_quote
Revises: crm_customer_search
Create Date: 2026-08-17

A repeat job from a known customer had to be preceded by a commercial proposal nobody
asked for, because the column demanded one. Making it optional says what is actually
true: an order may have come from a quote.

The unique constraint stays and keeps its meaning — one quote produces at most one
order — because Postgres allows several NULLs in a unique index.
"""

from alembic import op
import sqlalchemy as sa

revision = "crm_order_no_quote"
down_revision = "crm_customer_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "crm_orders",
        "quote_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Orders booked without a quote have no value to put here, so narrowing the column
    # back would fail on exactly the rows this change exists for.
    op.execute("DELETE FROM crm_orders WHERE quote_id IS NULL")
    op.alter_column(
        "crm_orders",
        "quote_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
