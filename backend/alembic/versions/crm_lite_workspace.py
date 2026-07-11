"""Add CRM-lite customers, versioned quotes, events, and orders.

Revision ID: crm_lite_workspace
Revises: filament_required_nozzle_hrc
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "crm_lite_workspace"
down_revision: Union[str, None] = "filament_required_nozzle_hrc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


quote_status = sa.Enum("draft", "sent", "accepted", "rejected", "expired", name="crmquotestatus")
order_status = sa.Enum(
    "new", "planned", "in_production", "ready", "completed", "cancelled", name="crmorderstatus"
)
quote_event_type = sa.Enum(
    "created",
    "version_created",
    "status_changed",
    "customer_changed",
    "shared",
    name="crmquoteeventtype",
)


def upgrade() -> None:
    op.create_table(
        "crm_customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("inn", sa.String(length=32), nullable=True),
        sa.Column("address", sa.String(length=1000), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_crm_customers_id", "crm_customers", ["id"])
    op.create_index("ix_crm_customers_user_id", "crm_customers", ["user_id"])
    op.create_index("ix_crm_customers_user_name", "crm_customers", ["user_id", "name"])

    op.create_table(
        "crm_quotes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("crm_customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("number", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", quote_status, nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="RUB"),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "number", name="uq_crm_quote_user_number"),
    )
    op.create_index("ix_crm_quotes_id", "crm_quotes", ["id"])
    op.create_index("ix_crm_quotes_user_id", "crm_quotes", ["user_id"])
    op.create_index("ix_crm_quotes_customer_id", "crm_quotes", ["customer_id"])
    op.create_index("ix_crm_quotes_status", "crm_quotes", ["status"])
    op.create_index(
        "ix_crm_quotes_user_status_updated", "crm_quotes", ["user_id", "status", "updated_at"]
    )

    op.create_table(
        "crm_quote_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "quote_id", sa.Integer(), sa.ForeignKey("crm_quotes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "source_history_id",
            sa.Integer(),
            sa.ForeignKey("calculator_history_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "shared_quote_id",
            sa.Integer(),
            sa.ForeignKey("shared_quotes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("seller_snapshot", sa.JSON(), nullable=False),
        sa.Column("customer_snapshot", sa.JSON(), nullable=False),
        sa.Column("calculation_snapshot", sa.JSON(), nullable=True),
        sa.Column("payment_terms", sa.String(length=1000), nullable=True),
        sa.Column("disclaimer_mode", sa.String(length=16), nullable=False, server_default="not_offer"),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("quote_id", "version_number", name="uq_crm_quote_version_number"),
    )
    op.create_index("ix_crm_quote_versions_id", "crm_quote_versions", ["id"])
    op.create_index("ix_crm_quote_versions_quote_id", "crm_quote_versions", ["quote_id"])

    op.create_table(
        "crm_quote_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("crm_quote_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False, server_default="pcs"),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("source_data", sa.JSON(), nullable=True),
        sa.UniqueConstraint("version_id", "position", name="uq_crm_quote_line_position"),
    )
    op.create_index("ix_crm_quote_lines_id", "crm_quote_lines", ["id"])
    op.create_index("ix_crm_quote_lines_version_id", "crm_quote_lines", ["version_id"])

    op.create_table(
        "crm_quote_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "quote_id", sa.Integer(), sa.ForeignKey("crm_quotes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", quote_event_type, nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_crm_quote_events_id", "crm_quote_events", ["id"])
    op.create_index("ix_crm_quote_events_quote_id", "crm_quote_events", ["quote_id"])
    op.create_index(
        "ix_crm_quote_events_quote_created", "crm_quote_events", ["quote_id", "created_at"]
    )

    op.create_table(
        "crm_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quote_id", sa.Integer(), sa.ForeignKey("crm_quotes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("crm_customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("number", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", order_status, nullable=False, server_default="new"),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("quote_id", name="uq_crm_order_quote"),
        sa.UniqueConstraint("user_id", "number", name="uq_crm_order_user_number"),
    )
    op.create_index("ix_crm_orders_id", "crm_orders", ["id"])
    op.create_index("ix_crm_orders_user_id", "crm_orders", ["user_id"])
    op.create_index("ix_crm_orders_quote_id", "crm_orders", ["quote_id"])
    op.create_index("ix_crm_orders_customer_id", "crm_orders", ["customer_id"])
    op.create_index("ix_crm_orders_status", "crm_orders", ["status"])
    op.create_index(
        "ix_crm_orders_user_status_updated", "crm_orders", ["user_id", "status", "updated_at"]
    )


def downgrade() -> None:
    op.drop_table("crm_orders")
    op.drop_table("crm_quote_events")
    op.drop_table("crm_quote_lines")
    op.drop_table("crm_quote_versions")
    op.drop_table("crm_quotes")
    op.drop_table("crm_customers")
    order_status.drop(op.get_bind(), checkfirst=True)
    quote_event_type.drop(op.get_bind(), checkfirst=True)
    quote_status.drop(op.get_bind(), checkfirst=True)
