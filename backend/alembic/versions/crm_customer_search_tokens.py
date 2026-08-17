"""crm customer search tokens

Revision ID: crm_customer_search
Revises: currency_reference
Create Date: 2026-08-17

Customer details are encrypted, so searching them meant decrypting every customer on
every keystroke. These keyed hashes turn that back into an indexed lookup. The table
starts empty and is filled by ``scripts/backfill_crm_search_tokens.py``; until then a
search simply finds nothing rather than returning something wrong.
"""

from alembic import op
import sqlalchemy as sa

revision = "crm_customer_search"
down_revision = "currency_reference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_customer_search_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("crm_customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("customer_id", "token", name="uq_crm_customer_search_token"),
    )
    op.create_index(
        "ix_crm_customer_search_tokens_customer_id",
        "crm_customer_search_tokens",
        ["customer_id"],
    )
    op.create_index(
        "ix_crm_cust_search_user_token",
        "crm_customer_search_tokens",
        ["user_id", "token"],
    )


def downgrade() -> None:
    op.drop_index("ix_crm_cust_search_user_token", table_name="crm_customer_search_tokens")
    op.drop_index(
        "ix_crm_customer_search_tokens_customer_id",
        table_name="crm_customer_search_tokens",
    )
    op.drop_table("crm_customer_search_tokens")
