"""Store printer_requests.status as VARCHAR(20) to match the ORM model.

The PrinterRequest ORM model maps status as String(20) (mirroring BrandRequest),
while an early migration created a native PostgreSQL enum printerrequeststatus.
Widening the column to VARCHAR(20) aligns PostgreSQL with the ORM and SQLite
tests without losing existing values or requiring ALTER TYPE for new statuses.

Revision ID: printer_request_status_varchar
Revises: preset_version_filament
"""

from alembic import op

revision = "printer_request_status_varchar"
down_revision = "preset_version_filament"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE printer_requests ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE printer_requests "
        "ALTER COLUMN status TYPE VARCHAR(20) USING status::text"
    )
    op.execute(
        "ALTER TABLE printer_requests ALTER COLUMN status SET DEFAULT 'pending'"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE printerrequeststatus AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )
    op.execute("ALTER TABLE printer_requests ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE printer_requests "
        "ALTER COLUMN status TYPE printerrequeststatus "
        "USING status::printerrequeststatus"
    )
    op.execute(
        "ALTER TABLE printer_requests "
        "ALTER COLUMN status SET DEFAULT 'pending'::printerrequeststatus"
    )
