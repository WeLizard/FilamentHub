"""Add durable staging for chunked OrcaSlicer sync reports.

Revision ID: orca_sync_report_chunks
Revises: orca_sync_state_bounds
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from alembic import op

revision = "orca_sync_report_chunks"
down_revision = "orca_sync_state_bounds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sync_preset_type = PGEnum(
        "filament",
        "printer",
        "print",
        name="syncpresettype",
        create_type=False,
    )
    sync_operation = PGEnum(
        "download",
        "upload",
        "delete",
        name="syncoperation",
        create_type=False,
    )

    op.create_table(
        "sync_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["device_id"], ["sync_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_sync_reports_device_version",
        "sync_reports",
        ["device_id", "sync_version"],
        unique=True,
    )
    op.create_index(
        "uq_sync_reports_user_report_id",
        "sync_reports",
        ["user_id", "report_id"],
        unique=True,
    )

    op.create_table(
        "sync_report_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_pk", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["report_pk"], ["sync_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_sync_report_chunks_report_index",
        "sync_report_chunks",
        ["report_pk", "chunk_index"],
        unique=True,
    )

    op.create_table(
        "sync_report_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_pk", sa.Integer(), nullable=False),
        sa.Column("chunk_pk", sa.Integer(), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("preset_type", sync_preset_type, nullable=False),
        sa.Column("operation", sync_operation, nullable=False),
        sa.Column("preset_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["chunk_pk"], ["sync_report_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_pk"], ["sync_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sync_report_items_report_cursor",
        "sync_report_items",
        ["report_pk", "id"],
    )
    op.create_index(
        "uq_sync_report_items_result_key",
        "sync_report_items",
        ["report_pk", "preset_type", "operation", "preset_id"],
        unique=True,
    )
    op.create_index(
        "uq_sync_report_items_chunk_position",
        "sync_report_items",
        ["chunk_pk", "item_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_sync_report_items_chunk_position",
        table_name="sync_report_items",
    )
    op.drop_index("uq_sync_report_items_result_key", table_name="sync_report_items")
    op.drop_index("ix_sync_report_items_report_cursor", table_name="sync_report_items")
    op.drop_table("sync_report_items")
    op.drop_index(
        "uq_sync_report_chunks_report_index",
        table_name="sync_report_chunks",
    )
    op.drop_table("sync_report_chunks")
    op.drop_index("uq_sync_reports_user_report_id", table_name="sync_reports")
    op.drop_index("uq_sync_reports_device_version", table_name="sync_reports")
    op.drop_table("sync_reports")
