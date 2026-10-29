"""Calendar-month buckets shared by the money reports."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import extract, func
from sqlalchemy.sql.elements import ColumnElement


def month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def month_label(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def last_month_indexes(now: datetime, count: int) -> list[int]:
    """The calendar months ending with the one that holds ``now``, oldest first."""
    current = month_index(now.year, now.month)
    return list(range(current - count + 1, current + 1))


def month_start(index: int) -> datetime:
    return datetime(index // 12, index % 12 + 1, 1, tzinfo=timezone.utc)


def month_index_expr(column: ColumnElement, dialect_name: str) -> ColumnElement:
    """SQL month index of a timestamp or date, read in UTC."""
    if dialect_name == "postgresql":
        column = func.timezone("UTC", column)
    return extract("year", column) * 12 + extract("month", column) - 1


def date_month_index_expr(column: ColumnElement) -> ColumnElement:
    return extract("year", column) * 12 + extract("month", column) - 1
