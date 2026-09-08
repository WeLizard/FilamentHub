"""PostgreSQL proof that sparse economics writes preserve field provenance."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.physical_printers import _locked_economics_printer
from app.models.calculator_profile import UserCalculatorProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.services.printer_economics_service import (
    lock_account_economics_profile,
    update_account_economics_sources,
)

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="set FH_TEST_POSTGRES_URL to run PostgreSQL concurrency tests",
    ),
]


async def _wait_until_blocked(sessions, blocked_pid: int, blocker_pid: int) -> None:
    async with sessions() as observer:
        async with asyncio.timeout(10):
            while True:
                blockers = await observer.scalar(
                    text("SELECT pg_blocking_pids(:pid)"), {"pid": blocked_pid}
                )
                if blocker_pid in blockers:
                    return
                await asyncio.sleep(0.02)


async def test_concurrent_sparse_printer_writes_keep_both_sources() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    pending = None
    try:
        async with sessions() as setup:
            user = User(
                email=f"economics-printer-{suffix}@example.com",
                username=f"economics_printer_{suffix}",
                password_hash="unused",
                active=True,
            )
            setup.add(user)
            await setup.flush()
            printer = UserPrinterDevice(
                user_id=user.id,
                name="Concurrent economics",
                device_fingerprint=None,
                supports_hh=False,
            )
            setup.add(printer)
            await setup.commit()
            user_id = user.id
            printer_id = printer.id

        async with sessions() as first, sessions() as second:
            first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
            second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
            first_row = await _locked_economics_printer(first, user_id, printer_id)
            first_row.average_power_watts = 420.0
            first_row.economics_field_sources = {
                "average_power_watts": "printer_explicit"
            }

            async def second_write() -> None:
                second_row = await _locked_economics_printer(second, user_id, printer_id)
                sources = dict(second_row.economics_field_sources or {})
                second_row.machine_hour_rate = 90.0
                sources["machine_hour_rate"] = "printer_explicit"
                second_row.economics_field_sources = sources
                await second.commit()

            pending = asyncio.create_task(second_write())
            await _wait_until_blocked(sessions, second_pid, first_pid)
            await first.commit()
            await asyncio.wait_for(pending, timeout=10)

        async with sessions() as verify:
            saved = await verify.scalar(
                select(UserPrinterDevice).where(UserPrinterDevice.id == printer_id)
            )
            assert saved is not None
            assert saved.average_power_watts == 420.0
            assert saved.machine_hour_rate == 90.0
            assert saved.economics_field_sources == {
                "average_power_watts": "printer_explicit",
                "machine_hour_rate": "printer_explicit",
            }
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await engine.dispose()


async def test_concurrent_sparse_account_writes_keep_both_sources() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    pending = None
    try:
        async with sessions() as setup:
            user = User(
                email=f"economics-account-{suffix}@example.com",
                username=f"economics_account_{suffix}",
                password_hash="unused",
                active=True,
            )
            setup.add(user)
            await setup.flush()
            setup.add(
                UserCalculatorProfile(
                    user_id=user.id,
                    economics_field_sources={"currency": "platform_default"},
                )
            )
            await setup.commit()
            user_id = user.id

        async with sessions() as first, sessions() as second:
            first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
            second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
            first_row = await lock_account_economics_profile(first, user_id)
            assert first_row is not None
            first_row.printing_rate_per_hour = 220.0
            update_account_economics_sources(
                first_row, {"printing_rate_per_hour"}, "account_explicit"
            )

            async def second_write() -> None:
                second_row = await lock_account_economics_profile(second, user_id)
                assert second_row is not None
                second_row.electricity_cost_per_kwh = 8.0
                update_account_economics_sources(
                    second_row, {"electricity_cost_per_kwh"}, "account_explicit"
                )
                await second.commit()

            pending = asyncio.create_task(second_write())
            await _wait_until_blocked(sessions, second_pid, first_pid)
            await first.commit()
            await asyncio.wait_for(pending, timeout=10)

        async with sessions() as verify:
            saved = await verify.scalar(
                select(UserCalculatorProfile).where(
                    UserCalculatorProfile.user_id == user_id
                )
            )
            assert saved is not None
            assert saved.printing_rate_per_hour == 220.0
            assert saved.electricity_cost_per_kwh == 8.0
            assert saved.economics_field_sources == {
                "currency": "platform_default",
                "printing_rate_per_hour": "account_explicit",
                "electricity_cost_per_kwh": "account_explicit",
            }
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await engine.dispose()
