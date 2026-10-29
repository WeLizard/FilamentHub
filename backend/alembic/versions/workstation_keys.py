"""Workstation keys: long-lived revocable credentials for plugin background reporting.

Revision ID: workstation_keys
Revises: connector_health_fields
"""

import sqlalchemy as sa

from alembic import op

revision = "workstation_keys"
down_revision = "connector_health_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workstation_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key_digest", name="uq_workstation_keys_digest"),
    )
    op.create_index("ix_workstation_keys_user_id", "workstation_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_workstation_keys_user_id", table_name="workstation_keys")
    op.drop_table("workstation_keys")
