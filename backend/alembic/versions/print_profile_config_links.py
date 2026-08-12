"""Link process profiles to exact machine configurations.

Revision ID: print_profile_config_links
Revises: orca_slice_profile_ids
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "print_profile_config_links"
down_revision: str | None = "orca_slice_profile_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _backfill_exact_links() -> None:
    """Backfill only unique owner-scoped name/slug matches.

    The legacy compatibility array remains untouched and continues to cover
    catalog-model compatibility. Ambiguous machine names are deliberately left
    without an exact link for the owner to resolve in the UI.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                INSERT INTO print_profile_configuration_links
                    (print_profile_id, printer_profile_id)
                SELECT DISTINCT matches.print_profile_id, matches.printer_profile_id
                FROM (
                    SELECT
                        process.id AS print_profile_id,
                        MIN(configuration.id) AS printer_profile_id
                    FROM print_profiles AS process
                    CROSS JOIN LATERAL jsonb_array_elements_text(
                        CASE
                            WHEN jsonb_typeof(process.compatible_printers::jsonb) = 'array'
                            THEN process.compatible_printers::jsonb
                            ELSE '[]'::jsonb
                        END
                    ) AS identifier(value)
                    JOIN printer_profiles AS configuration
                      ON configuration.active IS TRUE
                     AND (
                         configuration.owner_user_id = process.owner_user_id
                         OR (
                             configuration.owner_user_id IS NULL
                             AND configuration.is_official IS TRUE
                         )
                     )
                     AND (
                         configuration.name = identifier.value
                         OR configuration.slug = identifier.value
                     )
                    WHERE BTRIM(identifier.value) <> ''
                    GROUP BY process.id, identifier.value
                    HAVING COUNT(DISTINCT configuration.id) = 1
                ) AS matches
                ON CONFLICT (print_profile_id, printer_profile_id) DO NOTHING
                """
            )
        )
    elif bind.dialect.name == "sqlite":
        op.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO print_profile_configuration_links
                    (print_profile_id, printer_profile_id)
                SELECT DISTINCT matches.print_profile_id, matches.printer_profile_id
                FROM (
                    SELECT
                        process.id AS print_profile_id,
                        MIN(configuration.id) AS printer_profile_id
                    FROM print_profiles AS process
                    JOIN json_each(
                        CASE
                            WHEN json_type(process.compatible_printers) = 'array'
                            THEN process.compatible_printers
                            ELSE '[]'
                        END
                    ) AS identifier
                    JOIN printer_profiles AS configuration
                      ON configuration.active = 1
                     AND (
                         configuration.owner_user_id = process.owner_user_id
                         OR (
                             configuration.owner_user_id IS NULL
                             AND configuration.is_official = 1
                         )
                     )
                     AND (
                         configuration.name = identifier.value
                         OR configuration.slug = identifier.value
                     )
                    WHERE TRIM(identifier.value) <> ''
                    GROUP BY process.id, identifier.value
                    HAVING COUNT(DISTINCT configuration.id) = 1
                ) AS matches
                """
            )
        )


def upgrade() -> None:
    op.add_column(
        "print_profiles",
        sa.Column(
            "configuration_links_resolved",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_table(
        "print_profile_configuration_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("print_profile_id", sa.Integer(), nullable=False),
        sa.Column("printer_profile_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["print_profile_id"],
            ["print_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["printer_profile_id"],
            ["printer_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "print_profile_id",
            "printer_profile_id",
            name="uq_print_profile_config_link",
        ),
    )
    op.create_index(
        "ix_pp_config_print_profile",
        "print_profile_configuration_links",
        ["print_profile_id"],
    )
    op.create_index(
        "ix_pp_config_printer_profile",
        "print_profile_configuration_links",
        ["printer_profile_id"],
    )
    _backfill_exact_links()
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE print_profiles AS process
                SET configuration_links_resolved = TRUE
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(
                        CASE
                            WHEN jsonb_typeof(process.compatible_printers::jsonb) = 'array'
                            THEN process.compatible_printers::jsonb
                            ELSE '[]'::jsonb
                        END
                    ) AS identifier(value)
                    LEFT JOIN printer_profiles AS configuration
                      ON configuration.active IS TRUE
                     AND (
                         configuration.owner_user_id = process.owner_user_id
                         OR (
                             configuration.owner_user_id IS NULL
                             AND configuration.is_official IS TRUE
                         )
                     )
                     AND (
                         configuration.name = identifier.value
                         OR configuration.slug = identifier.value
                     )
                    WHERE BTRIM(identifier.value) <> ''
                    GROUP BY identifier.value
                    HAVING COUNT(DISTINCT configuration.id) <> 1
                )
                """
            )
        )
    elif bind.dialect.name == "sqlite":
        op.execute(
            sa.text(
                """
                UPDATE print_profiles AS process
                SET configuration_links_resolved = 1
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM json_each(
                        CASE
                            WHEN json_type(process.compatible_printers) = 'array'
                            THEN process.compatible_printers
                            ELSE '[]'
                        END
                    ) AS identifier
                    LEFT JOIN printer_profiles AS configuration
                      ON configuration.active = 1
                     AND (
                         configuration.owner_user_id = process.owner_user_id
                         OR (
                             configuration.owner_user_id IS NULL
                             AND configuration.is_official = 1
                         )
                     )
                     AND (
                         configuration.name = identifier.value
                         OR configuration.slug = identifier.value
                     )
                    WHERE TRIM(identifier.value) <> ''
                    GROUP BY identifier.value
                    HAVING COUNT(DISTINCT configuration.id) <> 1
                )
                """
            )
        )


def downgrade() -> None:
    op.drop_index(
        "ix_pp_config_printer_profile",
        table_name="print_profile_configuration_links",
    )
    op.drop_index(
        "ix_pp_config_print_profile",
        table_name="print_profile_configuration_links",
    )
    op.drop_table("print_profile_configuration_links")
    op.drop_column("print_profiles", "configuration_links_resolved")
