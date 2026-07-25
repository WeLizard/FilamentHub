"""Harden administrative email and notification communications.

Revision ID: communications_hardening
Revises: material_contract_expand
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "communications_hardening"
down_revision: str | None = "material_contract_expand"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confirmation_digest", sa.String(length=64), nullable=False),
        sa.Column("confirmation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("channel = 'in_app'", name="ck_notification_campaign_channel"),
        sa.CheckConstraint(
            "audience IN ('active', 'all', 'selected')",
            name="ck_notification_campaign_audience",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'sent', 'cancelled')",
            name="ck_notification_campaign_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_notification_campaigns_created_by_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_campaigns_id", "notification_campaigns", ["id"])
    op.create_index(
        "ix_notification_campaigns_public_id",
        "notification_campaigns",
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_notification_campaigns_status", "notification_campaigns", ["status"]
    )
    op.create_index(
        "ix_notification_campaigns_confirmation_expires_at",
        "notification_campaigns",
        ["confirmation_expires_at"],
    )
    op.create_index(
        "ix_notification_campaigns_created_by_id",
        "notification_campaigns",
        ["created_by_id"],
    )
    op.create_index(
        "ix_notification_campaigns_created_at", "notification_campaigns", ["created_at"]
    )

    op.create_table(
        "notification_campaign_recipients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["notification_campaigns.id"],
            name="fk_notification_campaign_recipients_campaign_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_notification_campaign_recipients_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "user_id", name="uq_notification_campaign_recipient"
        ),
    )
    op.create_index(
        "ix_notification_campaign_recipients_campaign_id",
        "notification_campaign_recipients",
        ["campaign_id"],
    )
    op.create_index(
        "ix_notification_campaign_recipients_user_id",
        "notification_campaign_recipients",
        ["user_id"],
    )

    op.add_column("notifications", sa.Column("campaign_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_notifications_campaign_id_notification_campaigns",
        "notifications",
        "notification_campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_notifications_campaign_id", "notifications", ["campaign_id"])
    op.create_unique_constraint(
        "uq_notification_campaign_user", "notifications", ["campaign_id", "user_id"]
    )

    op.add_column("email_messages", sa.Column("html_body", sa.Text(), nullable=True))
    op.add_column(
        "email_messages",
        sa.Column("client_idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_email_messages_client_idempotency_key",
        "email_messages",
        ["client_idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_email_messages_client_idempotency_key", table_name="email_messages")
    op.drop_column("email_messages", "client_idempotency_key")
    op.drop_column("email_messages", "html_body")

    op.drop_constraint("uq_notification_campaign_user", "notifications", type_="unique")
    op.drop_index("ix_notifications_campaign_id", table_name="notifications")
    op.drop_constraint(
        "fk_notifications_campaign_id_notification_campaigns",
        "notifications",
        type_="foreignkey",
    )
    op.drop_column("notifications", "campaign_id")

    op.drop_index(
        "ix_notification_campaign_recipients_user_id",
        table_name="notification_campaign_recipients",
    )
    op.drop_index(
        "ix_notification_campaign_recipients_campaign_id",
        table_name="notification_campaign_recipients",
    )
    op.drop_table("notification_campaign_recipients")

    op.drop_index("ix_notification_campaigns_created_at", table_name="notification_campaigns")
    op.drop_index(
        "ix_notification_campaigns_created_by_id", table_name="notification_campaigns"
    )
    op.drop_index(
        "ix_notification_campaigns_confirmation_expires_at",
        table_name="notification_campaigns",
    )
    op.drop_index("ix_notification_campaigns_status", table_name="notification_campaigns")
    op.drop_index("ix_notification_campaigns_public_id", table_name="notification_campaigns")
    op.drop_index("ix_notification_campaigns_id", table_name="notification_campaigns")
    op.drop_table("notification_campaigns")
