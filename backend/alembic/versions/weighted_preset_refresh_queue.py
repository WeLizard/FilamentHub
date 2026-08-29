"""Add durable coalescing queue for weighted preset rebuilds.

Revision ID: weighted_preset_refresh_queue
Revises: preset_version_selection
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "weighted_preset_refresh_queue"
down_revision = "preset_version_selection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weighted_preset_refresh_jobs",
        sa.Column("filament_id", sa.Integer(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["filament_id"],
            ["filaments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("filament_id"),
    )
    op.create_index(
        "ix_weighted_preset_refresh_jobs_next_attempt_at",
        "weighted_preset_refresh_jobs",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weighted_preset_refresh_jobs_next_attempt_at",
        table_name="weighted_preset_refresh_jobs",
    )
    op.drop_table("weighted_preset_refresh_jobs")
