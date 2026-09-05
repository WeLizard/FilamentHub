"""Add durable operation audit for account credential changes and revocations.

Revision ID: durable_auth_audit
Revises: brand_monthly_analytics_release
"""

import sqlalchemy as sa

from alembic import op

revision = "durable_auth_audit"
down_revision = "brand_monthly_analytics_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "action IN ('password_reset', 'password_change', 'auth_revoked')",
            name="ck_audit_events_action",
        ),
        sa.CheckConstraint("result IN ('success')", name="ck_audit_events_result"),
        sa.CheckConstraint(
            "reason IN ('recovery_grant', 'authenticated_change', 'logout', "
            "'refresh_reuse', 'admin_block')",
            name="ck_audit_events_reason",
        ),
    )
    op.create_index("ix_audit_events_actor_time", "audit_events", ["actor_user_id", "occurred_at"])
    op.create_index(
        "ix_audit_events_target_time", "audit_events", ["target_user_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_table("audit_events")
