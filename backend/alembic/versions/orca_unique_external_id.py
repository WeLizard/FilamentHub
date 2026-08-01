"""One OrcaSlicer identifier per account for presets and profiles.

Revision ID: orca_unique_external_id
Revises: orca_schema_observations
Create Date: 2026-08-01

Copies made by earlier concurrent imports keep their rows: only the OrcaSlicer
identifier is cleared on all but the newest of each group, so nothing a person
wrote is lost and the next sync matches them by name instead.
"""

from alembic import op

revision = "orca_unique_external_id"
down_revision = "orca_schema_observations"
branch_labels = None
depends_on = None

# table, owner column, index name
TARGETS = (
    ("presets", "user_id", "uq_presets_user_external_id"),
    ("printer_profiles", "owner_user_id", "uq_printer_profiles_owner_external"),
    ("print_profiles", "owner_user_id", "uq_print_profiles_owner_external"),
)


def upgrade() -> None:
    for table, owner, index_name in TARGETS:
        op.execute(
            f"""
            UPDATE {table} SET external_id = NULL
            WHERE id IN (
                SELECT id FROM (
                    SELECT id, row_number() OVER (
                        PARTITION BY {owner}, external_id ORDER BY id DESC
                    ) AS copy_rank
                    FROM {table}
                    WHERE {owner} IS NOT NULL AND external_id IS NOT NULL
                ) ranked
                WHERE copy_rank > 1
            )
            """
        )
        op.create_index(index_name, table, [owner, "external_id"], unique=True)


def downgrade() -> None:
    for table, _owner, index_name in TARGETS:
        op.drop_index(index_name, table_name=table)
