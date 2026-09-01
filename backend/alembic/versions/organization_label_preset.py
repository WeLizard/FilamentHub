"""Add organization-owned label-layout presets.

Revision ID: organization_label_preset
Revises: personal_label_preset
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "organization_label_preset"
down_revision = "personal_label_preset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_label_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id",
            "brand_id",
            "name",
            name="uq_org_brand_label_preset_name",
        ),
    )
    op.create_index(
        "ix_organization_label_presets_brand_id",
        "organization_label_presets",
        ["brand_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_label_presets_brand_id",
        table_name="organization_label_presets",
    )
    op.drop_table("organization_label_presets")
