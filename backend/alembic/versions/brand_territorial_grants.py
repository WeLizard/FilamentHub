"""Territorial grants: several organisations inside one brand.

Revision ID: brand_grants
Revises: country_cells
Create Date: 2026-08-08

Creality exists once; Creality Russia and Creality Germany join it, each with
their own country. Brand.organization_id describes a single workspace behind a
brand and cannot express that, and OrganizationBrandAccess answers a different
question — a colleague's access inside one organisation.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "brand_grants"
down_revision: Union[str, None] = "country_cells"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "pending", "active", "revoked", name="grant_status", create_type=False
    )
    source = postgresql.ENUM(
        "invitation", "application", name="grant_source", create_type=False
    )
    sa.Enum("pending", "active", "revoked", name="grant_status").create(
        op.get_bind(), checkfirst=True
    )
    sa.Enum("invitation", "application", name="grant_source").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "brand_territorial_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        # NULL — глобальная область; она не появляется сама и выдаётся решением.
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("status", status, nullable=False, server_default="pending"),
        sa.Column("source", source, nullable=False),
        sa.Column("manage_brand_country", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("manage_filament_country", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("create_filaments", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("edit_own_created_filaments", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("edit_brand_common", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("edit_all_filaments_common", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grants_brand", "brand_territorial_grants", ["brand_id"])
    op.create_index("ix_grants_org", "brand_territorial_grants", ["organization_id"])
    op.create_index("ix_grants_country", "brand_territorial_grants", ["country"])
    # Одной организации незачем два права на один бренд и одну страну; несколько
    # независимых организаций на страну не запрещены — это решение владельца.
    op.create_index(
        "uq_grant_org_brand_country",
        "brand_territorial_grants",
        ["brand_id", "organization_id", "country"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("brand_territorial_grants")
    sa.Enum(name="grant_source").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="grant_status").drop(op.get_bind(), checkfirst=True)
