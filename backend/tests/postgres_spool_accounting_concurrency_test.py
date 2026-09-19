"""PostgreSQL proof that spool counters and history serialize together."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.spool_service import use_spool
from app.services.spool_usage_service import record_spool_usage, revert_spool_usage

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


async def _seed_spool(sessions, suffix: str) -> tuple[int, int]:
    async with sessions() as setup:
        user = User(
            email=f"spool-accounting-{suffix}@example.com",
            username=f"spool_accounting_{suffix}",
            password_hash="unused",
            active=True,
        )
        spool = UserSpool(
            user=user,
            initial_weight_g=1000.0,
            used_weight_g=0.0,
            state=UserSpoolState.active,
            source="postgres_test",
        )
        setup.add_all([user, spool])
        await setup.commit()
        return user.id, spool.id


async def test_concurrent_use_serializes_stale_preload_and_keeps_two_events() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    pending = None
    try:
        user_id, spool_id = await _seed_spool(sessions, uuid4().hex[:12])
        async with sessions() as first, sessions() as second:
            first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
            second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
            # This object is deliberately stale before the first transaction locks
            # and changes the row. use_spool must refresh it under FOR UPDATE.
            stale = await second.scalar(
                select(UserSpool).where(UserSpool.id == spool_id)
            )
            assert stale is not None and stale.used_weight_g == 0.0

            locked = await first.scalar(
                select(UserSpool).where(UserSpool.id == spool_id)
                .with_for_update().execution_options(populate_existing=True)
            )
            assert locked is not None
            locked.used_weight_g = 10.0
            await record_spool_usage(
                first,
                spool=locked,
                event_type=PresetUsageEventType.manual_adjust,
                delta_weight_g=10.0,
            )

            async def second_use() -> None:
                user = await second.get(User, user_id)
                assert user is not None
                await use_spool(second, user, spool_id, 20.0)

            pending = asyncio.create_task(second_use())
            await _wait_until_blocked(sessions, second_pid, first_pid)
            await first.commit()
            await asyncio.wait_for(pending, timeout=10)

        async with sessions() as verify:
            spool = await verify.scalar(select(UserSpool).where(UserSpool.id == spool_id))
            events = list(
                await verify.scalars(
                    select(PresetUsageEvent)
                    .where(PresetUsageEvent.spool_id == spool_id)
                    .order_by(PresetUsageEvent.id)
                )
            )
            assert spool is not None
            assert spool.used_weight_g == pytest.approx(30.0)
            assert spool.remaining_weight_g == pytest.approx(970.0)
            assert [event.delta_weight_g for event in events] == [10.0, 20.0]
            assert [event.remaining_weight_g for event in events] == [990.0, 970.0]
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await engine.dispose()


async def test_concurrent_revert_marks_original_once_and_preserves_ledger() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    pending = None
    try:
        user_id, spool_id = await _seed_spool(sessions, uuid4().hex[:12])
        async with sessions() as setup:
            spool = await setup.scalar(select(UserSpool).where(UserSpool.id == spool_id))
            assert spool is not None
            spool.used_weight_g = 200.0
            event = await record_spool_usage(
                setup,
                spool=spool,
                event_type=PresetUsageEventType.manual_adjust,
                delta_weight_g=200.0,
            )
            await setup.commit()
            event_id = event.id

        async with sessions() as first, sessions() as second:
            first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
            second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
            locked_spool = await first.scalar(
                select(UserSpool).where(UserSpool.id == spool_id)
                .with_for_update().execution_options(populate_existing=True)
            )
            locked_event = await first.scalar(
                select(PresetUsageEvent).where(PresetUsageEvent.id == event_id)
                .with_for_update().execution_options(populate_existing=True)
            )
            assert locked_spool is not None and locked_event is not None
            locked_spool.used_weight_g = 0.0
            locked_event.meta = {"reverted": True}
            await record_spool_usage(
                first,
                spool=locked_spool,
                event_type=PresetUsageEventType.manual_adjust,
                delta_weight_g=-200.0,
                meta={"reverts_event_id": event_id},
            )

            async def second_revert() -> None:
                with pytest.raises(HTTPException) as exc_info:
                    await revert_spool_usage(
                        second,
                        user_id=user_id,
                        spool_id=spool_id,
                        event_id=event_id,
                    )
                assert exc_info.value.status_code == 409
                assert exc_info.value.detail["code"] == "ERR_USAGE_EVENT_ALREADY_REVERTED"

            pending = asyncio.create_task(second_revert())
            await _wait_until_blocked(sessions, second_pid, first_pid)
            await first.commit()
            await asyncio.wait_for(pending, timeout=10)

        async with sessions() as verify:
            spool = await verify.scalar(select(UserSpool).where(UserSpool.id == spool_id))
            events = list(
                await verify.scalars(
                    select(PresetUsageEvent)
                    .where(PresetUsageEvent.spool_id == spool_id)
                    .order_by(PresetUsageEvent.id)
                )
            )
            assert spool is not None and spool.used_weight_g == pytest.approx(0.0)
            assert len(events) == 2
            assert [event.delta_weight_g for event in events] == [200.0, -200.0]
            assert events[0].meta == {"reverted": True}
            assert events[1].meta == {"reverts_event_id": event_id}
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await engine.dispose()
