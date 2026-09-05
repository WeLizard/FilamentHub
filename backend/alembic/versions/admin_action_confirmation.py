"""Add one-time administrator confirmations and bounded audit operation codes.

Revision ID: admin_action_confirmation
Revises: durable_auth_audit
"""

import sqlalchemy as sa

from alembic import op

revision = "admin_action_confirmation"
down_revision = "durable_auth_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_action_confirmations",
        sa.Column("id", sa.String(43), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(43), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("email_digest", sa.String(64), nullable=False),
        sa.Column("parameters_digest", sa.String(64), nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "action IN ('block_user', 'promote_admin', 'demote_admin', "
            "'delete_user', 'change_admin_email')",
            name="ck_admin_confirmation_action",
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= 5", name="ck_admin_confirmation_attempts"
        ),
    )
    op.create_index(
        "ix_admin_confirmation_actor_time",
        "admin_action_confirmations",
        ["actor_user_id", "created_at"],
    )
    op.create_index("ix_admin_confirmation_created", "admin_action_confirmations", ["created_at"])
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_constraint("ck_audit_events_action", type_="check")
        batch.drop_constraint("ck_audit_events_reason", type_="check")
        batch.create_check_constraint(
            "ck_audit_events_action",
            "action IN ('password_reset', 'password_change', 'auth_revoked', "
            "'admin_role_changed', 'account_deleted', 'email_change_requested', 'email_changed')",
        )
        batch.create_check_constraint(
            "ck_audit_events_reason",
            "reason IN ('recovery_grant', 'authenticated_change', 'logout', "
            "'refresh_reuse', 'admin_block', 'admin_promote', 'admin_demote', "
            "'admin_delete', 'admin_email_code')",
        )


def downgrade() -> None:
    # Preserve durable history: the preceding schema cannot represent these events.
    if op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM audit_events WHERE action NOT IN "
            "('password_reset', 'password_change', 'auth_revoked') OR reason NOT IN "
            "('recovery_grant', 'authenticated_change', 'logout', 'refresh_reuse', 'admin_block')"
        )
    ):
        raise RuntimeError("Cannot downgrade while administrator audit events exist")
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_constraint("ck_audit_events_action", type_="check")
        batch.drop_constraint("ck_audit_events_reason", type_="check")
        batch.create_check_constraint(
            "ck_audit_events_action",
            "action IN ('password_reset', 'password_change', 'auth_revoked')",
        )
        batch.create_check_constraint(
            "ck_audit_events_reason",
            "reason IN ('recovery_grant', 'authenticated_change', 'logout', "
            "'refresh_reuse', 'admin_block')",
        )
    op.drop_table("admin_action_confirmations")
