"""Add stable revisions for material-slot desired assignments.

Revision ID: material_slot_assignment_rev
Revises: refresh_token_sessions
"""

import sqlalchemy as sa

from alembic import op

revision = "material_slot_assignment_rev"
down_revision = "refresh_token_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "material_slots",
        sa.Column(
            "assignment_revision",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("material_slots", "assignment_revision")
