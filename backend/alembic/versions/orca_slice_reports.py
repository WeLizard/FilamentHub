"""Remember the slices the plugin saw leaving OrcaSlicer

Revision ID: orca_slice_reports
Revises: usage_remaining
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "orca_slice_reports"
down_revision = "usage_remaining"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orca_slice_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("physical_printer_id", sa.Integer(), nullable=True),
        sa.Column("printer_profile_id", sa.Integer(), nullable=True),
        sa.Column("printer_settings_id", sa.String(length=200), nullable=True),
        sa.Column("printer_model", sa.String(length=200), nullable=True),
        sa.Column("file_name", sa.String(length=300), nullable=False),
        sa.Column("target_host", sa.String(length=50), nullable=True),
        sa.Column("slicer_version", sa.String(length=50), nullable=True),
        sa.Column("total_weight_g", sa.Float(), nullable=True),
        sa.Column("filament_weights_g", sa.JSON(), nullable=True),
        sa.Column("estimated_seconds", sa.Integer(), nullable=True),
        sa.Column("filament_changes", sa.Integer(), nullable=True),
        sa.Column("layer_count", sa.Integer(), nullable=True),
        sa.Column("sliced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["physical_printer_id"], ["user_printer_devices.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["printer_profile_id"], ["printer_profiles.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_orca_slice_reports_user_id", "orca_slice_reports", ["user_id"])
    op.create_index(
        "ix_orca_slice_reports_physical_printer_id",
        "orca_slice_reports",
        ["physical_printer_id"],
    )
    op.create_index(
        "ix_orca_slice_reports_printer_profile_id",
        "orca_slice_reports",
        ["printer_profile_id"],
    )
    op.create_index(
        "ix_orca_slice_reports_user_received",
        "orca_slice_reports",
        ["user_id", "received_at"],
    )
    # Exporting to a file and uploading to a printer fire the same seam once each.
    op.create_index(
        "uq_orca_slice_report_dedupe",
        "orca_slice_reports",
        ["user_id", "dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("orca_slice_reports")
