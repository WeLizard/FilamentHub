"""Add durable account email-change proofs.

Revision ID: account_email_change_proof
Revises: octoprint_reported_slot_source
"""

import sqlalchemy as sa

from alembic import op

revision = "account_email_change_proof"
down_revision = "octoprint_reported_slot_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_email_change_confirmations",
        sa.Column("id", sa.String(43), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(43), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("current_email_digest", sa.String(64), nullable=False),
        sa.Column("new_email_digest", sa.String(64), nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("link_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= 5", name="ck_account_email_change_attempts"
        ),
    )
    op.create_index(
        "ix_account_email_change_user_time",
        "account_email_change_confirmations",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_account_email_change_created",
        "account_email_change_confirmations",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_email_change_created", table_name="account_email_change_confirmations"
    )
    op.drop_index(
        "ix_account_email_change_user_time", table_name="account_email_change_confirmations"
    )
    op.drop_table("account_email_change_confirmations")
