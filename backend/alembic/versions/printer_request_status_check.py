"""Keep printer request statuses within the API vocabulary.

Revision ID: printer_request_status_check
Revises: printer_request_status_varchar
"""

from alembic import op

revision = "printer_request_status_check"
down_revision = "printer_request_status_varchar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_printer_requests_status",
        "printer_requests",
        "status IN ('pending', 'approved', 'rejected')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_printer_requests_status", "printer_requests", type_="check")
