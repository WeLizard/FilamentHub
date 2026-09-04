"""Add durable account auth versioning and password-reset grants.

Revision ID: auth_recovery_hardening
Revises: filament_technical_data
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "auth_recovery_hardening"
down_revision = "filament_technical_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_users_auth_version_nonnegative",
        "users",
        "auth_version >= 0",
    )
    op.create_table(
        "password_reset_tokens",
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_fingerprint"),
    )
    op.create_index(
        "ix_password_reset_tokens_expiry",
        "password_reset_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_password_reset_tokens_user",
        "password_reset_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_tokens_user",
        table_name="password_reset_tokens",
    )
    op.drop_index(
        "ix_password_reset_tokens_expiry",
        table_name="password_reset_tokens",
    )
    op.drop_table("password_reset_tokens")
    op.drop_constraint(
        "ck_users_auth_version_nonnegative",
        "users",
        type_="check",
    )
    op.drop_column("users", "auth_version")
