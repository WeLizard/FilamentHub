"""extend orca profiles structures

Revision ID: 9c0a8d1ab3ab
Revises: f2b7c90864d4
Create Date: 2025-11-10 15:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c0a8d1ab3ab"
down_revision: str | None = "f2b7c90864d4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Printers
    op.add_column("printers", sa.Column("model_id", sa.String(length=120), nullable=True))
    op.add_column("printers", sa.Column("family", sa.String(length=100), nullable=True))
    op.add_column("printers", sa.Column("technology", sa.String(length=30), nullable=True))
    op.add_column(
        "printers",
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.add_column("printers", sa.Column("vendor", sa.String(length=100), nullable=True))
    op.add_column("printers", sa.Column("nozzle_options", sa.JSON(), nullable=True))
    op.add_column("printers", sa.Column("default_materials", sa.JSON(), nullable=True))
    op.add_column("printers", sa.Column("extra_metadata", sa.JSON(), nullable=True))

    op.create_index("ix_printers_model_id", "printers", ["model_id"], unique=False)
    op.create_index("ix_printers_family", "printers", ["family"], unique=False)
    op.create_index("ix_printers_technology", "printers", ["technology"], unique=False)
    op.create_index("ix_printers_source", "printers", ["source"], unique=False)
    op.create_index("ix_printers_vendor", "printers", ["vendor"], unique=False)

    # Printer profiles
    op.add_column(
        "printer_profiles",
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.add_column(
        "printer_profiles",
        sa.Column("vendor", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "printer_profiles",
        sa.Column("external_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "printer_profiles",
        sa.Column("setting_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "printer_profiles",
        sa.Column("nozzle_diameters", sa.JSON(), nullable=True),
    )
    op.add_column(
        "printer_profiles",
        sa.Column("printable_area", sa.JSON(), nullable=True),
    )
    op.add_column(
        "printer_profiles",
        sa.Column("printable_height_mm", sa.Float(), nullable=True),
    )
    op.add_column(
        "printer_profiles",
        sa.Column("default_print_profile_slug", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "printer_profiles",
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
    )

    op.create_index("ix_printer_profiles_source", "printer_profiles", ["source"], unique=False)
    op.create_index("ix_printer_profiles_vendor", "printer_profiles", ["vendor"], unique=False)
    op.create_index("ix_printer_profiles_external_id", "printer_profiles", ["external_id"], unique=False)
    op.create_index("ix_printer_profiles_setting_id", "printer_profiles", ["setting_id"], unique=False)
    op.create_index(
        "ix_printer_profiles_default_print_profile_slug",
        "printer_profiles",
        ["default_print_profile_slug"],
        unique=False,
    )

    # Print profiles
    op.add_column(
        "print_profiles",
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.add_column(
        "print_profiles",
        sa.Column("vendor", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "print_profiles",
        sa.Column("external_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "print_profiles",
        sa.Column("setting_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "print_profiles",
        sa.Column("quality_tier", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "print_profiles",
        sa.Column("default_nozzle", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "print_profiles",
        sa.Column("layer_height_mm", sa.Float(), nullable=True),
    )
    op.add_column(
        "print_profiles",
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
    )

    op.create_index("ix_print_profiles_source", "print_profiles", ["source"], unique=False)
    op.create_index("ix_print_profiles_vendor", "print_profiles", ["vendor"], unique=False)
    op.create_index("ix_print_profiles_external_id", "print_profiles", ["external_id"], unique=False)
    op.create_index("ix_print_profiles_setting_id", "print_profiles", ["setting_id"], unique=False)
    op.create_index("ix_print_profiles_quality_tier", "print_profiles", ["quality_tier"], unique=False)
    op.create_index("ix_print_profiles_default_nozzle", "print_profiles", ["default_nozzle"], unique=False)
    op.create_index("ix_print_profiles_layer_height_mm", "print_profiles", ["layer_height_mm"], unique=False)

    # Junction tables for compatibility
    op.create_table(
        "print_profile_printers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "print_profile_id",
            sa.Integer(),
            sa.ForeignKey("print_profiles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "printer_id",
            sa.Integer(),
            sa.ForeignKey("printers.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("printer_slug", sa.String(length=200), nullable=False, index=True),
        sa.Column(
            "relation_type",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'explicit'"),
            index=True,
        ),
        sa.Column("condition", sa.Text(), nullable=True),
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

    op.create_table(
        "print_profile_filaments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "print_profile_id",
            sa.Integer(),
            sa.ForeignKey("print_profiles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "filament_id",
            sa.Integer(),
            sa.ForeignKey("filaments.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("filament_slug", sa.String(length=200), nullable=False, index=True),
        sa.Column(
            "relation_type",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'explicit'"),
            index=True,
        ),
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


def downgrade() -> None:
    op.drop_table("print_profile_filaments")
    op.drop_table("print_profile_printers")

    op.drop_index("ix_print_profiles_layer_height_mm", table_name="print_profiles")
    op.drop_index("ix_print_profiles_default_nozzle", table_name="print_profiles")
    op.drop_index("ix_print_profiles_quality_tier", table_name="print_profiles")
    op.drop_index("ix_print_profiles_setting_id", table_name="print_profiles")
    op.drop_index("ix_print_profiles_external_id", table_name="print_profiles")
    op.drop_index("ix_print_profiles_vendor", table_name="print_profiles")
    op.drop_index("ix_print_profiles_source", table_name="print_profiles")

    op.drop_column("print_profiles", "extra_metadata")
    op.drop_column("print_profiles", "layer_height_mm")
    op.drop_column("print_profiles", "default_nozzle")
    op.drop_column("print_profiles", "quality_tier")
    op.drop_column("print_profiles", "setting_id")
    op.drop_column("print_profiles", "external_id")
    op.drop_column("print_profiles", "vendor")
    op.drop_column("print_profiles", "source")

    op.drop_index("ix_printer_profiles_default_print_profile_slug", table_name="printer_profiles")
    op.drop_index("ix_printer_profiles_setting_id", table_name="printer_profiles")
    op.drop_index("ix_printer_profiles_external_id", table_name="printer_profiles")
    op.drop_index("ix_printer_profiles_vendor", table_name="printer_profiles")
    op.drop_index("ix_printer_profiles_source", table_name="printer_profiles")

    op.drop_column("printer_profiles", "extra_metadata")
    op.drop_column("printer_profiles", "default_print_profile_slug")
    op.drop_column("printer_profiles", "printable_height_mm")
    op.drop_column("printer_profiles", "printable_area")
    op.drop_column("printer_profiles", "nozzle_diameters")
    op.drop_column("printer_profiles", "setting_id")
    op.drop_column("printer_profiles", "external_id")
    op.drop_column("printer_profiles", "vendor")
    op.drop_column("printer_profiles", "source")

    op.drop_index("ix_printers_vendor", table_name="printers")
    op.drop_index("ix_printers_source", table_name="printers")
    op.drop_index("ix_printers_technology", table_name="printers")
    op.drop_index("ix_printers_family", table_name="printers")
    op.drop_index("ix_printers_model_id", table_name="printers")

    op.drop_column("printers", "extra_metadata")
    op.drop_column("printers", "default_materials")
    op.drop_column("printers", "nozzle_options")
    op.drop_column("printers", "vendor")
    op.drop_column("printers", "source")
    op.drop_column("printers", "technology")
    op.drop_column("printers", "family")
    op.drop_column("printers", "model_id")

