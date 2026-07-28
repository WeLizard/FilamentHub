"""Release the author reference instead of blocking account deletion.

Revision ID: author_optional_delete
Revises: device_hostname_unique
Create Date: 2026-07-28
"""

import sqlalchemy as sa

from alembic import op

revision = "author_optional_delete"
down_revision = "device_hostname_unique"
branch_labels = None
depends_on = None

_SHARED_AUTHORS = (
    ("filament_reviews", "user_id", True),
    ("brand_requests", "user_id", True),
    ("brand_requests", "processed_by_id", False),
    ("printer_requests", "user_id", True),
    ("printer_requests", "processed_by_id", False),
    ("notification_campaigns", "created_by_id", True),
    ("bundles", "uploaded_by_user_id", True),
    ("bundle_imports", "started_by_user_id", True),
    ("wiki_articles", "created_by_id", False),
    ("wiki_articles", "updated_by_id", False),
    ("wiki_articles", "reviewed_by_id", False),
    ("material_properties", "created_by_id", False),
    ("material_properties", "updated_by_id", False),
    ("material_properties", "verified_by_id", False),
    ("print_problems", "created_by_id", False),
    ("print_problems", "updated_by_id", False),
    ("print_problems", "verified_by_id", False),
    ("brand_invites", "invited_by_id", False),
    ("brand_invites", "accepted_by_id", False),
    ("feedback", "responded_by", False),
    ("presets", "user_id", False),
)


def _constraint(table: str, column: str) -> str:
    return f"{table}_{column}_fkey"


def upgrade() -> None:
    for table, column, was_required in _SHARED_AUTHORS:
        if was_required:
            op.alter_column(table, column, existing_type=sa.Integer(), nullable=True)
        constraint = _constraint(table, column)
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint, table, "users", [column], ["id"], ondelete="SET NULL"
        )

    op.execute(
        sa.text(
            "UPDATE bundle_imports SET started_by_user_id = NULL "
            "WHERE started_by_user_id = 0"
        )
    )


def downgrade() -> None:
    for table, column, _ in _SHARED_AUTHORS:
        constraint = _constraint(table, column)
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, "users", [column], ["id"])
