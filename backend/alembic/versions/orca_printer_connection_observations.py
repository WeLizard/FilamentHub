"""OrcaSlicer plugin printer-connection observations (staging/evidence).

Revision ID: orca_conn_observations
Revises: communications_hardening
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "orca_conn_observations"
down_revision: str | None = "communications_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "orca_printer_connection_observations"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), server_default="orcaslicer_plugin", nullable=False),
        sa.Column("source_instance_id", sa.String(length=100), nullable=True),
        sa.Column("printer_settings_id", sa.String(length=200), nullable=True),
        sa.Column("preset_name", sa.String(length=200), nullable=True),
        sa.Column("inherits", sa.String(length=200), nullable=True),
        sa.Column("printer_model", sa.String(length=200), nullable=True),
        sa.Column("print_host", sa.String(length=500), nullable=True),
        sa.Column("host_type", sa.String(length=50), nullable=True),
        sa.Column("payload_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("observation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("matched_printer_profile_id", sa.Integer(), nullable=True),
        sa.Column("sanitized_payload", sa.JSON(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_printer_profile_id"], ["printer_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(f"ix_{TABLE}_owner_user_id", TABLE, ["owner_user_id"])
    op.create_index(f"ix_{TABLE}_printer_settings_id", TABLE, ["printer_settings_id"])
    op.create_index(f"ix_{TABLE}_observation_fingerprint", TABLE, ["observation_fingerprint"])
    op.create_index(f"ix_{TABLE}_matched_printer_profile_id", TABLE, ["matched_printer_profile_id"])
    op.create_index(
        "ix_orca_conn_obs_owner_fingerprint",
        TABLE,
        ["owner_user_id", "observation_fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_orca_conn_obs_owner_fingerprint", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_matched_printer_profile_id", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_observation_fingerprint", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_printer_settings_id", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_owner_user_id", table_name=TABLE)
    op.drop_table(TABLE)
