"""Catalog bundles: bundles + bundle_imports tables, content_hash on profiles

Revision ID: d6f1b8e2a905
Revises: c5d3a7b92e04
Create Date: 2026-04-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d6f1b8e2a905"
down_revision: Union[str, None] = "c5d3a7b92e04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # bundles
    op.create_table(
        "bundles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "uploaded_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("validation_summary", sa.JSON(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("uuid", name="uq_bundles_uuid"),
        sa.UniqueConstraint("sha256", name="uq_bundles_sha256"),
    )
    op.create_index("ix_bundles_status", "bundles", ["status"])
    op.create_index("ix_bundles_source", "bundles", ["source"])
    op.create_index("ix_bundles_uploaded_by_user_id", "bundles", ["uploaded_by_user_id"])

    # bundle_imports
    op.create_table(
        "bundle_imports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "bundle_id",
            sa.BigInteger(),
            sa.ForeignKey("bundles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rolled_back_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_bundle_imports_bundle_id", "bundle_imports", ["bundle_id"])

    # printers.created_from_bundle_id
    op.add_column(
        "printers",
        sa.Column(
            "created_from_bundle_id",
            sa.BigInteger(),
            sa.ForeignKey("bundles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_printers_created_from_bundle_id", "printers", ["created_from_bundle_id"]
    )

    # printer_profiles: content_hash + created_from_bundle_id
    op.add_column(
        "printer_profiles",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "printer_profiles",
        sa.Column(
            "created_from_bundle_id",
            sa.BigInteger(),
            sa.ForeignKey("bundles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_printer_profiles_created_from_bundle_id",
        "printer_profiles",
        ["created_from_bundle_id"],
    )
    op.create_index(
        "uq_printer_profiles_content_hash",
        "printer_profiles",
        ["content_hash"],
        unique=True,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )

    # print_profiles: content_hash + created_from_bundle_id
    op.add_column(
        "print_profiles",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "print_profiles",
        sa.Column(
            "created_from_bundle_id",
            sa.BigInteger(),
            sa.ForeignKey("bundles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_print_profiles_created_from_bundle_id",
        "print_profiles",
        ["created_from_bundle_id"],
    )
    op.create_index(
        "uq_print_profiles_content_hash",
        "print_profiles",
        ["content_hash"],
        unique=True,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_print_profiles_content_hash", table_name="print_profiles")
    op.drop_index("ix_print_profiles_created_from_bundle_id", table_name="print_profiles")
    op.drop_column("print_profiles", "created_from_bundle_id")
    op.drop_column("print_profiles", "content_hash")

    op.drop_index("uq_printer_profiles_content_hash", table_name="printer_profiles")
    op.drop_index(
        "ix_printer_profiles_created_from_bundle_id", table_name="printer_profiles"
    )
    op.drop_column("printer_profiles", "created_from_bundle_id")
    op.drop_column("printer_profiles", "content_hash")

    op.drop_index("ix_printers_created_from_bundle_id", table_name="printers")
    op.drop_column("printers", "created_from_bundle_id")

    op.drop_index("ix_bundle_imports_bundle_id", table_name="bundle_imports")
    op.drop_table("bundle_imports")

    op.drop_index("ix_bundles_uploaded_by_user_id", table_name="bundles")
    op.drop_index("ix_bundles_source", table_name="bundles")
    op.drop_index("ix_bundles_status", table_name="bundles")
    op.drop_table("bundles")
