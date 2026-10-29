"""Printer confirmation: observed printers are proposals until confirmed.

Revision ID: printer_confirmation
Revises: material_base_subtype

``confirmed_at`` marks a physical printer a person or a real device vouched for;
``dismissed_at`` hides a proposal without deleting it. Existing rows are
confirmed except ghosts: rows created only by connection discovery that never
received any device signal, user-entered data, slice report, recommendation
choice or dependent record.
"""

import sqlalchemy as sa

from alembic import op

revision = "printer_confirmation"
down_revision = "material_base_subtype"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_printer_devices", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "user_printer_devices", sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        """
        UPDATE user_printer_devices AS d
        SET confirmed_at = COALESCE(d.updated_at, d.created_at)
        WHERE NOT (
            EXISTS (SELECT 1 FROM printer_connection_bindings b
                    WHERE b.physical_printer_id = d.id)
            AND NOT EXISTS (SELECT 1 FROM printer_connection_bindings b
                            WHERE b.physical_printer_id = d.id AND b.assignment_confirmed)
            AND d.last_seen_at IS NULL
            AND d.api_key IS NULL
            AND d.device_fingerprint IS NULL
            AND d.printer_hostname IS NULL
            AND NOT d.supports_hh
            AND NOT d.reports_feed
            AND d.purchase_cost IS NULL
            AND d.residual_value IS NULL
            AND d.useful_life_hours IS NULL
            AND d.average_power_watts IS NULL
            AND d.power_hotend_w IS NULL
            AND d.power_bed_w IS NULL
            AND d.power_steppers_w IS NULL
            AND d.power_electronics_w IS NULL
            AND d.maintenance_cost_per_hour IS NULL
            AND d.machine_hour_rate IS NULL
            AND NOT EXISTS (SELECT 1 FROM print_jobs j WHERE j.physical_printer_id = d.id)
            AND NOT EXISTS (SELECT 1 FROM material_systems m WHERE m.physical_printer_id = d.id)
            AND NOT EXISTS (SELECT 1 FROM physical_printer_connectors c
                            WHERE c.physical_printer_id = d.id)
            AND NOT EXISTS (SELECT 1 FROM orca_slice_reports r
                            WHERE r.physical_printer_id = d.id)
            AND NOT EXISTS (SELECT 1 FROM users u
                            WHERE u.recommend_physical_printer_id = d.id)
        )
        """
    )


def downgrade() -> None:
    op.drop_column("user_printer_devices", "dismissed_at")
    op.drop_column("user_printer_devices", "confirmed_at")
