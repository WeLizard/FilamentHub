"""Add normalized local printer bridge observations.

Revision ID: printer_bridge_observations
Revises: crm_order_spool_reservations
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "printer_bridge_observations"
down_revision: str | None = "crm_order_spool_reservations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "physical_printer_connectors",
        sa.Column("source_instance_id", sa.String(length=100), nullable=True),
    )
    op.create_table(
        "physical_printer_status_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("remaining_seconds", sa.Integer(), nullable=True),
        sa.Column("current_layer", sa.Integer(), nullable=True),
        sa.Column("total_layers", sa.Integer(), nullable=True),
        sa.Column("job_name", sa.String(length=300), nullable=True),
        sa.Column("nozzle_temperature", sa.Float(), nullable=True),
        sa.Column("nozzle_target_temperature", sa.Float(), nullable=True),
        sa.Column("bed_temperature", sa.Float(), nullable=True),
        sa.Column("bed_target_temperature", sa.Float(), nullable=True),
        sa.Column("chamber_temperature", sa.Float(), nullable=True),
        sa.Column("wifi_signal", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["physical_printer_connectors.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id"),
    )
    op.create_index(
        "ix_printer_status_obs_user",
        "physical_printer_status_observations",
        ["user_id"],
    )
    op.create_table(
        "material_slot_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column("material_slot_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("present", sa.Boolean(), nullable=True),
        sa.Column("active_feed", sa.Boolean(), nullable=True),
        sa.Column("material", sa.String(length=80), nullable=True),
        sa.Column("color_hex", sa.String(length=6), nullable=True),
        sa.Column("remaining_percent", sa.Integer(), nullable=True),
        sa.Column("remaining_grams", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["physical_printer_connectors.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["material_slot_id"], ["material_slots.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connector_id",
            "material_slot_id",
            name="uq_material_slot_observation_connector_slot",
        ),
    )
    op.create_index(
        "ix_material_slot_obs_connector",
        "material_slot_observations",
        ["connector_id"],
    )
    op.create_index(
        "ix_material_slot_obs_user",
        "material_slot_observations",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_material_slot_obs_user", table_name="material_slot_observations")
    op.drop_index(
        "ix_material_slot_obs_connector", table_name="material_slot_observations"
    )
    op.drop_table("material_slot_observations")
    op.drop_index(
        "ix_printer_status_obs_user",
        table_name="physical_printer_status_observations",
    )
    op.drop_table("physical_printer_status_observations")
    op.drop_column("physical_printer_connectors", "source_instance_id")
