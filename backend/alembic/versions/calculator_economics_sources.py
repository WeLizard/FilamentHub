"""Persist field-level provenance for calculator and printer economics.

Revision ID: calculator_economics_sources
Revises: account_active_sessions
"""

import sqlalchemy as sa

from alembic import op

revision = "calculator_economics_sources"
down_revision = "account_active_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_calculator_profiles",
        sa.Column(
            "economics_field_sources",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "user_printer_devices",
        sa.Column(
            "economics_field_sources",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_printer_devices", "economics_field_sources")
    op.drop_column("user_calculator_profiles", "economics_field_sources")
