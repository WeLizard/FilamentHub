"""Add an opaque compact lookup reference to manufacturer QR batches.

Revision ID: qr_batch_token_ref
Revises: qr_instance_constraints
"""

from __future__ import annotations

import secrets

import sqlalchemy as sa

from alembic import op

revision = "qr_batch_token_ref"
down_revision = "qr_instance_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qr_manufacturer_batches",
        sa.Column("token_ref", sa.String(length=14), nullable=True),
    )
    connection = op.get_bind()
    batch_ids = list(
        connection.execute(sa.text("SELECT id FROM qr_manufacturer_batches ORDER BY id")).scalars()
    )
    allocated: set[str] = set()
    for batch_id in batch_ids:
        while True:
            token_ref = secrets.token_urlsafe(10)
            if token_ref not in allocated:
                allocated.add(token_ref)
                break
        connection.execute(
            sa.text(
                "UPDATE qr_manufacturer_batches SET token_ref = :token_ref WHERE id = :batch_id"
            ),
            {"token_ref": token_ref, "batch_id": batch_id},
        )
    op.alter_column("qr_manufacturer_batches", "token_ref", nullable=False)
    op.create_unique_constraint(
        "uq_qr_batch_token_ref",
        "qr_manufacturer_batches",
        ["token_ref"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_qr_batch_token_ref",
        "qr_manufacturer_batches",
        type_="unique",
    )
    op.drop_column("qr_manufacturer_batches", "token_ref")
