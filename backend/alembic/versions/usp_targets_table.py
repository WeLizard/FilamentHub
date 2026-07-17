"""target set table for saved preset library scope

Replaces the single user_saved_presets.target_printer_profile_id with a
target set (RFC material-systems §3.3: «Добавить в Orca» selects one or
several machine profiles). Scope values: unscoped (no targets), targeted
(one), compatible (a set). Existing targeted rows are backfilled into the
new table before the column is dropped.

Revision ID: usp_targets_table
Revises: usp_library_scope
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "usp_targets_table"
down_revision: str | None = "usp_library_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_saved_preset_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_saved_preset_id",
            sa.Integer(),
            sa.ForeignKey("user_saved_presets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "printer_profile_id",
            sa.Integer(),
            sa.ForeignKey("printer_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_usp_targets_saved_profile_unique",
        "user_saved_preset_targets",
        ["user_saved_preset_id", "printer_profile_id"],
        unique=True,
    )
    op.create_index(
        "ix_usp_targets_printer_profile",
        "user_saved_preset_targets",
        ["printer_profile_id"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO user_saved_preset_targets (user_saved_preset_id, printer_profile_id)
            SELECT id, target_printer_profile_id
            FROM user_saved_presets
            WHERE target_printer_profile_id IS NOT NULL
            """
        )
    )

    op.drop_index("ix_user_saved_presets_target_profile", table_name="user_saved_presets")
    op.drop_constraint(
        "fk_user_saved_presets_target_profile", "user_saved_presets", type_="foreignkey"
    )
    op.drop_column("user_saved_presets", "target_printer_profile_id")


def downgrade() -> None:
    op.add_column(
        "user_saved_presets",
        sa.Column("target_printer_profile_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_saved_presets_target_profile",
        "user_saved_presets",
        "printer_profiles",
        ["target_printer_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_user_saved_presets_target_profile",
        "user_saved_presets",
        ["target_printer_profile_id"],
    )
    # A multi-target set cannot round-trip into a single column: keep the
    # lowest-id target per saved preset, matching the pre-upgrade shape for
    # rows that had exactly one.
    op.execute(
        sa.text(
            """
            UPDATE user_saved_presets
            SET target_printer_profile_id = (
                SELECT t.printer_profile_id
                FROM user_saved_preset_targets t
                WHERE t.user_saved_preset_id = user_saved_presets.id
                ORDER BY t.id
                LIMIT 1
            )
            """
        )
    )
    op.drop_index("ix_usp_targets_printer_profile", table_name="user_saved_preset_targets")
    op.drop_index(
        "ix_usp_targets_saved_profile_unique", table_name="user_saved_preset_targets"
    )
    op.drop_table("user_saved_preset_targets")
