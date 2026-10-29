"""Low-stock alert rules, the per-spool fired flag and two notification types.

Revision ID: stock_alert_rules
Revises: spool_collections

Backward compatible: new table, one defaulted column, two enum labels (a label
cannot be removed again, so the downgrade leaves them in place).
"""

import sqlalchemy as sa

from alembic import op

revision = "stock_alert_rules"
down_revision = "spool_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'low_stock_spool'")
            op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'low_stock_material'")
    op.add_column(
        "user_spools",
        sa.Column("low_stock_fired", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "stock_alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("spool_id", sa.Integer(), sa.ForeignKey("user_spools.id", ondelete="CASCADE")),
        sa.Column("material_key", sa.String(40)),
        sa.Column("threshold_g", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("scope IN ('all', 'spool', 'material')", name="ck_stock_alert_scope"),
        sa.CheckConstraint("threshold_g > 0", name="ck_stock_alert_threshold"),
    )
    op.create_index("ix_stock_alert_rules_user_id", "stock_alert_rules", ["user_id"])
    op.create_index(
        "uq_stock_alert_all",
        "stock_alert_rules",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("scope = 'all'"),
    )
    op.create_index(
        "uq_stock_alert_spool",
        "stock_alert_rules",
        ["user_id", "spool_id"],
        unique=True,
        postgresql_where=sa.text("scope = 'spool'"),
    )
    op.create_index(
        "uq_stock_alert_material",
        "stock_alert_rules",
        ["user_id", "material_key"],
        unique=True,
        postgresql_where=sa.text("scope = 'material'"),
    )


def downgrade() -> None:
    op.drop_table("stock_alert_rules")
    op.drop_column("user_spools", "low_stock_fired")
