"""Add the filament duplicate review queue and filament authorship.

Revision ID: filament_duplicate_reviews
Revises: catalog_image_confirms
"""

import sqlalchemy as sa

from alembic import op

revision = "filament_duplicate_reviews"
down_revision = "catalog_image_confirms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "filaments",
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_filaments_created_by_user"),
            nullable=True,
        ),
    )
    op.create_index("ix_filaments_created_by_user_id", "filaments", ["created_by_user_id"])

    op.create_table(
        "filament_duplicate_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "filament_id",
            sa.Integer(),
            sa.ForeignKey("filaments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.Integer(),
            sa.ForeignKey("filaments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "resolved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("filament_id", "candidate_id", name="uq_filament_dup_review_pair"),
    )
    op.create_index("ix_filament_dup_review_status", "filament_duplicate_reviews", ["status"])
    op.create_index(
        "ix_filament_dup_review_candidate", "filament_duplicate_reviews", ["candidate_id"]
    )


def downgrade() -> None:
    op.drop_table("filament_duplicate_reviews")
    op.drop_index("ix_filaments_created_by_user_id", table_name="filaments")
    op.drop_column("filaments", "created_by_user_id")
