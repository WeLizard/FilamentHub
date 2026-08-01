"""Record the legal package attached to each acceptance.

Revision ID: legal_document_pack
Revises: email_language_columns
Create Date: 2026-08-01
"""

import sqlalchemy as sa

from alembic import op

revision = "legal_document_pack"
down_revision = "email_language_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("legal_document_pack", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "user_legal_acceptances",
        sa.Column(
            "legal_document_pack",
            sa.String(length=16),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.drop_constraint(
        "uq_user_legal_acceptance_version",
        "user_legal_acceptances",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_user_legal_acceptance_pack_version",
        "user_legal_acceptances",
        ["user_id", "document_type", "legal_document_pack", "document_version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_user_legal_acceptance_pack_version",
        "user_legal_acceptances",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_user_legal_acceptance_version",
        "user_legal_acceptances",
        ["user_id", "document_type", "document_version"],
    )
    op.drop_column("user_legal_acceptances", "legal_document_pack")
    op.drop_column("users", "legal_document_pack")
