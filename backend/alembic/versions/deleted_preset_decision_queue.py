"""Normalize locally deleted Orca preset decisions.

Revision ID: deleted_preset_queue
Revises: physical_printer_feed_idx
"""

import sqlalchemy as sa

from alembic import op

revision = "deleted_preset_queue"
down_revision = "physical_printer_feed_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deleted_preset_decision_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("preset_id", sa.Integer(), nullable=False),
        sa.Column("preset_name", sa.String(length=500), nullable=False),
        sa.Column("bundle_preset_name", sa.String(length=500), nullable=True),
        sa.Column("is_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_saved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_id", "preset_id", name="uq_deleted_preset_notification_preset"
        ),
    )
    op.create_index(
        "ix_deleted_preset_notification_id",
        "deleted_preset_decision_items",
        ["notification_id", "id"],
    )
    op.execute(
        """
        INSERT INTO deleted_preset_decision_items
            (notification_id, preset_id, preset_name, bundle_preset_name, is_created, is_saved)
        SELECT n.id,
               (item->>'preset_id')::integer,
               left(coalesce(nullif(item->>'preset_name', ''), 'Unknown preset'), 500),
               left(item->>'bundle_preset_name', 500),
               CASE WHEN lower(item->>'is_created') IN ('true', 'false')
                    THEN (item->>'is_created')::boolean ELSE false END,
               CASE WHEN lower(item->>'is_saved') IN ('true', 'false')
                    THEN (item->>'is_saved')::boolean ELSE false END
        FROM notifications AS n
        CROSS JOIN LATERAL json_array_elements(
            CASE
                WHEN json_typeof(n.extra_data->'deleted_presets') = 'array'
                THEN n.extra_data->'deleted_presets'
                ELSE '[]'::json
            END
        ) AS item
        WHERE n.type = 'preset_locally_deleted'
          AND n.read IS FALSE
          AND (item->>'preset_id') ~ '^[1-9][0-9]*$'
          AND (item->>'preset_id')::numeric <= 2147483647
        ON CONFLICT (notification_id, preset_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_deleted_preset_notification_id", table_name="deleted_preset_decision_items")
    op.drop_table("deleted_preset_decision_items")
