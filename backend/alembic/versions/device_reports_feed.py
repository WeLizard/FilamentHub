"""Tell a reporting printer apart from a Happy Hare printer

Revision ID: device_reports_feed
Revises: user_legal_acceptance
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "device_reports_feed"
down_revision = "user_legal_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_printer_devices",
        sa.Column(
            "reports_feed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Until now the Happy Hare flag doubled as "this printer has spoken", so
    # everything it marked is exactly the set of printers that already report.
    op.execute(sa.text("UPDATE user_printer_devices SET reports_feed = supports_hh"))


def downgrade() -> None:
    op.drop_column("user_printer_devices", "reports_feed")
