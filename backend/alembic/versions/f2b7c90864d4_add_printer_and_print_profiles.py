"""Add tables for printer and print profiles

Revision ID: f2b7c90864d4
Revises: cf5f5c9bd1d2
Create Date: 2025-11-07 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2b7c90864d4"
down_revision: Union[str, None] = "cf5f5c9bd1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create tables for printer and print profiles."""
    op.create_table(
        "printer_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("printer_id", sa.Integer(), sa.ForeignKey("printers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("orcaslicer_settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("start_gcode", sa.Text(), nullable=True),
        sa.Column("end_gcode", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_printer_profiles_slug"),
    )
    op.create_index(
        "ix_printer_profiles_printer_owner",
        "printer_profiles",
        ["printer_id", "owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_printer_profiles_official_active",
        "printer_profiles",
        ["is_official", "active"],
        unique=False,
    )

    op.create_table(
        "print_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("compatible_printers", sa.JSON(), nullable=True),
        sa.Column("compatible_filaments", sa.JSON(), nullable=True),
        sa.Column("orcaslicer_settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_print_profiles_slug"),
    )
    op.create_index(
        "ix_print_profiles_owner",
        "print_profiles",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_print_profiles_official_active",
        "print_profiles",
        ["is_official", "active"],
        unique=False,
    )


def downgrade() -> None:
    """Drop printer and print profile tables."""
    op.drop_index("ix_print_profiles_official_active", table_name="print_profiles")
    op.drop_index("ix_print_profiles_owner", table_name="print_profiles")
    op.drop_table("print_profiles")

    op.drop_index("ix_printer_profiles_official_active", table_name="printer_profiles")
    op.drop_index("ix_printer_profiles_printer_owner", table_name="printer_profiles")
    op.drop_table("printer_profiles")


