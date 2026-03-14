"""Add calculator history entries table.

Revision ID: c8d34f71b2aa
Revises: a4c6b3d8e9f1
Create Date: 2026-03-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8d34f71b2aa"
down_revision: Union[str, Sequence[str], None] = "a4c6b3d8e9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calculator_history_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("pricing_method", sa.String(length=32), nullable=False),
        sa.Column("request_data", sa.JSON(), nullable=False),
        sa.Column("result_data", sa.JSON(), nullable=False),
        sa.Column("parsed_gcode", sa.JSON(), nullable=True),
        sa.Column("filament_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_calculator_history_entries_created_at"),
        "calculator_history_entries",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_calculator_history_entries_id"),
        "calculator_history_entries",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_calculator_history_entries_pricing_method"),
        "calculator_history_entries",
        ["pricing_method"],
        unique=False,
    )
    op.create_index(
        op.f("ix_calculator_history_entries_user_id"),
        "calculator_history_entries",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_calculator_history_entries_user_id"), table_name="calculator_history_entries")
    op.drop_index(op.f("ix_calculator_history_entries_pricing_method"), table_name="calculator_history_entries")
    op.drop_index(op.f("ix_calculator_history_entries_id"), table_name="calculator_history_entries")
    op.drop_index(op.f("ix_calculator_history_entries_created_at"), table_name="calculator_history_entries")
    op.drop_table("calculator_history_entries")
