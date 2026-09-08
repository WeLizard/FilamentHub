"""The economics provenance migration is additive and reversible."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "calculator_economics_sources.py"
    )
    spec = importlib.util.spec_from_file_location(
        "calculator_economics_sources_migration", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_seeds_empty_sources_without_changing_existing_rows() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE TABLE user_calculator_profiles "
                    "(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"
                )
            )
            connection.execute(
                sa.text(
                    "CREATE TABLE user_printer_devices "
                    "(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"
                )
            )
            connection.execute(
                sa.text("INSERT INTO user_calculator_profiles VALUES (1, 10)")
            )
            connection.execute(sa.text("INSERT INTO user_printer_devices VALUES (2, 10)"))

            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
                assert connection.execute(
                    sa.text(
                        "SELECT id, user_id, economics_field_sources "
                        "FROM user_calculator_profiles"
                    )
                ).one() == (1, 10, "{}")
                assert connection.execute(
                    sa.text(
                        "SELECT id, user_id, economics_field_sources "
                        "FROM user_printer_devices"
                    )
                ).one() == (2, 10, "{}")

                migration.downgrade()
                assert {
                    column["name"]
                    for column in sa.inspect(connection).get_columns(
                        "user_calculator_profiles"
                    )
                } == {"id", "user_id"}
                assert {
                    column["name"]
                    for column in sa.inspect(connection).get_columns(
                        "user_printer_devices"
                    )
                } == {"id", "user_id"}
    finally:
        engine.dispose()
