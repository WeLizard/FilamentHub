"""Add multi-brand organizations and scoped memberships.

Revision ID: organization_brand_ownership
Revises: preset_compat_context
Create Date: 2026-07-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "organization_brand_ownership"
down_revision: Union[str, None] = "preset_compat_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

organization_role = postgresql.ENUM(
    "owner",
    "editor",
    name="organizationmemberrole",
    create_type=False,
)


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'moderator'")
    organization_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.add_column("brands", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.add_column(
        "brands",
        sa.Column(
            "name_correction_available",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "brands",
        sa.Column("name_corrected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_brands_organization_id",
        "brands",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_brands_organization_id"), "brands", ["organization_id"], unique=False
    )

    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            organization_role,
            server_default=sa.text("'editor'::organizationmemberrole"),
            nullable=False,
        ),
        sa.Column("all_brands", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("invited_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_membership_user"
        ),
    )
    op.create_index(
        op.f("ix_organization_memberships_organization_id"),
        "organization_memberships",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_memberships_user_id"),
        "organization_memberships",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "organization_brand_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["organization_memberships.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("membership_id", "brand_id", name="uq_membership_brand_access"),
    )
    op.create_index(
        op.f("ix_organization_brand_access_membership_id"),
        "organization_brand_access",
        ["membership_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_brand_access_brand_id"),
        "organization_brand_access",
        ["brand_id"],
        unique=False,
    )

    op.add_column("brand_invites", sa.Column("brand_id", sa.Integer(), nullable=True))
    op.add_column("brand_invites", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.add_column(
        "brand_invites",
        sa.Column("target_type", sa.String(length=16), server_default="new", nullable=False),
    )
    op.add_column("brand_invites", sa.Column("proposed_slug", sa.String(length=100), nullable=True))
    op.add_column(
        "brand_invites",
        sa.Column("member_role", sa.String(length=16), server_default="owner", nullable=False),
    )
    op.add_column(
        "brand_invites",
        sa.Column(
            "sender_profile", sa.String(length=32), server_default="partnerships", nullable=False
        ),
    )
    op.add_column("brand_invites", sa.Column("batch_id", sa.String(length=36), nullable=True))
    op.add_column(
        "brand_invites",
        sa.Column("send_status", sa.String(length=16), server_default="pending", nullable=False),
    )
    op.add_column("brand_invites", sa.Column("send_error", sa.String(length=500), nullable=True))
    op.add_column(
        "brand_invites", sa.Column("provider_message_id", sa.String(length=100), nullable=True)
    )
    op.add_column("brand_invites", sa.Column("reply_token", sa.String(length=64), nullable=True))
    op.add_column("brand_invites", sa.Column("sent_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_brand_invites_brand_id",
        "brand_invites",
        "brands",
        ["brand_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_brand_invites_organization_id",
        "brand_invites",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_brand_invites_brand_id"), "brand_invites", ["brand_id"], unique=False
    )
    op.create_index(
        op.f("ix_brand_invites_organization_id"),
        "brand_invites",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_brand_invites_batch_id"), "brand_invites", ["batch_id"], unique=False
    )
    op.create_index(
        op.f("ix_brand_invites_reply_token"),
        "brand_invites",
        ["reply_token"],
        unique=True,
    )

    # Preserve current representatives. Every legacy brand relationship becomes
    # an organization; the first user is owner and additional users are editors.
    op.execute(
        """
        INSERT INTO organizations (name, slug, created_by_id, active, created_at, updated_at)
        SELECT b.name, b.slug, MIN(u.id), true, now(), now()
        FROM brands b
        JOIN users u ON u.brand_id = b.id
        GROUP BY b.id, b.name, b.slug
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE brands b
        SET organization_id = o.id
        FROM organizations o
        WHERE o.slug = b.slug
          AND EXISTS (SELECT 1 FROM users u WHERE u.brand_id = b.id)
        """
    )
    op.execute(
        """
        INSERT INTO organization_memberships
            (organization_id, user_id, role, all_brands, active, joined_at)
        SELECT
            b.organization_id,
            u.id,
            CASE
                WHEN u.id = MIN(u.id) OVER (PARTITION BY u.brand_id)
                THEN 'owner'::organizationmemberrole
                ELSE 'editor'::organizationmemberrole
            END,
            CASE
                WHEN u.id = MIN(u.id) OVER (PARTITION BY u.brand_id)
                THEN true
                ELSE false
            END,
            true,
            now()
        FROM users u
        JOIN brands b ON b.id = u.brand_id
        WHERE b.organization_id IS NOT NULL
        ON CONFLICT (organization_id, user_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO organization_brand_access (membership_id, brand_id)
        SELECT om.id, b.id
        FROM organization_memberships om
        JOIN brands b ON b.organization_id = om.organization_id
        WHERE om.all_brands = false
        ON CONFLICT (membership_id, brand_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_brand_invites_reply_token"), table_name="brand_invites")
    op.drop_index(op.f("ix_brand_invites_batch_id"), table_name="brand_invites")
    op.drop_index(op.f("ix_brand_invites_organization_id"), table_name="brand_invites")
    op.drop_index(op.f("ix_brand_invites_brand_id"), table_name="brand_invites")
    op.drop_constraint("fk_brand_invites_organization_id", "brand_invites", type_="foreignkey")
    op.drop_constraint("fk_brand_invites_brand_id", "brand_invites", type_="foreignkey")
    op.drop_column("brand_invites", "sent_at")
    op.drop_column("brand_invites", "reply_token")
    op.drop_column("brand_invites", "provider_message_id")
    op.drop_column("brand_invites", "send_error")
    op.drop_column("brand_invites", "send_status")
    op.drop_column("brand_invites", "batch_id")
    op.drop_column("brand_invites", "sender_profile")
    op.drop_column("brand_invites", "member_role")
    op.drop_column("brand_invites", "proposed_slug")
    op.drop_column("brand_invites", "target_type")
    op.drop_column("brand_invites", "organization_id")
    op.drop_column("brand_invites", "brand_id")

    op.drop_table("organization_brand_access")
    op.drop_table("organization_memberships")
    op.drop_index(op.f("ix_brands_organization_id"), table_name="brands")
    op.drop_constraint("fk_brands_organization_id", "brands", type_="foreignkey")
    op.drop_column("brands", "name_corrected_at")
    op.drop_column("brands", "name_correction_available")
    op.drop_column("brands", "organization_id")
    op.drop_table("organizations")
    organization_role.drop(op.get_bind(), checkfirst=True)

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM users WHERE role = 'moderator') THEN
                RAISE EXCEPTION
                    'Cannot downgrade while moderator users exist; reassign them explicitly first';
            END IF;
        END
        $$
        """
    )
    op.execute("ALTER TYPE userrole RENAME TO userrole_old")
    op.execute("CREATE TYPE userrole AS ENUM ('user', 'brand', 'admin')")
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::text::userrole"
    )
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'user'")
    op.execute("DROP TYPE userrole_old")
