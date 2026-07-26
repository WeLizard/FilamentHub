"""Merge configurations and processes duplicated by identifier changes

Revision ID: merge_dup_profiles
Revises: one_feed_per_printer
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "merge_dup_profiles"
down_revision = "one_feed_per_printer"
branch_labels = None
depends_on = None


# Orca's preset identifiers changed format several times, and the sync used to
# create a new row whenever it failed to recognise one. The name survived every
# change, so rows sharing an owner and a name describe one preset: the newest is
# kept and everything pointing at the older ones is moved onto it.
_GROUPS = """
    WITH ranked AS (
        SELECT id, owner_user_id, name,
               row_number() OVER (
                   PARTITION BY owner_user_id, name ORDER BY id DESC
               ) AS rn
        FROM {table}
        WHERE owner_user_id IS NOT NULL AND is_official = false
    )
    SELECT d.id AS doomed_id, k.id AS keep_id
    FROM ranked d
    JOIN ranked k
      ON k.owner_user_id = d.owner_user_id AND k.name = d.name AND k.rn = 1
    WHERE d.rn > 1
"""


def _pairs(bind, table: str) -> list[tuple[int, int]]:
    rows = bind.execute(sa.text(_GROUPS.format(table=table))).all()
    return [(row[0], row[1]) for row in rows]


def upgrade() -> None:
    bind = op.get_bind()

    for doomed_id, keep_id in _pairs(bind, "printer_profiles"):
        for table, column, sibling in (
            ("user_printer_profile_links", "printer_profile_id", "physical_printer_id"),
            ("user_saved_preset_targets", "printer_profile_id", "user_saved_preset_id"),
        ):
            # A row already pointing at the survivor would collide on the pair's
            # unique constraint, so those are dropped instead of moved.
            bind.execute(
                sa.text(
                    f"""
                    DELETE FROM {table} AS victim
                    WHERE victim.{column} = :doomed
                      AND EXISTS (
                          SELECT 1 FROM {table} AS kept
                          WHERE kept.{column} = :keep
                            AND kept.{sibling} = victim.{sibling}
                      )
                    """
                ),
                {"doomed": doomed_id, "keep": keep_id},
            )
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = :keep WHERE {column} = :doomed"),
                {"doomed": doomed_id, "keep": keep_id},
            )

        bind.execute(
            sa.text(
                "UPDATE users SET recommend_printer_profile_id = :keep "
                "WHERE recommend_printer_profile_id = :doomed"
            ),
            {"doomed": doomed_id, "keep": keep_id},
        )
        bind.execute(
            sa.text(
                "UPDATE orca_printer_connection_observations "
                "SET matched_printer_profile_id = :keep "
                "WHERE matched_printer_profile_id = :doomed"
            ),
            {"doomed": doomed_id, "keep": keep_id},
        )
        bind.execute(
            sa.text("DELETE FROM printer_profiles WHERE id = :doomed"),
            {"doomed": doomed_id},
        )

    for doomed_id, keep_id in _pairs(bind, "print_profiles"):
        # Compatibility links live on the older rows, so losing them would tell a
        # person their process no longer fits any of their machines.
        bind.execute(
            sa.text(
                """
                DELETE FROM print_profile_printers AS victim
                WHERE victim.print_profile_id = :doomed
                  AND EXISTS (
                      SELECT 1 FROM print_profile_printers AS kept
                      WHERE kept.print_profile_id = :keep
                        AND kept.printer_slug = victim.printer_slug
                  )
                """
            ),
            {"doomed": doomed_id, "keep": keep_id},
        )
        bind.execute(
            sa.text(
                "UPDATE print_profile_printers SET print_profile_id = :keep "
                "WHERE print_profile_id = :doomed"
            ),
            {"doomed": doomed_id, "keep": keep_id},
        )
        bind.execute(
            sa.text(
                """
                DELETE FROM print_profile_filaments AS victim
                WHERE victim.print_profile_id = :doomed
                  AND EXISTS (
                      SELECT 1 FROM print_profile_filaments AS kept
                      WHERE kept.print_profile_id = :keep
                        AND kept.filament_id = victim.filament_id
                  )
                """
            ),
            {"doomed": doomed_id, "keep": keep_id},
        )
        bind.execute(
            sa.text(
                "UPDATE print_profile_filaments SET print_profile_id = :keep "
                "WHERE print_profile_id = :doomed"
            ),
            {"doomed": doomed_id, "keep": keep_id},
        )
        bind.execute(
            sa.text("DELETE FROM print_profiles WHERE id = :doomed"),
            {"doomed": doomed_id},
        )


def downgrade() -> None:
    # Merged rows cannot be told apart afterwards, so there is nothing to undo.
    pass
