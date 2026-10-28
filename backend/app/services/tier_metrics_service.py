"""Numbers behind the paid Workshop tier: live printers and regular quote makers."""

from datetime import datetime, timezone

from sqlalchemy import Integer, and_, case, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.crm import CrmQuote
from app.models.print_job import PrintJob
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.user_printer_device import UserPrinterDevice

WORKSHOP_PRINTER_THRESHOLD = 4
PAYMENT_LAUNCH_TARGET = 10
QUOTE_WINDOW_MONTHS = 6


def live_printer_condition() -> ColumnElement[bool]:
    """A printer row backed by a real signal, not only by plugin discovery.

    Reported by a device, provider or bridge (`last_seen_at`), used for a print
    job, or bound to a confirmed connection.
    """
    has_print_job = exists().where(PrintJob.physical_printer_id == UserPrinterDevice.id)
    has_confirmed_binding = exists().where(
        PrinterConnectionBinding.physical_printer_id == UserPrinterDevice.id,
        PrinterConnectionBinding.assignment_confirmed.is_(True),
    )
    return or_(UserPrinterDevice.last_seen_at.isnot(None), has_print_job, has_confirmed_binding)


def _month_index(column: ColumnElement) -> ColumnElement[int]:
    return cast(func.extract("year", column), Integer) * 12 + cast(
        func.extract("month", column), Integer
    )


def _first_of_month(moment: datetime, months_back: int) -> datetime:
    total = moment.year * 12 + moment.month - 1 - months_back
    return datetime(total // 12, total % 12 + 1, 1, tzinfo=timezone.utc)


async def live_printer_counts(db: AsyncSession) -> tuple[int, int]:
    """Live printers in total and users whose live printers exceed the threshold."""
    live_count = func.sum(case((live_printer_condition(), 1), else_=0))
    per_user = (
        select(live_count.label("live"))
        .select_from(UserPrinterDevice)
        .group_by(UserPrinterDevice.user_id)
        .subquery()
    )
    total, over_threshold = (
        await db.execute(
            select(
                func.coalesce(func.sum(per_user.c.live), 0),
                func.coalesce(
                    func.sum(case((per_user.c.live > WORKSHOP_PRINTER_THRESHOLD, 1), else_=0)),
                    0,
                ),
            )
        )
    ).one()
    return int(total), int(over_threshold)


async def regular_quote_users(db: AsyncSession, now: datetime) -> int:
    """Users with a quote in two consecutive calendar months of the recent window."""
    window_start = _first_of_month(now, QUOTE_WINDOW_MONTHS - 1)
    months = (
        select(CrmQuote.user_id.label("user_id"), _month_index(CrmQuote.created_at).label("m"))
        .where(CrmQuote.created_at >= window_start)
        .distinct()
        .subquery()
    )
    following = months.alias("following")
    return (
        await db.scalar(
            select(func.count(func.distinct(months.c.user_id))).join(
                following,
                and_(
                    following.c.user_id == months.c.user_id,
                    following.c.m == months.c.m + 1,
                ),
            )
        )
    ) or 0
