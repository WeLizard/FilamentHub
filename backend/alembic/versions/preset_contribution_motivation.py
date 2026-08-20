"""add preset contribution motivation primitives

Revision ID: preset_contribution_motivation
Revises: preset_import_provenance
"""

import sqlalchemy as sa

from alembic import op

revision = "preset_contribution_motivation"
down_revision = "preset_import_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "presets",
        sa.Column("demand_signature", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_presets_demand_signature",
        "presets",
        ["demand_signature"],
        unique=False,
    )
    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=True),
        sa.Column("evidence_id", sa.Integer(), nullable=True),
        sa.Column(
            "earned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_achievements_user_id",
        "user_achievements",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_achievements_code",
        "user_achievements",
        ["code"],
        unique=False,
    )
    op.create_index(
        "uq_user_achievements_user_code",
        "user_achievements",
        ["user_id", "code"],
        unique=True,
    )
    op.create_table(
        "preset_funnel_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_preset_funnel_events_event_type",
        "preset_funnel_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_preset_funnel_events_created_at",
        "preset_funnel_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_preset_funnel_events_created_at",
        table_name="preset_funnel_events",
    )
    op.drop_index(
        "ix_preset_funnel_events_event_type",
        table_name="preset_funnel_events",
    )
    op.drop_table("preset_funnel_events")
    op.drop_index(
        "uq_user_achievements_user_code",
        table_name="user_achievements",
    )
    op.drop_index("ix_user_achievements_code", table_name="user_achievements")
    op.drop_index("ix_user_achievements_user_id", table_name="user_achievements")
    op.drop_table("user_achievements")
    op.drop_index("ix_presets_demand_signature", table_name="presets")
    op.drop_column("presets", "demand_signature")
