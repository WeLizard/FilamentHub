"""add provider-neutral print job history

Revision ID: print_job_history
Revises: printer_bridge_credentials
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "print_job_history"
down_revision: str | None = "printer_bridge_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "print_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("logical_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("physical_printer_id", sa.Integer(), nullable=True),
        sa.Column("calculator_history_id", sa.Integer(), nullable=True),
        sa.Column("calculator_job_key", sa.String(length=160), nullable=True),
        sa.Column("orca_slice_report_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_ref", sa.String(length=200), nullable=False),
        sa.Column("source_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("printer_name_snapshot", sa.String(length=200), nullable=True),
        sa.Column("calculation_title_snapshot", sa.String(length=255), nullable=True),
        sa.Column("file_name_snapshot", sa.String(length=300), nullable=True),
        sa.Column("estimated_duration_s", sa.Float(), nullable=True),
        sa.Column("actual_duration_s", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["calculator_history_id"],
            ["calculator_history_entries.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["orca_slice_report_id"], ["orca_slice_reports.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["physical_printer_id"], ["user_printer_devices.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("logical_id"),
        sa.UniqueConstraint("user_id", "source", "source_ref", name="uq_print_job_source_ref"),
    )
    op.create_index("ix_print_jobs_user_id", "print_jobs", ["user_id"])
    op.create_index("ix_print_jobs_status", "print_jobs", ["status"])
    op.create_index("ix_print_jobs_user_status", "print_jobs", ["user_id", "status", "created_at"])
    op.create_index("ix_print_jobs_printer", "print_jobs", ["physical_printer_id", "created_at"])

    op.create_table(
        "print_job_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("print_job_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["print_job_id"], ["print_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("print_job_id", "event_key", name="uq_print_job_event_key"),
    )
    op.create_index("ix_print_job_events_user", "print_job_events", ["user_id"])
    op.create_index("ix_print_job_events_time", "print_job_events", ["print_job_id", "occurred_at"])

    op.create_table(
        "print_job_materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("print_job_id", sa.Integer(), nullable=False),
        sa.Column("spool_id", sa.Integer(), nullable=True),
        sa.Column("material_line_key", sa.String(length=160), nullable=True),
        sa.Column("tool_index", sa.Integer(), nullable=True),
        sa.Column("planned_weight_g", sa.Float(), nullable=True),
        sa.Column("spool_snapshot", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["print_job_id"], ["print_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spool_id"], ["user_spools.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_print_job_materials_job", "print_job_materials", ["print_job_id"])
    op.create_index("ix_print_job_materials_spool", "print_job_materials", ["spool_id"])

    op.add_column("preset_usage_events", sa.Column("print_job_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_usage_event_print_job",
        "preset_usage_events",
        "print_jobs",
        ["print_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_preset_usage_print_job", "preset_usage_events", ["print_job_id"])


def downgrade() -> None:
    op.drop_index("ix_preset_usage_print_job", table_name="preset_usage_events")
    op.drop_constraint("fk_usage_event_print_job", "preset_usage_events", type_="foreignkey")
    op.drop_column("preset_usage_events", "print_job_id")
    op.drop_index("ix_print_job_materials_spool", table_name="print_job_materials")
    op.drop_index("ix_print_job_materials_job", table_name="print_job_materials")
    op.drop_table("print_job_materials")
    op.drop_index("ix_print_job_events_time", table_name="print_job_events")
    op.drop_index("ix_print_job_events_user", table_name="print_job_events")
    op.drop_table("print_job_events")
    op.drop_index("ix_print_jobs_printer", table_name="print_jobs")
    op.drop_index("ix_print_jobs_user_status", table_name="print_jobs")
    op.drop_index("ix_print_jobs_status", table_name="print_jobs")
    op.drop_index("ix_print_jobs_user_id", table_name="print_jobs")
    op.drop_table("print_jobs")
