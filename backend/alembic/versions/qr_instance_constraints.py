"""Enforce one well-formed manufacturer QR identity per spool.

Revision ID: qr_instance_constraints
Revises: qr_instance_foundation
"""

from __future__ import annotations

from alembic import op

revision = "qr_instance_constraints"
down_revision = "qr_instance_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_qr_instance_binding_shape",
        "qr_manufacturer_instance_states",
        "(status = 'claimed' AND user_id IS NOT NULL AND user_spool_id IS NOT NULL) "
        "OR (status IN ('revoked', 'scrapped') AND user_id IS NULL "
        "AND user_spool_id IS NULL)",
    )
    op.create_unique_constraint(
        "uq_qr_instance_user_spool",
        "qr_manufacturer_instance_states",
        ["user_spool_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_qr_instance_user_spool",
        "qr_manufacturer_instance_states",
        type_="unique",
    )
    op.drop_constraint(
        "ck_qr_instance_binding_shape",
        "qr_manufacturer_instance_states",
        type_="check",
    )
