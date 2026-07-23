"""User catalog recommendation selection (physical printer + configuration).

Adds a per-user "recommend for my printer" choice so it follows the account
across devices instead of living only in the browser. FK SET NULL clears the
choice automatically when the referenced printer/configuration is deleted.

Revision ID: user_recommend_selection
Revises: printer_conn_bindings
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "user_recommend_selection"
down_revision: str | None = "printer_conn_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_PRINTER = "fk_users_recommend_physical_printer"
FK_PROFILE = "fk_users_recommend_printer_profile"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("recommend_physical_printer_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("recommend_printer_profile_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        FK_PRINTER,
        "users",
        "user_printer_devices",
        ["recommend_physical_printer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        FK_PROFILE,
        "users",
        "printer_profiles",
        ["recommend_printer_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(FK_PROFILE, "users", type_="foreignkey")
    op.drop_constraint(FK_PRINTER, "users", type_="foreignkey")
    op.drop_column("users", "recommend_printer_profile_id")
    op.drop_column("users", "recommend_physical_printer_id")
