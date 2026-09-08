"""Add temporary owner-bound Calculator G-code artifacts.

Revision ID: calculator_gcode_artifacts
Revises: admin_action_confirmation
"""

import sqlalchemy as sa

from alembic import op

revision = "calculator_gcode_artifacts"
down_revision = "admin_action_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calculator_gcode_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("storage_key", sa.String(64), nullable=True, unique=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="uploading"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "state IN ('uploading', 'ready', 'failed', 'cancelled')",
            name="ck_calc_gcode_artifact_state",
        ),
        sa.CheckConstraint(
            "expected_size_bytes > 0",
            name="ck_calc_gcode_artifact_size",
        ),
    )
    op.create_index(
        "ix_calc_gcode_owner_expiry",
        "calculator_gcode_artifacts",
        ["owner_user_id", "expires_at"],
    )
    op.create_index(
        "ix_calc_gcode_state_expiry",
        "calculator_gcode_artifacts",
        ["state", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("calculator_gcode_artifacts")
