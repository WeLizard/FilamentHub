"""Room for encrypted quote details

Revision ID: quote_details_enc
Revises: calc_machine_defaults
Create Date: 2026-07-27

The seller's name, tax id, phone and payment terms are stored encrypted from
now on, and ciphertext is longer than what a person typed. Existing rows stay
readable: anything without the marker prefix is read as plain text.
"""
from alembic import op
import sqlalchemy as sa


revision = "quote_details_enc"
down_revision = "calc_machine_defaults"
branch_labels = None
depends_on = None

WIDENED = (
    ("seller_name", 255, 1024),
    ("seller_inn", 32, 512),
    ("seller_phone", 64, 512),
    ("payment_terms", 512, 2048),
)


def upgrade() -> None:
    for column, _plain, encrypted in WIDENED:
        op.alter_column(
            "user_calculator_profiles",
            column,
            type_=sa.String(length=encrypted),
            existing_nullable=False,
        )


def downgrade() -> None:
    for column, plain, _encrypted in WIDENED:
        op.alter_column(
            "user_calculator_profiles",
            column,
            type_=sa.String(length=plain),
            existing_nullable=False,
        )
