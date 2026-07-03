"""add subscriptions + app_settings, drop users.pro_access/pro_expires_at

Revision ID: add_subscriptions_settings
Revises: add_user_pro_access
Create Date: 2026-07-03

Replaces the interim per-user pro_access flag with a proper payment-ready
Subscription model (reverse trial) and a key-value app_settings table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_subscriptions_settings"
down_revision: Union[str, None] = "add_user_pro_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("trialing", "active", "past_due", "canceled", "expired", name="subscriptionstatus"),
            nullable=False,
            server_default="trialing",
        ),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_comp", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_subscriptions_id", "subscriptions", ["id"])
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"], unique=True)

    # Reverse trial: give every existing user a trialing subscription.
    op.execute(
        "INSERT INTO subscriptions "
        "(user_id, status, cancel_at_period_end, is_comp, created_at, updated_at) "
        "SELECT id, 'trialing', false, false, now(), now() FROM users"
    )

    # Superseded by the subscription model.
    op.drop_column("users", "pro_expires_at")
    op.drop_column("users", "pro_access")


def downgrade() -> None:
    """Downgrade database schema."""
    op.add_column(
        "users",
        sa.Column("pro_access", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("pro_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_table("subscriptions")
    op.drop_table("app_settings")
    sa.Enum(name="subscriptionstatus").drop(op.get_bind(), checkfirst=True)
