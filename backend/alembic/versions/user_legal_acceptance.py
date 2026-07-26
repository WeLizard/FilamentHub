"""Add versioned legal acceptance evidence.

Revision ID: user_legal_acceptance
Revises: drop_user_bio
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "user_legal_acceptance"
down_revision: str | None = "drop_user_bio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("terms_version_accepted", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "personal_data_consent_version", sa.String(length=32), nullable=True
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "privacy_policy_version_presented",
            sa.String(length=32),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("legal_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("legal_acceptance_language", sa.String(length=8), nullable=True),
    )

    op.create_table(
        "user_legal_acceptances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("document_version", sa.String(length=32), nullable=False),
        sa.Column(
            "related_privacy_policy_version",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("acceptance_source", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_legal_acceptance_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "document_type",
            "document_version",
            name="uq_user_legal_acceptance_version",
        ),
    )
    op.create_index(
        "ix_user_legal_acceptances_user_id",
        "user_legal_acceptances",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_legal_acceptances_user_id",
        table_name="user_legal_acceptances",
    )
    op.drop_table("user_legal_acceptances")
    op.drop_column("users", "legal_acceptance_language")
    op.drop_column("users", "legal_accepted_at")
    op.drop_column("users", "personal_data_consent_version")
    op.drop_column("users", "privacy_policy_version_presented")
    op.drop_column("users", "terms_version_accepted")
