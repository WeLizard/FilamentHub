"""Spool purchase date as a real column.

Revision ID: spool_purchase_date
Revises: printer_confirmation

``purchased_on`` is the day a spool was bought. Imports kept it as a
``dd.mm.yyyy`` string in ``extra``; valid dates are moved into the column and
anything else stays NULL, so spending reports fall back to the creation date.
"""

import sqlalchemy as sa

from alembic import op

revision = "spool_purchase_date"
down_revision = "printer_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_spools", sa.Column("purchased_on", sa.Date(), nullable=True))
    op.execute(
        """
        UPDATE user_spools AS s
        SET purchased_on = CASE
            WHEN p.month BETWEEN 1 AND 12 AND p.year BETWEEN 1990 AND 2100 THEN
                CASE
                    WHEN p.day BETWEEN 1 AND EXTRACT(
                        DAY FROM (make_date(p.year, p.month, 1) + INTERVAL '1 month - 1 day')
                    ) THEN make_date(p.year, p.month, p.day)
                END
        END
        FROM (
            SELECT id,
                   CAST(substr(raw, 1, 2) AS INTEGER) AS day,
                   CAST(substr(raw, 4, 2) AS INTEGER) AS month,
                   CAST(substr(raw, 7, 4) AS INTEGER) AS year
            FROM (
                SELECT id, btrim(CAST(extra AS jsonb) ->> 'purchased_on') AS raw
                FROM user_spools
            ) AS r
            WHERE raw ~ '^[0-9]{2}[.][0-9]{2}[.][0-9]{4}$'
        ) AS p
        WHERE s.id = p.id
        """
    )


def downgrade() -> None:
    op.drop_column("user_spools", "purchased_on")
