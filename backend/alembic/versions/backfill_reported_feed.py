"""Mark printers whose feed system already reported through Spoolman

Revision ID: backfill_reported_feed
Revises: material_system_declared_slots
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "backfill_reported_feed"
down_revision = "material_system_declared_slots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # A spool carrying a printer name and a real gate index could only have been
    # written by the feed system itself, so those printers have already spoken.
    op.execute(
        sa.text(
            """
            UPDATE user_printer_devices AS d
            SET supports_hh = true
            WHERE d.supports_hh = false
              AND d.printer_hostname IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM user_spools AS s
                  WHERE s.user_id = d.user_id
                    AND s.extra ->> 'printer_name' IS NOT NULL
                    AND trim(both '"' from s.extra ->> 'printer_name') = d.printer_hostname
              )
            """
        )
    )


def downgrade() -> None:
    pass
