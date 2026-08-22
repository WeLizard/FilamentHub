"""Add revisioned shared routing configuration to OctoPrint Bridge.

Revision ID: octoprint_bridge_routing
Revises: unify_user_achievements
"""

import sqlalchemy as sa

from alembic import op

revision = "octoprint_bridge_routing"
down_revision = "unify_user_achievements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("octoprint_bridge_connections") as batch_op:
        batch_op.add_column(
            sa.Column(
                "desired_routing_mode",
                sa.String(length=20),
                server_default="manual",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "desired_tool_slot_map",
                sa.JSON(),
                server_default="[]",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "routing_revision",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("applied_routing_revision", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("octoprint_bridge_connections") as batch_op:
        batch_op.drop_column("applied_routing_revision")
        batch_op.drop_column("routing_revision")
        batch_op.drop_column("desired_tool_slot_map")
        batch_op.drop_column("desired_routing_mode")
