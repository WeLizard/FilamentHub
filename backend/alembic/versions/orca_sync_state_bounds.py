"""Add bounded Orca sync state projection and cursor indexes.

Revision ID: orca_sync_state_bounds
Revises: weighted_preset_refresh_queue
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from alembic import op

revision = "orca_sync_state_bounds"
down_revision = "weighted_preset_refresh_queue"
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
    sync_status = PGEnum(
        "success",
        "error",
        "conflict",
        name="syncstatus",
        create_type=False,
    )

    op.create_table(
        "sync_preset_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("preset_type", sync_preset_type, nullable=False),
        sa.Column("preset_id", sa.Integer(), nullable=False),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("operation", sync_operation, nullable=False),
        sa.Column("status", sync_status, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "present",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["sync_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_sync_preset_states_device_type_preset",
        "sync_preset_states",
        ["device_id", "preset_type", "preset_id"],
        unique=True,
    )
    op.create_index(
        "ix_sync_preset_states_user_device_type_preset",
        "sync_preset_states",
        ["user_id", "device_id", "preset_type", "preset_id"],
    )

    op.create_index(
        "ix_sync_history_device_version",
        "sync_history",
        ["device_id", "sync_version"],
    )
    op.create_index(
        "ix_sync_history_user_id_cursor",
        "sync_history",
        ["user_id", "id"],
    )
    op.create_index(
        "ix_sync_history_device_type_preset_cursor",
        "sync_history",
        ["device_id", "preset_type", "preset_id", "id"],
    )
    op.create_index(
        "ix_sync_devices_user_cursor",
        "sync_devices",
        ["user_id", "id"],
    )
    op.create_index(
        "ix_sync_devices_user_last_sync",
        "sync_devices",
        ["user_id", "last_sync_at", "id"],
    )

    # Preserve the latest observation for existing installations. Presence is
    # derived independently so a failed rewrite does not erase a previously
    # written managed file, while a later successful delete does.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                history.*,
                ROW_NUMBER() OVER (
                    PARTITION BY device_id, preset_type, preset_id
                    ORDER BY id DESC
                ) AS row_number,
                MAX(
                    CASE
                        WHEN operation = 'download'
                         AND status IN ('success', 'conflict')
                        THEN id ELSE 0
                    END
                ) OVER (
                    PARTITION BY device_id, preset_type, preset_id
                ) AS last_present_id,
                MAX(
                    CASE
                        WHEN operation = 'delete' AND status = 'success'
                        THEN id ELSE 0
                    END
                ) OVER (
                    PARTITION BY device_id, preset_type, preset_id
                ) AS last_removed_id
            FROM sync_history AS history
        )
        INSERT INTO sync_preset_states (
            user_id,
            device_id,
            preset_type,
            preset_id,
            sync_version,
            operation,
            status,
            error_message,
            present,
            observed_at
        )
        SELECT
            user_id,
            device_id,
            preset_type,
            preset_id,
            sync_version,
            operation,
            status,
            error_message,
            last_present_id > last_removed_id,
            created_at
        FROM ranked
        WHERE row_number = 1
        """
    )


def downgrade() -> None:
    op.drop_index("ix_sync_devices_user_last_sync", table_name="sync_devices")
    op.drop_index("ix_sync_devices_user_cursor", table_name="sync_devices")
    op.drop_index(
        "ix_sync_history_device_type_preset_cursor",
        table_name="sync_history",
    )
    op.drop_index("ix_sync_history_user_id_cursor", table_name="sync_history")
    op.drop_index("ix_sync_history_device_version", table_name="sync_history")
    op.drop_index(
        "ix_sync_preset_states_user_device_type_preset",
        table_name="sync_preset_states",
    )
    op.drop_index(
        "uq_sync_preset_states_device_type_preset",
        table_name="sync_preset_states",
    )
    op.drop_table("sync_preset_states")
