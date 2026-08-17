"""currencies reference table

Revision ID: currency_reference
Revises: preset_moderation_not_required
Create Date: 2026-08-16

The list of currencies lived in the frontend, so adding one meant a release. It is
reference data: it belongs in a table an admin can extend. The rows come from
``app.services.currency_service`` so the reference has a single definition.
"""

from alembic import op
import sqlalchemy as sa

from app.services.currency_service import currency_seed_rows

revision = "currency_reference"
down_revision = "preset_moderation_not_required"
branch_labels = None
depends_on = None


def upgrade() -> None:
    currencies = op.create_table(
        "currencies",
        sa.Column("code", sa.String(length=4), primary_key=True),
        sa.Column("symbol", sa.String(length=8), nullable=False),
        sa.Column("decimals", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("rounding_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("countries", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
    )

    op.bulk_insert(currencies, currency_seed_rows())


def downgrade() -> None:
    op.drop_table("currencies")
