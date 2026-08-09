"""Add sanitized Wiki media assets.

Revision ID: wiki_media_assets
Revises: filament_public_slugs
Create Date: 2026-08-09
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "wiki_media_assets"
down_revision: Union[str, None] = "filament_public_slugs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wiki_media_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("published", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_wiki_media_public_id"),
        sa.UniqueConstraint("storage_path", name="uq_wiki_media_storage_path"),
    )
    op.create_index(
        "ix_wiki_media_uploader", "wiki_media_assets", ["uploaded_by_id"]
    )
    op.create_index(
        "ix_wiki_media_published", "wiki_media_assets", ["published"]
    )


def downgrade() -> None:
    op.drop_index("ix_wiki_media_published", table_name="wiki_media_assets")
    op.drop_index("ix_wiki_media_uploader", table_name="wiki_media_assets")
    op.drop_table("wiki_media_assets")
