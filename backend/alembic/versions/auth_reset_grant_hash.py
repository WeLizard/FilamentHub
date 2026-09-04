"""Use a privacy-neutral name for the password-reset grant digest.

Revision ID: auth_reset_grant_hash
Revises: auth_recovery_hardening
"""

from __future__ import annotations

from alembic import op

revision = "auth_reset_grant_hash"
down_revision = "auth_recovery_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "password_reset_tokens",
        "token_fingerprint",
        new_column_name="grant_hash",
    )


def downgrade() -> None:
    op.alter_column(
        "password_reset_tokens",
        "grant_hash",
        new_column_name="token_fingerprint",
    )
