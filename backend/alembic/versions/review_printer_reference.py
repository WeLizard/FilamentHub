"""A review can name the machine it is about, not just describe it.

Revision ID: review_printer_reference
Revises: email_send_reservations
Create Date: 2026-08-02

The printer was free text, so the same machine arrived as "Voron 2.4",
"voron 2.4" and "Ворон 2.4" and nothing could be counted. The text stays for a
self-build that no catalogue lists; a picked machine now also leaves a
reference. Existing reviews keep their text and gain no reference — nobody can
say for them which machine they meant.
"""

import sqlalchemy as sa

from alembic import op

revision = "review_printer_reference"
down_revision = "email_send_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "filament_reviews",
        sa.Column("printer_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_filament_reviews_printer_id", "filament_reviews", ["printer_id"]
    )
    op.create_foreign_key(
        "fk_filament_reviews_printer_id",
        "filament_reviews",
        "printers",
        ["printer_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_filament_reviews_printer_id", "filament_reviews", type_="foreignkey"
    )
    op.drop_index("ix_filament_reviews_printer_id", table_name="filament_reviews")
    op.drop_column("filament_reviews", "printer_id")
