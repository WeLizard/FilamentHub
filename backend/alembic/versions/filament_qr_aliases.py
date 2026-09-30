"""Preserve printed product QR codes after catalog filament merges.

Revision ID: filament_qr_aliases
Revises: feedback_plugin_log
"""

import sqlalchemy as sa

from alembic import op

revision = "filament_qr_aliases"
down_revision = "feedback_plugin_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "filament_qr_aliases",
        sa.Column("code", sa.String(length=50), primary_key=True),
        sa.Column("filament_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["filament_id"], ["filaments.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_filament_qr_aliases_filament_id",
        "filament_qr_aliases",
        ["filament_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_filament_qr_aliases_filament_id", table_name="filament_qr_aliases")
    op.drop_table("filament_qr_aliases")
