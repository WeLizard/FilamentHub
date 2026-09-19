"""Attach an encrypted OrcaSlicer plugin log to feedback.

Revision ID: feedback_plugin_log
Revises: deleted_preset_queue
"""

import sqlalchemy as sa

from alembic import op

revision = "feedback_plugin_log"
down_revision = "deleted_preset_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("plugin_log", sa.Text(), nullable=True))
    op.add_column("feedback", sa.Column("plugin_log_size", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_feedback_plugin_log_size",
        "feedback",
        "plugin_log_size IS NULL OR (plugin_log_size > 0 AND plugin_log_size <= 65536)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_feedback_plugin_log_size", "feedback", type_="check")
    op.drop_column("feedback", "plugin_log_size")
    op.drop_column("feedback", "plugin_log")
