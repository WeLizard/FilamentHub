"""One machine answers at one hostname, enforced by the database.

Revision ID: device_hostname_unique
Revises: user_provisional_since
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from alembic import op

revision = "device_hostname_unique"
down_revision = "user_provisional_since"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Whoever reported last keeps the name; the rest are cards left over from an
    # earlier pairing of the same machine and lose it. Nothing else is touched.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY user_id, printer_hostname
                           ORDER BY last_seen_at DESC NULLS LAST, id DESC
                       ) AS position
                FROM user_printer_devices
                WHERE printer_hostname IS NOT NULL
            )
            UPDATE user_printer_devices
            SET printer_hostname = NULL
            WHERE id IN (SELECT id FROM ranked WHERE position > 1)
            """
        )
    )
    op.create_unique_constraint(
        "uq_user_printer_hostname",
        "user_printer_devices",
        ["user_id", "printer_hostname"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_user_printer_hostname", "user_printer_devices", type_="unique"
    )
