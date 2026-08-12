"""Add explicit spool reservations to production orders.

Revision ID: crm_order_spool_reservations
Revises: print_profile_config_links
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "crm_order_spool_reservations"
down_revision: str | None = "print_profile_config_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_orders",
        sa.Column(
            "material_requirements",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.create_table(
        "crm_order_spool_reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("spool_id", sa.Integer(), nullable=False),
        sa.Column("material_line_key", sa.String(length=160), nullable=False),
        sa.Column("material_label", sa.String(length=255), nullable=True),
        sa.Column("weight_g", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(length=32), nullable=True),
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
        sa.ForeignKeyConstraint(["order_id"], ["crm_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spool_id"], ["user_spools.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_order_spool_reservations_order_status",
        "crm_order_spool_reservations",
        ["order_id", "status"],
    )
    op.create_index(
        "ix_crm_order_spool_reservations_user_status_spool",
        "crm_order_spool_reservations",
        ["user_id", "status", "spool_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_crm_order_spool_reservations_user_status_spool",
        table_name="crm_order_spool_reservations",
    )
    op.drop_index(
        "ix_crm_order_spool_reservations_order_status",
        table_name="crm_order_spool_reservations",
    )
    op.drop_table("crm_order_spool_reservations")
    op.drop_column("crm_orders", "material_requirements")
