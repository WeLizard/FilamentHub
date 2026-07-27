"""What a person's own machine costs to run, kept beside the machine

Revision ID: printer_economics
Revises: orca_slice_reports
Create Date: 2026-07-26

These live on the FilamentHub device record, never in the OrcaSlicer preset:
the preset must stay exactly what the slicer wrote. All columns are optional —
a machine without them behaves as before, on the account-wide economics profile.
"""
from alembic import op
import sqlalchemy as sa


revision = "printer_economics"
down_revision = "orca_slice_reports"
branch_labels = None
depends_on = None


COLUMNS = (
    sa.Column("purchase_cost", sa.Float(), nullable=True),
    sa.Column("residual_value", sa.Float(), nullable=True),
    sa.Column("useful_life_hours", sa.Integer(), nullable=True),
    sa.Column("average_power_watts", sa.Float(), nullable=True),
    # The parts that add up to the average draw, kept per machine because two
    # printers of the same model rarely carry the same heaters and board.
    sa.Column("power_hotend_w", sa.Float(), nullable=True),
    sa.Column("power_bed_w", sa.Float(), nullable=True),
    sa.Column("power_steppers_w", sa.Float(), nullable=True),
    sa.Column("power_electronics_w", sa.Float(), nullable=True),
    sa.Column("maintenance_cost_per_hour", sa.Float(), nullable=True),
    sa.Column("machine_hour_rate", sa.Float(), nullable=True),
    # The currency the two money fields were entered in, so changing the
    # account currency later cannot silently reinterpret them.
    sa.Column("economics_currency", sa.String(length=4), nullable=True),
)


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("user_printer_devices", column.copy())


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("user_printer_devices", column.name)
