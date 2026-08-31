"""PostgreSQL proof that concurrent adapters cannot steal one tag UID."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.spool_tag import SpoolTag
from app.models.user import User
from app.models.user_spool import UserSpool
from app.services.spool_tag_service import SpoolTagConflict, link_spool_tag

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="set FH_TEST_POSTGRES_URL to run PostgreSQL concurrency tests",
    ),
]


async def test_concurrent_adapters_cannot_reassign_one_uid() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    async with sessions() as setup:
        user = User(
            email=f"tag-pg-{suffix}@example.com",
            username=f"tag_pg_{suffix}",
            password_hash="unused",
            active=True,
        )
        setup.add(user)
        await setup.flush()
        spools = [
            UserSpool(user_id=user.id, initial_weight_g=1000, source="manual")
            for _ in range(2)
        ]
        setup.add_all(spools)
        await setup.commit()
        user_id = user.id
        spool_ids = [spool.id for spool in spools]

    ready = asyncio.Event()
    waiting = 0
    waiting_lock = asyncio.Lock()

    async def link(spool_id: int) -> tuple[str, int]:
        nonlocal waiting
        async with sessions() as db:
            async with waiting_lock:
                waiting += 1
                if waiting == 2:
                    ready.set()
            await ready.wait()
            try:
                tag = await link_spool_tag(
                    db,
                    user_id=user_id,
                    spool_id=spool_id,
                    uid="A1B2C3D4E5F60708",
                    technology="nfc",
                    source="postgres_test",
                )
                assert tag is not None
                await db.commit()
                return "linked", spool_id
            except SpoolTagConflict as exc:
                await db.rollback()
                return "conflict", exc.spool_id

    results = await asyncio.gather(*(link(spool_id) for spool_id in spool_ids))
    assert sorted(status for status, _spool_id in results) == ["conflict", "linked"]
    winner = next(spool_id for status, spool_id in results if status == "linked")
    assert next(spool_id for status, spool_id in results if status == "conflict") == winner

    async with sessions() as verify:
        rows = list(
            (
                await verify.scalars(
                    select(SpoolTag).where(
                        SpoolTag.user_id == user_id,
                        SpoolTag.uid == "A1B2C3D4E5F60708",
                    )
                )
            ).all()
        )
        assert len(rows) == 1
        assert rows[0].spool_id == winner
        assert await verify.scalar(
            select(func.count())
            .select_from(SpoolTag)
            .where(SpoolTag.user_id == user_id)
        ) == 1
    await engine.dispose()

