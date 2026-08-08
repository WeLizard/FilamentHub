"""Country-snapshotted filament analytics events.

Revision ID: filament_analytics_events
Revises: brand_cell_currency
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "filament_analytics_events"
down_revision: Union[str, None] = "brand_cell_currency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "filament_analytics_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filament_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["filament_id"], ["filaments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_filament_analytics_events_filament_id",
        "filament_analytics_events",
        ["filament_id"],
    )
    op.create_index(
        "ix_filament_analytics_events_event_type",
        "filament_analytics_events",
        ["event_type"],
    )
    op.create_index(
        "ix_filament_analytics_events_country",
        "filament_analytics_events",
        ["country"],
    )
    op.create_index(
        "ix_filament_analytics_events_created_at",
        "filament_analytics_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_filament_analytics_events_created_at",
        table_name="filament_analytics_events",
    )
    op.drop_index(
        "ix_filament_analytics_events_country",
        table_name="filament_analytics_events",
    )
    op.drop_index(
        "ix_filament_analytics_events_event_type",
        table_name="filament_analytics_events",
    )
    op.drop_index(
        "ix_filament_analytics_events_filament_id",
        table_name="filament_analytics_events",
    )
    op.drop_table("filament_analytics_events")
