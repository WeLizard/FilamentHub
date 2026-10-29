"""Filament packagings: every weight and carrier a manufacturer sells.

Revision ID: filament_packagings
Revises: feature_code_synonyms

Additive JSON list; the single spool columns stay the main packaging.
"""

import sqlalchemy as sa

from alembic import op

revision = "filament_packagings"
down_revision = "feature_code_synonyms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "filaments",
        sa.Column("packagings", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("filaments", "packagings")
