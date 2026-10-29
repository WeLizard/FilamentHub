"""Personal spool folders (many-to-many).

Revision ID: spool_collections
Revises: workstation_keys
"""

import sqlalchemy as sa

from alembic import op

revision = "spool_collections"
down_revision = "workstation_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spool_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_key", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "name_key", name="uq_spool_collection_name"),
    )
    op.create_index("ix_spool_collections_user_id", "spool_collections", ["user_id"])
    op.create_table(
        "spool_collection_members",
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("spool_collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "spool_id",
            sa.Integer(),
            sa.ForeignKey("user_spools.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_spool_collection_members_spool_id", "spool_collection_members", ["spool_id"])


def downgrade() -> None:
    op.drop_index("ix_spool_collection_members_spool_id", table_name="spool_collection_members")
    op.drop_table("spool_collection_members")
    op.drop_index("ix_spool_collections_user_id", table_name="spool_collections")
    op.drop_table("spool_collections")
