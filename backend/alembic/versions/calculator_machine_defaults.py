"""Standard machine numbers follow the account, not the browser

Revision ID: calc_machine_defaults
Revises: printer_economics
Create Date: 2026-07-27

Machine price, expected life, upkeep and the wattage breakdown lived only in the
browser's local storage, so a person lost them on another computer while their
per-machine economics followed the account. These columns close that gap.
"""
from alembic import op
import sqlalchemy as sa


revision = "calc_machine_defaults"
down_revision = "printer_economics"
branch_labels = None
depends_on = None


COLUMNS = (
    sa.Column("printer_purchase_price", sa.Float(), nullable=False, server_default="0"),
    sa.Column("printer_useful_hours", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("maintenance_cost_per_hour", sa.Float(), nullable=False, server_default="0"),
    sa.Column("power_hotend_w", sa.Float(), nullable=False, server_default="0"),
    sa.Column("power_bed_w", sa.Float(), nullable=False, server_default="0"),
    sa.Column("power_steppers_w", sa.Float(), nullable=False, server_default="0"),
    sa.Column("power_electronics_w", sa.Float(), nullable=False, server_default="0"),
)


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("user_calculator_profiles", column.copy())


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("user_calculator_profiles", column.name)
