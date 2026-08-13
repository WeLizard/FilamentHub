"""add durable local Orca profile identity and snapshot scopes

Revision ID: orca_profile_identity
Revises: brand_request_site_check
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "orca_profile_identity"
down_revision: str | None = "brand_request_site_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orca_profile_sync_scopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("source_instance_id", sa.String(length=100), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("current_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('machine', 'process')", name="ck_orca_sync_scope_kind"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orca_profile_sync_scopes_owner_user_id",
        "orca_profile_sync_scopes",
        ["owner_user_id"],
    )
    op.create_index(
        "uq_orca_sync_scope_owner_source_account_kind",
        "orca_profile_sync_scopes",
        ["owner_user_id", "source_instance_id", "account_id", "kind"],
        unique=True,
    )

    op.create_table(
        "orca_profile_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("source_instance_id", sa.String(length=100), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("local_profile_id", sa.String(length=36), nullable=False),
        sa.Column("printer_profile_id", sa.Integer(), nullable=True),
        sa.Column("print_profile_id", sa.Integer(), nullable=True),
        sa.Column("present", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("last_name", sa.String(length=200), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('machine', 'process')",
            name="ck_orca_profile_binding_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'machine' AND printer_profile_id IS NOT NULL AND print_profile_id IS NULL) "
            "OR (kind = 'process' AND print_profile_id IS NOT NULL AND printer_profile_id IS NULL)",
            name="ck_orca_profile_binding_target",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["printer_profile_id"], ["printer_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["print_profile_id"], ["print_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orca_profile_bindings_owner_user_id",
        "orca_profile_bindings",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_orca_profile_bindings_printer_profile_id",
        "orca_profile_bindings",
        ["printer_profile_id"],
    )
    op.create_index(
        "ix_orca_profile_bindings_print_profile_id",
        "orca_profile_bindings",
        ["print_profile_id"],
    )
    op.create_index(
        "uq_orca_binding_owner_source_account_kind_local",
        "orca_profile_bindings",
        ["owner_user_id", "source_instance_id", "account_id", "kind", "local_profile_id"],
        unique=True,
    )
    op.create_index(
        "ix_orca_binding_scope_present",
        "orca_profile_bindings",
        ["owner_user_id", "source_instance_id", "account_id", "kind", "present"],
    )


def downgrade() -> None:
    op.drop_index("ix_orca_binding_scope_present", table_name="orca_profile_bindings")
    op.drop_index(
        "uq_orca_binding_owner_source_account_kind_local",
        table_name="orca_profile_bindings",
    )
    op.drop_index(
        "ix_orca_profile_bindings_print_profile_id",
        table_name="orca_profile_bindings",
    )
    op.drop_index(
        "ix_orca_profile_bindings_printer_profile_id",
        table_name="orca_profile_bindings",
    )
    op.drop_index(
        "ix_orca_profile_bindings_owner_user_id",
        table_name="orca_profile_bindings",
    )
    op.drop_table("orca_profile_bindings")
    op.drop_index(
        "uq_orca_sync_scope_owner_source_account_kind",
        table_name="orca_profile_sync_scopes",
    )
    op.drop_index(
        "ix_orca_profile_sync_scopes_owner_user_id",
        table_name="orca_profile_sync_scopes",
    )
    op.drop_table("orca_profile_sync_scopes")
