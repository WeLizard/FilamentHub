"""Separate feedback activity from workflow status.

Revision ID: feedback_admin_unread_counter
Revises: organization_label_preset
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "feedback_admin_unread_counter"
down_revision = "organization_label_preset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback",
        sa.Column(
            "admin_unread_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("feedback", "admin_unread_count")
