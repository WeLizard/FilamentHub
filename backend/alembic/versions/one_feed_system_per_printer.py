"""Keep a printer to a single feed system

Revision ID: one_feed_per_printer
Revises: device_reports_feed
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "one_feed_per_printer"
down_revision = "device_reports_feed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    duplicates = op.get_bind().execute(
        sa.text(
            """
            SELECT physical_printer_id, count(*) AS systems
            FROM material_systems
            GROUP BY physical_printer_id
            HAVING count(*) > 1
            ORDER BY physical_printer_id
            """
        )
    ).all()
    if duplicates:
        # Merging them means deciding which one owns the spools in the slots,
        # which is a person's call, so say plainly what to look at.
        listed = ", ".join(f"printer {row[0]}: {row[1]} systems" for row in duplicates)
        raise RuntimeError(
            "Cannot enforce one feed system per printer while these have more "
            f"than one ({listed}). Keep one system on each and run again."
        )
    op.create_index(
        "uq_material_system_per_printer",
        "material_systems",
        ["physical_printer_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_material_system_per_printer", table_name="material_systems")
