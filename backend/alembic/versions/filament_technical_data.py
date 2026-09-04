"""Add exact-variant storage and physical technical data.

Revision ID: filament_technical_data
Revises: catalog_master_import
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "filament_technical_data"
down_revision = "catalog_master_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filaments", sa.Column("storage_temperature_min_c", sa.Float()))
    op.add_column("filaments", sa.Column("storage_temperature_max_c", sa.Float()))
    op.add_column(
        "filaments",
        sa.Column("storage_relative_humidity_max_percent", sa.Float()),
    )
    op.add_column(
        "filaments",
        sa.Column("storage_relative_humidity_target_percent", sa.Float()),
    )
    op.add_column("filaments", sa.Column("storage_airtight_required", sa.Boolean()))
    op.add_column("filaments", sa.Column("storage_desiccant_recommended", sa.Boolean()))
    op.add_column(
        "filaments",
        sa.Column("storage_light_protection_required", sa.Boolean()),
    )
    op.add_column("filaments", sa.Column("storage_after_opening_guidance", sa.Text()))
    op.add_column("filaments", sa.Column("unopened_shelf_life_months", sa.Integer()))
    op.add_column("filaments", sa.Column("spool_outer_diameter_mm", sa.Float()))
    op.add_column("filaments", sa.Column("spool_width_mm", sa.Float()))
    op.add_column("filaments", sa.Column("spool_core_diameter_mm", sa.Float()))
    op.add_column("filaments", sa.Column("packaged_gross_weight_g", sa.Float()))
    op.add_column(
        "filaments",
        sa.Column("technical_data_source_ref", sa.String(length=500)),
    )
    op.add_column(
        "filaments",
        sa.Column("technical_data_version", sa.String(length=100)),
    )
    op.add_column("filaments", sa.Column("technical_data_effective_date", sa.Date()))
    op.add_column(
        "filaments",
        sa.Column("technical_data_last_verified_by", sa.String(length=32)),
    )
    op.add_column(
        "filaments",
        sa.Column("technical_data_last_verified_at", sa.DateTime(timezone=True)),
    )

    op.execute(sa.text("""
            UPDATE filaments
            SET technical_data_last_verified_by = 'legacy_catalog',
                technical_data_last_verified_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
            WHERE density IS NOT NULL
               OR drying_required IS NOT NULL
               OR drying_temperature_c IS NOT NULL
               OR drying_duration_hours IS NOT NULL
               OR enclosure_requirement IS NOT NULL
               OR chamber_temperature_c IS NOT NULL
               OR json_array_length(bed_adhesives) > 0
               OR json_array_length(post_processing_chemicals) > 0
               OR spool_weight IS NOT NULL
               OR empty_spool_weight_g IS NOT NULL
               OR recommended_nozzle_temp_min IS NOT NULL
               OR recommended_nozzle_temp_max IS NOT NULL
               OR recommended_bed_temp_min IS NOT NULL
               OR recommended_bed_temp_max IS NOT NULL
               OR required_nozzle_hrc IS NOT NULL
            """))

    op.create_check_constraint(
        "ck_filaments_drying_parameters_pair",
        "filaments",
        "(drying_temperature_c IS NULL) = (drying_duration_hours IS NULL)",
    )
    op.create_check_constraint(
        "ck_filaments_drying_required_values",
        "filaments",
        "drying_required IS NULL OR NOT drying_required OR drying_temperature_c IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_filaments_drying_not_required",
        "filaments",
        "drying_required IS NULL OR drying_required OR drying_temperature_c IS NULL",
    )
    op.create_check_constraint(
        "ck_filaments_storage_temperature",
        "filaments",
        "(storage_temperature_min_c IS NULL) = "
        "(storage_temperature_max_c IS NULL) AND "
        "(storage_temperature_min_c IS NULL OR "
        "storage_temperature_min_c BETWEEN -100 AND 200 AND "
        "storage_temperature_max_c BETWEEN -100 AND 200 AND "
        "storage_temperature_min_c <= storage_temperature_max_c)",
    )
    op.create_check_constraint(
        "ck_filaments_storage_humidity_max",
        "filaments",
        "storage_relative_humidity_max_percent IS NULL OR "
        "storage_relative_humidity_max_percent BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_filaments_storage_humidity_target",
        "filaments",
        "storage_relative_humidity_target_percent IS NULL OR "
        "storage_relative_humidity_target_percent BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_filaments_storage_humidity_order",
        "filaments",
        "storage_relative_humidity_max_percent IS NULL OR "
        "storage_relative_humidity_target_percent IS NULL OR "
        "storage_relative_humidity_target_percent <= "
        "storage_relative_humidity_max_percent",
    )
    op.create_check_constraint(
        "ck_filaments_shelf_life",
        "filaments",
        "unopened_shelf_life_months IS NULL OR " "unopened_shelf_life_months BETWEEN 1 AND 1200",
    )
    op.create_check_constraint(
        "ck_filaments_spool_outer_diameter",
        "filaments",
        "spool_outer_diameter_mm IS NULL OR "
        "spool_outer_diameter_mm > 0 AND spool_outer_diameter_mm <= 2000",
    )
    op.create_check_constraint(
        "ck_filaments_spool_width",
        "filaments",
        "spool_width_mm IS NULL OR spool_width_mm > 0 AND spool_width_mm <= 2000",
    )
    op.create_check_constraint(
        "ck_filaments_spool_core_diameter",
        "filaments",
        "spool_core_diameter_mm IS NULL OR "
        "spool_core_diameter_mm > 0 AND spool_core_diameter_mm <= 2000",
    )
    op.create_check_constraint(
        "ck_filaments_spool_diameter_order",
        "filaments",
        "spool_outer_diameter_mm IS NULL OR spool_core_diameter_mm IS NULL OR "
        "spool_core_diameter_mm <= spool_outer_diameter_mm",
    )
    op.create_check_constraint(
        "ck_filaments_packaged_weight",
        "filaments",
        "packaged_gross_weight_g IS NULL OR "
        "packaged_gross_weight_g > 0 AND packaged_gross_weight_g <= 100000",
    )
    op.create_check_constraint(
        "ck_filaments_packaged_weight_total",
        "filaments",
        "(packaged_gross_weight_g IS NULL OR spool_weight IS NULL OR "
        "packaged_gross_weight_g >= spool_weight) AND "
        "(packaged_gross_weight_g IS NULL OR empty_spool_weight_g IS NULL OR "
        "packaged_gross_weight_g >= empty_spool_weight_g) AND "
        "(packaged_gross_weight_g IS NULL OR spool_weight IS NULL OR "
        "empty_spool_weight_g IS NULL OR "
        "packaged_gross_weight_g >= spool_weight + empty_spool_weight_g)",
    )
    op.create_check_constraint(
        "ck_filaments_technical_verifier",
        "filaments",
        "technical_data_last_verified_by IS NULL OR "
        "technical_data_last_verified_by IN "
        "('manufacturer_representative','administrator','legacy_catalog')",
    )
    op.create_check_constraint(
        "ck_filaments_nozzle_temp_order",
        "filaments",
        "recommended_nozzle_temp_min IS NULL OR "
        "recommended_nozzle_temp_max IS NULL OR "
        "recommended_nozzle_temp_min <= recommended_nozzle_temp_max",
    )
    op.create_check_constraint(
        "ck_filaments_bed_temp_order",
        "filaments",
        "recommended_bed_temp_min IS NULL OR "
        "recommended_bed_temp_max IS NULL OR "
        "recommended_bed_temp_min <= recommended_bed_temp_max",
    )


def downgrade() -> None:
    for constraint in (
        "ck_filaments_bed_temp_order",
        "ck_filaments_nozzle_temp_order",
        "ck_filaments_technical_verifier",
        "ck_filaments_packaged_weight_total",
        "ck_filaments_packaged_weight",
        "ck_filaments_spool_diameter_order",
        "ck_filaments_spool_core_diameter",
        "ck_filaments_spool_width",
        "ck_filaments_spool_outer_diameter",
        "ck_filaments_shelf_life",
        "ck_filaments_storage_humidity_order",
        "ck_filaments_storage_humidity_target",
        "ck_filaments_storage_humidity_max",
        "ck_filaments_storage_temperature",
        "ck_filaments_drying_not_required",
        "ck_filaments_drying_required_values",
        "ck_filaments_drying_parameters_pair",
    ):
        op.drop_constraint(constraint, "filaments", type_="check")

    for column in (
        "technical_data_last_verified_at",
        "technical_data_last_verified_by",
        "technical_data_effective_date",
        "technical_data_version",
        "technical_data_source_ref",
        "packaged_gross_weight_g",
        "spool_core_diameter_mm",
        "spool_width_mm",
        "spool_outer_diameter_mm",
        "unopened_shelf_life_months",
        "storage_after_opening_guidance",
        "storage_light_protection_required",
        "storage_desiccant_recommended",
        "storage_airtight_required",
        "storage_relative_humidity_target_percent",
        "storage_relative_humidity_max_percent",
        "storage_temperature_max_c",
        "storage_temperature_min_c",
    ):
        op.drop_column("filaments", column)
