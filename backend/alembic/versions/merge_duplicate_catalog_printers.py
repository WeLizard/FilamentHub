"""Merge catalog printers a person's account created before the bundle arrived

Revision ID: merge_dup_printers
Revises: merge_dup_profiles
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "merge_dup_printers"
down_revision = "merge_dup_profiles"
branch_labels = None
depends_on = None


# Before the OrcaSlicer bundle was imported, a machine could enter the catalog on
# its own; the bundle then brought the same models as system records. Two records
# for one model split a person's printers in half — one looks at each — so the
# user-made record hands everything over to the system one, which is the record
# the bundle keeps up to date.
_PAIRS = """
    SELECT mine.id AS mine_id, mine.slug AS mine_slug,
           theirs.id AS theirs_id, theirs.slug AS theirs_slug
    FROM printers AS mine
    JOIN printers AS theirs
      ON theirs.source = 'system'
     AND lower(theirs.name) = lower(mine.name)
     AND theirs.id <> mine.id
    WHERE mine.source <> 'system'
"""


def upgrade() -> None:
    bind = op.get_bind()
    pairs = bind.execute(sa.text(_PAIRS)).all()

    for mine_id, mine_slug, theirs_id, theirs_slug in pairs:
        params = {"mine": mine_id, "theirs": theirs_id}

        # A preset already tied to the surviving record would double up.
        bind.execute(
            sa.text(
                """
                DELETE FROM preset_printers AS victim
                WHERE victim.printer_id = :mine
                  AND EXISTS (
                      SELECT 1 FROM preset_printers AS kept
                      WHERE kept.printer_id = :theirs
                        AND kept.preset_id = victim.preset_id
                  )
                """
            ),
            params,
        )
        for table in ("preset_printers", "printer_profiles", "user_printer_devices"):
            bind.execute(
                sa.text(f"UPDATE {table} SET printer_id = :theirs WHERE printer_id = :mine"),
                params,
            )

        # Process compatibility points at a printer by slug as well as by id.
        bind.execute(
            sa.text(
                """
                DELETE FROM print_profile_printers AS victim
                WHERE victim.printer_id = :mine
                  AND EXISTS (
                      SELECT 1 FROM print_profile_printers AS kept
                      WHERE kept.printer_id = :theirs
                        AND kept.print_profile_id = victim.print_profile_id
                  )
                """
            ),
            params,
        )
        bind.execute(
            sa.text(
                "UPDATE print_profile_printers SET printer_id = :theirs, printer_slug = :theirs_slug "
                "WHERE printer_id = :mine"
            ),
            {**params, "theirs_slug": theirs_slug},
        )
        # Links recorded by slug alone, with no id resolved at the time.
        bind.execute(
            sa.text(
                "UPDATE print_profile_printers SET printer_slug = :theirs_slug "
                "WHERE printer_id IS NULL AND printer_slug = :mine_slug"
            ),
            {"theirs_slug": theirs_slug, "mine_slug": mine_slug},
        )

        bind.execute(sa.text("DELETE FROM printers WHERE id = :mine"), params)


def downgrade() -> None:
    # The merged record cannot be told from the surviving one afterwards.
    pass
