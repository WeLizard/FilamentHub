"""The Workshop-tier numbers must count real printers, not plugin discovery rows."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmQuote
from app.models.print_job import PrintJob, PrintJobStatus
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.services.tier_metrics_service import live_printer_counts, regular_quote_users


async def _user(db: AsyncSession, name: str) -> User:
    user = User(
        email=f"{name}@example.com", username=name, password_hash="x", active=True
    )
    db.add(user)
    await db.flush()
    return user


async def _printer(db: AsyncSession, user: User, **fields) -> UserPrinterDevice:
    printer = UserPrinterDevice(user_id=user.id, name="Printer", **fields)
    db.add(printer)
    await db.flush()
    return printer


def _binding(user: User, printer: UserPrinterDevice, confirmed: bool, n: int):
    return PrinterConnectionBinding(
        user_id=user.id,
        physical_printer_id=printer.id,
        normalized_endpoint=f"moonraker|http|host-{n}|80|",
        assignment_confirmed=confirmed,
    )


@pytest.mark.asyncio
async def test_each_real_signal_makes_a_printer_live_and_discovery_alone_does_not(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, "signals")
    await _printer(db_session, user)
    unconfirmed = await _printer(db_session, user)
    db_session.add(_binding(user, unconfirmed, False, 1))
    seen = await _printer(db_session, user, last_seen_at=datetime.now(timezone.utc))
    printed = await _printer(db_session, user)
    db_session.add(
        PrintJob(
            user_id=user.id,
            physical_printer_id=printed.id,
            title="job",
            status=PrintJobStatus.completed,
            source="test",
            source_ref="job-1",
            source_payload_hash="0" * 64,
        )
    )
    bound = await _printer(db_session, user)
    db_session.add(_binding(user, bound, True, 2))
    await db_session.commit()

    live, over_threshold = await live_printer_counts(db_session)

    assert seen.id and printed.id and bound.id
    assert (live, over_threshold) == (3, 0)


@pytest.mark.asyncio
async def test_only_live_printers_push_a_user_over_the_threshold(
    db_session: AsyncSession,
) -> None:
    farm = await _user(db_session, "farm")
    for _ in range(5):
        await _printer(db_session, farm, last_seen_at=datetime.now(timezone.utc))
    discovered = await _user(db_session, "discovered")
    for _ in range(10):
        await _printer(db_session, discovered)
    await db_session.commit()

    live, over_threshold = await live_printer_counts(db_session)

    assert (live, over_threshold) == (5, 1)


async def _quote(db: AsyncSession, user: User, number: int, created_at: datetime) -> None:
    db.add(
        CrmQuote(
            user_id=user.id,
            number=f"Q-{number}",
            title="Quote",
            created_at=created_at,
            updated_at=created_at,
        )
    )


def _months_ago(now: datetime, months: int) -> datetime:
    total = now.year * 12 + now.month - 1 - months
    return datetime(total // 12, total % 12 + 1, 10, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_regular_quote_users_need_two_consecutive_calendar_months(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(timezone.utc)
    regular = await _user(db_session, "regular")
    await _quote(db_session, regular, 1, _months_ago(now, 1))
    await _quote(db_session, regular, 2, _months_ago(now, 0))
    gap = await _user(db_session, "gap")
    await _quote(db_session, gap, 3, _months_ago(now, 3))
    await _quote(db_session, gap, 4, _months_ago(now, 1))
    busy = await _user(db_session, "busy")
    await _quote(db_session, busy, 5, _months_ago(now, 2))
    await _quote(db_session, busy, 6, _months_ago(now, 2) + timedelta(days=1))
    await db_session.commit()

    assert await regular_quote_users(db_session, now) == 1
