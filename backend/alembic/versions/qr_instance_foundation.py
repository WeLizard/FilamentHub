"""Add QR instance bindings and compact manufacturer batches.

Revision ID: qr_instance_foundation
Revises: weighted_preset_unique
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "qr_instance_foundation"
down_revision = "weighted_preset_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qr_user_spool_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_spool_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filament_id", sa.Integer(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("last_rotation_key_digest", sa.String(length=64), nullable=True),
        sa.Column("retirement_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "state IN ('active', 'pending_retirement')",
            name="ck_qr_user_binding_state",
        ),
        sa.ForeignKeyConstraint(["filament_id"], ["filaments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_spool_id"], ["user_spools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_spool_id", name="uq_qr_user_binding_spool"),
        sa.UniqueConstraint("token_digest", name="uq_qr_user_binding_token"),
    )
    op.create_index(
        "ix_qr_user_binding_filament",
        "qr_user_spool_bindings",
        ["filament_id"],
    )
    op.create_index("ix_qr_user_binding_purge", "qr_user_spool_bindings", ["purge_after"])
    op.create_index("ix_qr_user_binding_user", "qr_user_spool_bindings", ["user_id"])

    op.create_table(
        "qr_manufacturer_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total_quantity", sa.Integer(), nullable=False),
        sa.Column("manifest_revision", sa.Integer(), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("idempotency_key_digest", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
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
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('sku', 'serialized')", name="ck_qr_batch_mode"),
        sa.CheckConstraint("status IN ('active', 'cancelled')", name="ck_qr_batch_status"),
        sa.CheckConstraint("total_quantity > 0", name="ck_qr_batch_quantity"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key_digest",
            name="uq_qr_batch_org_idempotency",
        ),
        sa.UniqueConstraint("public_id", name="uq_qr_batch_public_id"),
    )
    op.create_index(
        "ix_qr_batch_brand_created",
        "qr_manufacturer_batches",
        ["brand_id", "created_at"],
    )
    op.create_index(
        "ix_qr_batch_org_created",
        "qr_manufacturer_batches",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "qr_manufacturer_batch_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("filament_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("ordinal_start", sa.Integer(), nullable=False),
        sa.Column("product_qr_code", sa.String(length=50), nullable=False),
        sa.CheckConstraint("ordinal_start >= 0", name="ck_qr_batch_item_ordinal"),
        sa.CheckConstraint("quantity > 0", name="ck_qr_batch_item_quantity"),
        sa.ForeignKeyConstraint(["batch_id"], ["qr_manufacturer_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["filament_id"], ["filaments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "filament_id", name="uq_qr_batch_item_filament"),
        sa.UniqueConstraint("batch_id", "ordinal_start", name="uq_qr_batch_item_ordinal"),
    )
    op.create_index("ix_qr_batch_item_batch", "qr_manufacturer_batch_items", ["batch_id"])

    op.create_table(
        "qr_manufacturer_instance_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("filament_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_spool_id", sa.Integer(), nullable=True),
        sa.Column("last_operation_key_digest", sa.String(length=64), nullable=True),
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
        sa.CheckConstraint("ordinal >= 0", name="ck_qr_instance_ordinal"),
        sa.CheckConstraint(
            "status IN ('claimed', 'revoked', 'scrapped')",
            name="ck_qr_instance_state",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["qr_manufacturer_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["filament_id"], ["filaments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_spool_id"], ["user_spools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "ordinal", name="uq_qr_instance_batch_ordinal"),
    )
    op.create_index(
        "ix_qr_instance_filament",
        "qr_manufacturer_instance_states",
        ["filament_id"],
    )
    op.create_index(
        "ix_qr_instance_spool",
        "qr_manufacturer_instance_states",
        ["user_spool_id"],
    )
    op.create_index("ix_qr_instance_user", "qr_manufacturer_instance_states", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_qr_instance_user", table_name="qr_manufacturer_instance_states")
    op.drop_index("ix_qr_instance_spool", table_name="qr_manufacturer_instance_states")
    op.drop_index("ix_qr_instance_filament", table_name="qr_manufacturer_instance_states")
    op.drop_table("qr_manufacturer_instance_states")
    op.drop_index("ix_qr_batch_item_batch", table_name="qr_manufacturer_batch_items")
    op.drop_table("qr_manufacturer_batch_items")
    op.drop_index("ix_qr_batch_org_created", table_name="qr_manufacturer_batches")
    op.drop_index("ix_qr_batch_brand_created", table_name="qr_manufacturer_batches")
    op.drop_table("qr_manufacturer_batches")
    op.drop_index("ix_qr_user_binding_user", table_name="qr_user_spool_bindings")
    op.drop_index("ix_qr_user_binding_purge", table_name="qr_user_spool_bindings")
    op.drop_index("ix_qr_user_binding_filament", table_name="qr_user_spool_bindings")
    op.drop_table("qr_user_spool_bindings")
