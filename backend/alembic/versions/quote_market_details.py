"""Seller details a quote needs outside Russia, and which market it follows

Revision ID: quote_market_details
Revises: quote_details_enc
Create Date: 2026-07-27

A quote carried a tax id and a phone, which is enough at home and short
everywhere else: Russia expects КПП, ОГРН, a legal address and bank details;
a European or British quote is expected to name the company registration
number and the VAT number; a Chinese one carries the 18-character unified
social credit code. All of them are the seller's own data, so they are stored
encrypted like the details already there.
"""
from alembic import op
import sqlalchemy as sa


revision = "quote_market_details"
down_revision = "quote_details_enc"
branch_labels = None
depends_on = None


COLUMNS = (
    sa.Column("seller_registration_id", sa.String(length=512), nullable=False, server_default=""),
    sa.Column("seller_tax_code", sa.String(length=512), nullable=False, server_default=""),
    sa.Column("seller_address", sa.String(length=2048), nullable=False, server_default=""),
    sa.Column("seller_bank_details", sa.String(length=2048), nullable=False, server_default=""),
    sa.Column("quote_market", sa.String(length=8), nullable=False, server_default=""),
)


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("user_calculator_profiles", column.copy())


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("user_calculator_profiles", column.name)
