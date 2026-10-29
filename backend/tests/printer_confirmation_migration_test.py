"""Backfill leaves only untouched Orca observations unconfirmed."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations

NULLABLE_DEVICE_COLUMNS = (
    "last_seen_at",
    "api_key",
    "device_fingerprint",
    "printer_hostname",
    "purchase_cost",
    "residual_value",
    "useful_life_hours",
    "average_power_watts",
    "power_hotend_w",
    "power_bed_w",
    "power_steppers_w",
    "power_electronics_w",
    "maintenance_cost_per_hour",
    "machine_hour_rate",
)


def _migration_module():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "printer_confirmation.py"
    spec = importlib.util.spec_from_file_location("printer_confirmation_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recommendation_choice_and_slice_report_keep_an_observed_printer_confirmed() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        nullable = ", ".join(f"{column} TEXT" for column in NULLABLE_DEVICE_COLUMNS)
        connection.execute(
            sa.text(
                "CREATE TABLE user_printer_devices (id INTEGER PRIMARY KEY, "
                "supports_hh BOOLEAN NOT NULL DEFAULT 0, reports_feed BOOLEAN NOT NULL DEFAULT 0, "
                f"{nullable}, created_at TEXT, updated_at TEXT)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE printer_connection_bindings "
                "(physical_printer_id INTEGER, assignment_confirmed BOOLEAN)"
            )
        )
        for table in (
            "print_jobs",
            "material_systems",
            "physical_printer_connectors",
            "orca_slice_reports",
        ):
            connection.execute(sa.text(f"CREATE TABLE {table} (physical_printer_id INTEGER)"))
        connection.execute(
            sa.text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, recommend_physical_printer_id INTEGER)"
            )
        )

        ghost, recommended, sliced, entered_by_hand = 1, 2, 3, 4
        for device_id in (ghost, recommended, sliced, entered_by_hand):
            connection.execute(
                sa.text(
                    "INSERT INTO user_printer_devices (id, created_at, updated_at) "
                    "VALUES (:id, '2026-08-01', '2026-08-02')"
                ),
                {"id": device_id},
            )
        for device_id in (ghost, recommended, sliced):
            connection.execute(
                sa.text("INSERT INTO printer_connection_bindings VALUES (:id, 0)"),
                {"id": device_id},
            )
        connection.execute(sa.text("INSERT INTO users VALUES (1, :id)"), {"id": recommended})
        connection.execute(sa.text("INSERT INTO orca_slice_reports VALUES (:id)"), {"id": sliced})

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        confirmed = {
            row.id: row.confirmed_at
            for row in connection.execute(
                sa.text("SELECT id, confirmed_at FROM user_printer_devices")
            )
        }

    assert confirmed[ghost] is None
    assert confirmed[recommended] is not None
    assert confirmed[sliced] is not None
    assert confirmed[entered_by_hand] is not None
