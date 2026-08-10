"""Store exact print-profile identity on Orca slice reports.

Revision ID: orca_slice_profile_ids
Revises: crm_customer_fields_text
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "orca_slice_profile_ids"
down_revision: str | None = "crm_customer_fields_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orca_slice_reports",
        sa.Column("print_settings_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "orca_slice_reports",
        sa.Column("print_profile_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_orca_slice_print_profile",
        "orca_slice_reports",
        "print_profiles",
        ["print_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_orca_slice_reports_print_profile_id",
        "orca_slice_reports",
        ["print_profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_orca_slice_reports_print_profile_id", table_name="orca_slice_reports")
    op.drop_constraint(
        "fk_orca_slice_print_profile",
        "orca_slice_reports",
        type_="foreignkey",
    )
    op.drop_column("orca_slice_reports", "print_profile_id")
    op.drop_column("orca_slice_reports", "print_settings_id")
