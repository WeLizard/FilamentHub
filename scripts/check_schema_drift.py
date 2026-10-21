#!/usr/bin/env python3
"""Compare a migrated PostgreSQL schema with the ORM metadata.

Called by ``check_postgres_runtime.py`` after ``alembic upgrade head``. Every
difference reported by ``alembic.autogenerate.compare_metadata`` is either

* noise that does not change database behaviour (the rules below), or
* drift, which fails the check unless it is listed in ``schema_drift_known.txt``.

The known-drift file is a ratchet: new drift fails, and an entry whose drift has
been fixed also fails until the entry is deleted.

Not compared: server defaults. Alembic evaluates them with SQL such as
``'[]'::json = '[]'``, which PostgreSQL rejects for ``json`` columns, so the
comparison aborts the whole run. Column comments are ignored as documentation.
"""

from __future__ import annotations

import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KNOWN_DRIFT_FILE = Path(__file__).with_name("schema_drift_known.txt")


@dataclass(frozen=True)
class Finding:
    key: str
    detail: str


@dataclass
class Report:
    noise: dict[str, int]
    drift: list[Finding]
    unexpected: list[Finding]
    stale: list[str]

    @property
    def ok(self) -> bool:
        return not self.unexpected and not self.stale


def load_known(path: Path = KNOWN_DRIFT_FILE) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            keys.add(line)
    return keys


def _flatten(diffs: list[Any]) -> list[tuple]:
    flat: list[tuple] = []
    for diff in diffs:
        if isinstance(diff, list):
            flat.extend(diff)
        else:
            flat.append(diff)
    return flat


def _index_columns(index: Any) -> tuple[str, ...]:
    return tuple(getattr(expr, "name", None) or str(expr) for expr in index.expressions)


def _fk_columns(fk: Any) -> tuple[str, ...]:
    return tuple(element.parent.name for element in fk.elements)


def _fk_target(fk: Any) -> str:
    return fk.elements[0].target_fullname if fk.elements else "?"


def _unique_columns(constraint: Any) -> tuple[str, ...]:
    return tuple(column.name for column in constraint.columns)


def _is_string_enum_noise(db_type: Any, model_type: Any) -> bool:
    """``Enum(native_enum=False)`` is a VARCHAR; alembic reports it as a type change."""
    from sqlalchemy import Enum, String

    if not (isinstance(model_type, Enum) and not model_type.native_enum):
        return False
    if isinstance(db_type, Enum) or not isinstance(db_type, String):
        return False
    return db_type.length is None or model_type.length is None or db_type.length >= model_type.length


def _is_json_noise(db_type: Any, model_type: Any) -> bool:
    """Portable ``JSON`` in the model, ``JSONB`` in PostgreSQL."""
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    return isinstance(db_type, JSONB) and isinstance(model_type, JSON) and not isinstance(model_type, JSONB)


def classify(diffs: list[Any], metadata: Any) -> tuple[dict[str, int], list[Finding]]:
    noise: dict[str, int] = defaultdict(int)
    drift: list[Finding] = []
    flat = _flatten(diffs)

    removed_indexes = [d[1] for d in flat if d[0] == "remove_index"]
    added_indexes = [d[1] for d in flat if d[0] == "add_index"]
    removed_uniques = [d[1] for d in flat if d[0] == "remove_constraint"]
    added_uniques = [d[1] for d in flat if d[0] == "add_constraint"]
    removed_fks = [d[1] for d in flat if d[0] == "remove_fk"]
    added_fks = [d[1] for d in flat if d[0] == "add_fk"]

    def model_unique_sets(table_name: str) -> set[tuple[str, ...]]:
        table = metadata.tables.get(table_name)
        if table is None:
            return set()
        sets = {_index_columns(i) for i in table.indexes if i.unique}
        sets |= {
            _unique_columns(c)
            for c in table.constraints
            if c.__class__.__name__ == "UniqueConstraint"
        }
        pk = tuple(c.name for c in table.primary_key.columns)
        sets.add(pk)
        return sets

    # Unique constraints: a unique constraint that the model expresses as a unique
    # index (or the reverse) enforces the same rule.
    unmatched_uniques = []
    for constraint in removed_uniques:
        table_name = constraint.table.name
        columns = _unique_columns(constraint)
        if columns in model_unique_sets(table_name):
            noise["unique constraint in DB, unique index in model"] += 1
            for index in added_indexes:
                if index.table.name == table_name and _index_columns(index) == columns:
                    added_indexes = [i for i in added_indexes if i is not index]
                    break
            removed_indexes = [
                i
                for i in removed_indexes
                if not (i.table.name == table_name and _index_columns(i) == columns)
            ]
        else:
            unmatched_uniques.append(constraint)
    for constraint in unmatched_uniques:
        drift.append(
            Finding(
                f"unique-only-in-db:{constraint.table.name}({','.join(_unique_columns(constraint))})",
                "unique constraint exists in the database but not in the model",
            )
        )
    for constraint in added_uniques:
        drift.append(
            Finding(
                f"unique-only-in-model:{constraint.table.name}({','.join(_unique_columns(constraint))})",
                "unique constraint exists in the model but not in the database",
            )
        )

    # Indexes: same table, columns and uniqueness under another name is naming noise.
    by_signature: dict[tuple, list] = defaultdict(list)
    for index in added_indexes:
        by_signature[(index.table.name, _index_columns(index), bool(index.unique))].append(index)
    for index in removed_indexes:
        signature = (index.table.name, _index_columns(index), bool(index.unique))
        if by_signature.get(signature):
            by_signature[signature].pop()
            noise["index differs only by name"] += 1
        else:
            drift.append(
                Finding(
                    f"index-only-in-db:{index.name}",
                    f"{index.table.name}({', '.join(_index_columns(index))}) "
                    f"unique={bool(index.unique)} exists in the database, not in the model",
                )
            )
    for leftovers in by_signature.values():
        for index in leftovers:
            table = metadata.tables[index.table.name]
            pk = tuple(c.name for c in table.primary_key.columns)
            if _index_columns(index) == pk:
                # Model asks for index=True on the primary key; PostgreSQL already has one.
                noise["redundant index on primary key"] += 1
                continue
            drift.append(
                Finding(
                    f"index-only-in-model:{index.name}",
                    f"{index.table.name}({', '.join(_index_columns(index))}) "
                    f"unique={bool(index.unique)} exists in the model, not in the database",
                )
            )

    # Foreign keys are matched by table, columns and target; the name is irrelevant.
    model_fks = {
        (fk.table.name, _fk_columns(fk), _fk_target(fk)): fk for fk in added_fks
    }
    for fk in removed_fks:
        signature = (fk.table.name, _fk_columns(fk), _fk_target(fk))
        model_fk = model_fks.pop(signature, None)
        if model_fk is None:
            drift.append(
                Finding(
                    f"fk-only-in-db:{signature[0]}({','.join(signature[1])})",
                    f"foreign key to {signature[2]} exists in the database, not in the model",
                )
            )
            continue
        options = (
            (fk.ondelete or "NO ACTION").upper(),
            (fk.onupdate or "NO ACTION").upper(),
        )
        model_options = (
            (model_fk.ondelete or "NO ACTION").upper(),
            (model_fk.onupdate or "NO ACTION").upper(),
        )
        if options == model_options:
            noise["foreign key differs only by name"] += 1
        else:
            drift.append(
                Finding(
                    f"fk-options:{signature[0]}({','.join(signature[1])})",
                    f"-> {signature[2]}: database ON DELETE/UPDATE {options}, model {model_options}",
                )
            )
    for signature in model_fks:
        drift.append(
            Finding(
                f"fk-only-in-model:{signature[0]}({','.join(signature[1])})",
                f"foreign key to {signature[2]} exists in the model, not in the database",
            )
        )

    for diff in flat:
        operation = diff[0]
        if operation in {"remove_index", "add_index", "remove_constraint", "add_constraint",
                         "remove_fk", "add_fk"}:
            continue
        if operation == "modify_comment":
            noise["column comment"] += 1
        elif operation == "modify_type":
            _, _, table, column, _, db_type, model_type = diff
            if _is_string_enum_noise(db_type, model_type):
                noise["non-native Enum stored as VARCHAR"] += 1
            elif _is_json_noise(db_type, model_type):
                noise["JSON in model, JSONB in database"] += 1
            else:
                drift.append(
                    Finding(
                        f"type:{table}.{column}",
                        f"database {db_type!r}, model {model_type!r}",
                    )
                )
        elif operation == "modify_nullable":
            _, _, table, column, _, db_nullable, model_nullable = diff
            drift.append(
                Finding(
                    f"nullable:{table}.{column}",
                    f"database nullable={db_nullable}, model nullable={model_nullable}",
                )
            )
        elif operation in {"add_column", "remove_column"}:
            table = diff[2]
            column = diff[3].name
            side = "model" if operation == "add_column" else "database"
            drift.append(Finding(f"column-only-in-{side}:{table}.{column}", operation))
        elif operation in {"add_table", "remove_table"}:
            side = "model" if operation == "add_table" else "database"
            drift.append(Finding(f"table-only-in-{side}:{diff[1].name}", operation))
        else:
            drift.append(Finding(f"{operation}:{diff[1:3]!r}", repr(diff)[:300]))

    return dict(noise), sorted(drift, key=lambda finding: finding.key)


def evaluate(diffs: list[Any], metadata: Any, known: set[str]) -> Report:
    noise, drift = classify(diffs, metadata)
    keys = {finding.key for finding in drift}
    return Report(
        noise=noise,
        drift=drift,
        unexpected=[finding for finding in drift if finding.key not in known],
        stale=sorted(known - keys),
    )


async def compare(engine: Any, metadata: Any) -> list[Any]:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    def run(connection: Any) -> list[Any]:
        context = MigrationContext.configure(
            connection,
            opts={"compare_type": True, "compare_server_default": False},
        )
        with warnings.catch_warnings():
            # Mutually dependent foreign keys make table sorting warn; the diff is unaffected.
            warnings.simplefilter("ignore")
            return compare_metadata(context, metadata)

    async with engine.connect() as connection:
        return await connection.run_sync(run)


def render(report: Report) -> str:
    lines = ["Schema drift (migrated PostgreSQL vs ORM metadata):"]
    for label, count in sorted(report.noise.items()):
        lines.append(f"  noise  {count:3d}  {label}")
    known = [f for f in report.drift if f not in report.unexpected]
    lines.append(f"  known drift tracked in schema_drift_known.txt: {len(known)}")
    if report.unexpected:
        lines.append("  NEW drift (fix the model or add a migration; do not extend the list silently):")
        lines.extend(f"    {f.key}: {f.detail}" for f in report.unexpected)
    if report.stale:
        lines.append("  Stale entries in schema_drift_known.txt (drift is fixed, delete them):")
        lines.extend(f"    {key}" for key in report.stale)
    return "\n".join(lines)


async def verify(engine: Any, metadata: Any) -> Report:
    return evaluate(await compare(engine, metadata), metadata, load_known())
