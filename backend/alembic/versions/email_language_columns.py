"""Store the language of outgoing email per invitation and per CRM thread.

Revision ID: email_language_columns
Revises: octoprint_bridge_adapter
Create Date: 2026-08-01
"""

import sqlalchemy as sa

from alembic import op

revision = "email_language_columns"
down_revision = "octoprint_bridge_adapter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rows created before this column were all sent in Russian, so they keep "ru";
    # everything created afterwards carries the language chosen in the admin panel.
    op.add_column(
        "brand_invites",
        sa.Column("language", sa.String(length=2), nullable=False, server_default="ru"),
    )
    op.add_column(
        "email_threads",
        sa.Column("language", sa.String(length=2), nullable=False, server_default="ru"),
    )


def downgrade() -> None:
    op.drop_column("email_threads", "language")
    op.drop_column("brand_invites", "language")
