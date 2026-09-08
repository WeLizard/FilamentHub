"""Avoid holding PostgreSQL's exclusive audit lock across constraint validation."""

import importlib.util
from io import StringIO
from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations


def migration_module():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "account_active_sessions.py"
    spec = importlib.util.spec_from_file_location("account_active_sessions_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_postgres_validation_releases_add_lock_before_scan_and_swaps_last():
    migration = migration_module()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={
            "as_sql": True,
            "output_buffer": output,
            "transactional_ddl": True,
        },
    )
    with context.begin_transaction(), Operations.context(context):
        migration.upgrade()
    statements = [item.strip() for item in output.getvalue().split(";") if item.strip()]
    add = next(index for index, sql in enumerate(statements) if "NOT VALID" in sql)
    validate = next(index for index, sql in enumerate(statements) if "VALIDATE CONSTRAINT" in sql)
    swap = next(
        index
        for index, sql in enumerate(statements)
        if sql == "ALTER TABLE audit_events DROP CONSTRAINT ck_audit_events_reason"
    )
    # Both statements are autocommit operations, separated by Alembic's new
    # transaction then its commit: ADD's lock cannot survive into VALIDATE.
    assert "BEGIN" in statements[add + 1 : validate]
    assert "COMMIT" in statements[add + 1 : validate]
    column_statements = [index for index, sql in enumerate(statements) if "ADD COLUMN" in sql]
    assert validate < min(column_statements) <= max(column_statements) < swap
    assert "RENAME CONSTRAINT" in statements[swap + 1]
    assert statements[swap + 2 :] == ["COMMIT"]


@pytest.mark.parametrize("new_audit", [False, True])
def test_sqlite_upgrade_preserves_audit_and_downgrade_refuses_new_history(new_audit):
    migration = migration_module()
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            connection.execute(sa.text("CREATE TABLE refresh_sessions (id TEXT PRIMARY KEY)"))
            connection.execute(
                sa.text(
                    "CREATE TABLE audit_events (id INTEGER PRIMARY KEY, reason VARCHAR(32) NOT NULL, "
                    f"CONSTRAINT ck_audit_events_reason CHECK (reason IN ({migration._OLD_REASONS})))"
                )
            )
            connection.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
            connection.execute(sa.text("INSERT INTO refresh_sessions (id) VALUES ('retained')"))
            connection.execute(
                sa.text("INSERT INTO audit_events (id, reason) VALUES (1, 'logout')")
            )
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
                assert (
                    connection.execute(
                        sa.text("SELECT reason FROM audit_events WHERE id=1")
                    ).scalar()
                    == "logout"
                )
                assert connection.execute(
                    sa.text("SELECT browser, os, device_type FROM refresh_sessions")
                ).one() == ("unknown", "unknown", "unknown")
                if new_audit:
                    connection.execute(
                        sa.text(
                            "INSERT INTO audit_events (id, reason) VALUES (2, 'session_revoke')"
                        )
                    )
                    with pytest.raises(RuntimeError, match="session revocation audit events"):
                        migration.downgrade()
                    assert (
                        connection.execute(sa.text("SELECT COUNT(*) FROM audit_events")).scalar()
                        == 2
                    )
                else:
                    migration.downgrade()
                    assert (
                        connection.execute(sa.text("SELECT reason FROM audit_events")).scalar()
                        == "logout"
                    )
                    assert {
                        column["name"]
                        for column in sa.inspect(connection).get_columns("refresh_sessions")
                    } == {"id"}
                    assert {
                        column["name"] for column in sa.inspect(connection).get_columns("users")
                    } == {"id"}
    finally:
        engine.dispose()
