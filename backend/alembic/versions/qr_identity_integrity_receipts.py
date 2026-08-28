"""Preserve claimed QR tombstones and add durable operation receipts.

Revision ID: qr_identity_integrity_receipts
Revises: qr_batch_token_ref
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "qr_identity_integrity_receipts"
down_revision = "qr_batch_token_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_qr_instance_binding_shape",
        "qr_manufacturer_instance_states",
        type_="check",
    )
    op.create_check_constraint(
        "ck_qr_instance_binding_shape",
        "qr_manufacturer_instance_states",
        "status = 'claimed' OR (status IN ('revoked', 'scrapped') "
        "AND user_id IS NULL AND user_spool_id IS NULL)",
    )
    op.drop_constraint(
        "qr_manufacturer_instance_states_user_id_fkey",
        "qr_manufacturer_instance_states",
        type_="foreignkey",
    )
    op.drop_constraint(
        "qr_manufacturer_instance_states_user_spool_id_fkey",
        "qr_manufacturer_instance_states",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "qr_manufacturer_instance_states_user_id_fkey",
        "qr_manufacturer_instance_states",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "qr_manufacturer_instance_states_user_spool_id_fkey",
        "qr_manufacturer_instance_states",
        "user_spools",
        ["user_spool_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "qr_operation_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=128), nullable=False),
        sa.Column("key_digest", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("response_snapshot_ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope",
            "subject",
            "key_digest",
            name="uq_qr_operation_receipt_key",
        ),
    )
    op.create_index(
        "ix_qr_operation_receipt_subject_created",
        "qr_operation_receipts",
        ["scope", "subject", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_qr_operation_receipt_subject_created",
        table_name="qr_operation_receipts",
    )
    op.drop_table("qr_operation_receipts")

    op.drop_constraint(
        "qr_manufacturer_instance_states_user_spool_id_fkey",
        "qr_manufacturer_instance_states",
        type_="foreignkey",
    )
    op.drop_constraint(
        "qr_manufacturer_instance_states_user_id_fkey",
        "qr_manufacturer_instance_states",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "qr_manufacturer_instance_states_user_id_fkey",
        "qr_manufacturer_instance_states",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "qr_manufacturer_instance_states_user_spool_id_fkey",
        "qr_manufacturer_instance_states",
        "user_spools",
        ["user_spool_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "ck_qr_instance_binding_shape",
        "qr_manufacturer_instance_states",
        type_="check",
    )
    op.execute(
        "DELETE FROM qr_manufacturer_instance_states "
        "WHERE status = 'claimed' AND (user_id IS NULL OR user_spool_id IS NULL)"
    )
    op.create_check_constraint(
        "ck_qr_instance_binding_shape",
        "qr_manufacturer_instance_states",
        "(status = 'claimed' AND user_id IS NOT NULL AND user_spool_id IS NOT NULL) "
        "OR (status IN ('revoked', 'scrapped') AND user_id IS NULL "
        "AND user_spool_id IS NULL)",
    )
