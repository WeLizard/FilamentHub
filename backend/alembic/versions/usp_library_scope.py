"""library scope for user saved presets

Adds the filament-library scope (RFC material-systems §3.3, PROFILE-LIBRARY-1):
a saved preset is either unscoped (universal — today's behavior) or targeted
to one of the user's own Orca machine profiles (PrinterProfile.id). The
"compatible" set is computed at apply time and never stored.

Revision ID: usp_library_scope
Revises: usp_user_preset_unique_restore
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "usp_library_scope"
down_revision: str | None = "usp_user_preset_unique_restore"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_saved_presets",
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="unscoped"),
    )
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


def downgrade() -> None:
    op.drop_index(
        "ix_user_saved_presets_target_profile", table_name="user_saved_presets"
    )
    op.drop_constraint(
        "fk_user_saved_presets_target_profile", "user_saved_presets", type_="foreignkey"
    )
    op.drop_column("user_saved_presets", "target_printer_profile_id")
    op.drop_column("user_saved_presets", "scope")
