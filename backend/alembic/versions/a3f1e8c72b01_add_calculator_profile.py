"""Add user_calculator_profiles table

Revision ID: a3f1e8c72b01
Revises: c8d34f71b2aa
Create Date: 2026-03-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3f1e8c72b01"
down_revision: Union[str, None] = "c8d34f71b2aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_calculator_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        # Economics
        sa.Column("electricity_cost_per_kwh", sa.Float(), nullable=False, server_default="6.0"),
        sa.Column("printer_power_w", sa.Float(), nullable=False, server_default="350.0"),
        sa.Column("modeling_rate_per_hour", sa.Float(), nullable=False, server_default="934.0"),
        sa.Column("postprocessing_rate_per_hour", sa.Float(), nullable=False, server_default="100.0"),
        sa.Column("printing_rate_per_hour", sa.Float(), nullable=False, server_default="170.0"),
        sa.Column("amortization_rate_per_hour", sa.Float(), nullable=False, server_default="16.0"),
        sa.Column("overhead_percent", sa.Float(), nullable=False, server_default="20.0"),
        sa.Column("markup_percent", sa.Float(), nullable=False, server_default="30.0"),
        sa.Column("tax_rate_percent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("fixed_costs", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("bed_prep_cost_per_print", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("min_order_price", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("round_to_nearest", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("rounding_mode", sa.String(16), nullable=False, server_default="up"),
        # Quote
        sa.Column("seller_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("seller_inn", sa.String(32), nullable=False, server_default=""),
        sa.Column("seller_phone", sa.String(64), nullable=False, server_default=""),
        sa.Column("payment_terms", sa.String(512), nullable=False, server_default=""),
        sa.Column("validity_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("disclaimer_mode", sa.String(16), nullable=False, server_default="not_offer"),
        sa.Column("currency", sa.String(4), nullable=False, server_default="₽"),
        sa.Column("quote_number_prefix", sa.String(32), nullable=False, server_default="КП"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_calculator_profiles")
