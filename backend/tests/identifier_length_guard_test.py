"""Guard: DB identifier names stay within PostgreSQL's 63-char limit.

SQLite (the test DB) has no such limit, so an over-long index/constraint name
slips past every other test and only fails when the migration is applied to
Postgres. This walks Base.metadata and fails fast instead. When a long table +
column produces an auto-generated ix_<table>_<column> over the limit, give the
index an explicit short name.
"""

from __future__ import annotations

from app.db.base import Base

MAX_IDENTIFIER_LENGTH = 63  # PostgreSQL NAMEDATALEN - 1


def test_identifiers_within_postgres_limit() -> None:
    violations: list[str] = []
    for table in Base.metadata.tables.values():
        if len(table.name) > MAX_IDENTIFIER_LENGTH:
            violations.append(f"table {table.name} ({len(table.name)})")
        for index in table.indexes:
            if index.name and len(index.name) > MAX_IDENTIFIER_LENGTH:
                violations.append(f"index {index.name} ({len(index.name)})")
        for constraint in table.constraints:
            name = getattr(constraint, "name", None)
            if isinstance(name, str) and len(name) > MAX_IDENTIFIER_LENGTH:
                violations.append(f"constraint {name} ({len(name)})")

    assert not violations, (
        "Identifier(s) exceed PostgreSQL's 63-char limit — give them a short "
        "explicit name. Offending: " + ", ".join(sorted(violations))
    )
