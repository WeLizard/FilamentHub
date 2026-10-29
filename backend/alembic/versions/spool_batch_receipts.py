"""Add idempotency receipts for batch spool creation.

Revision ID: spool_batch_receipts
Revises: feedback_attachments
"""

import sqlalchemy as sa

from alembic import op

revision = "spool_batch_receipts"
down_revision = "feedback_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spool_batch_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_spool_batch_receipt_user"),
            nullable=False,
        ),
        sa.Column("key_digest", sa.String(64), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_mode", sa.String(16), nullable=False),
        sa.Column("total_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("currency", sa.String(4), nullable=True),
        sa.Column("spool_ids", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "key_digest", name="uq_spool_batch_receipt_key"),
    )


def downgrade() -> None:
    op.drop_table("spool_batch_receipts")
