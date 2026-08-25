"""Repair sequences after migrations that inserted explicit primary keys.

Revision ID: repair_seeded_sequences
Revises: official_preset_ownership
"""

from alembic import op

revision = "repair_seeded_sequences"
down_revision = "official_preset_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # create_user_materials_brand inserted brands.id=1 explicitly. PostgreSQL
    # sequences do not advance for explicit values, so the first normal insert
    # on a clean installation otherwise tries id=1 again.
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('brands', 'id'),
            GREATEST(COALESCE((SELECT MAX(id) FROM brands), 1), 1),
            EXISTS(SELECT 1 FROM brands)
        )
        """
    )


def downgrade() -> None:
    # A sequence may have advanced through real inserts after this migration.
    # Rewinding it would risk reusing an existing primary key.
    pass
