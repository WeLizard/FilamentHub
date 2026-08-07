"""Let the remaining catalogue timestamps carry their timezone.

Revision ID: timestamps_carry_timezone
Revises: orca_schema_review_status
Create Date: 2026-08-07

Most of the schema already stores timestamps with a timezone; these nine tables
were left behind. Their values have always been UTC, so nothing is recomputed:
the column is only told what its numbers already mean. Without that, the API
hands the browser a time with no zone, and a browser reads such a string as
local — showing every date three hours early in Moscow and eight in Shanghai.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "timestamps_carry_timezone"
down_revision: Union[str, None] = "orca_schema_review_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS: tuple[tuple[str, str], ...] = (
    ("brand_invites", "accepted_at"),
    ("brand_invites", "created_at"),
    ("brand_invites", "expires_at"),
    ("brand_invites", "revoked_at"),
    ("brand_invites", "sent_at"),
    ("brand_requests", "created_at"),
    ("brand_requests", "processed_at"),
    ("brand_requests", "updated_at"),
    ("brand_slug_redirects", "created_at"),
    ("brands", "created_at"),
    ("brands", "updated_at"),
    ("filament_lines", "created_at"),
    ("filament_lines", "updated_at"),
    ("filament_reviews", "created_at"),
    ("filament_reviews", "updated_at"),
    ("filaments", "created_at"),
    ("filaments", "updated_at"),
    ("printer_requests", "created_at"),
    ("printer_requests", "processed_at"),
    ("printer_requests", "updated_at"),
    ("printers", "created_at"),
    ("printers", "updated_at"),
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table, column in COLUMNS:
        op.execute(
            f'ALTER TABLE {table} ALTER COLUMN "{column}" '
            f'TYPE timestamptz USING "{column}" AT TIME ZONE \'UTC\''
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table, column in COLUMNS:
        op.execute(
            f'ALTER TABLE {table} ALTER COLUMN "{column}" '
            f'TYPE timestamp USING "{column}" AT TIME ZONE \'UTC\''
        )
