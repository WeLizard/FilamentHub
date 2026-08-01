"""Add aggregated observations for unknown OrcaSlicer preset fields.

Revision ID: orca_schema_observations
Revises: unique_email_ignoring_case
Create Date: 2026-08-01
"""

import sqlalchemy as sa

from alembic import op

revision = "orca_schema_observations"
down_revision = "unique_email_ignoring_case"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orca_schema_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("field_name", sa.String(length=200), nullable=False),
        sa.Column("value_shape", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="new", nullable=False),
        sa.Column("occurrences", sa.Integer(), server_default="1", nullable=False),
        sa.Column("registry_version", sa.String(length=100), nullable=False),
        sa.Column("first_source", sa.String(length=50), nullable=False),
        sa.Column("last_source", sa.String(length=50), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "field_name", "value_shape", name="uq_orca_schema_obs_field"),
    )
    op.create_index(
        "ix_orca_schema_obs_status_seen",
        "orca_schema_observations",
        ["status", "last_seen_at"],
    )
    op.create_index("ix_orca_schema_obs_scope", "orca_schema_observations", ["scope"])


def downgrade() -> None:
    op.drop_index("ix_orca_schema_obs_scope", table_name="orca_schema_observations")
    op.drop_index("ix_orca_schema_obs_status_seen", table_name="orca_schema_observations")
    op.drop_table("orca_schema_observations")
