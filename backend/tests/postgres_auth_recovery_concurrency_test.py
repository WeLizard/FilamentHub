"""PostgreSQL proof that one recovery grant changes a password only once."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import decode_refresh_token, token_auth_version_matches
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.services.account_auth_service import (
    InvalidPasswordResetError,
    issue_password_reset_grant,
    reset_password_with_grant,
    token_data_for_user,
)
from app.services.refresh_session_service import issue_refresh_session, rotate_refresh_session

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="set FH_TEST_POSTGRES_URL to run PostgreSQL concurrency tests",
    ),
]


async def test_concurrent_reset_consumes_grant_once_and_revokes_all_refresh_families() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    async with sessions() as setup:
        user = User(
            email=f"reset-race-{suffix}@example.com",
            username=f"reset_race_{suffix}",
            password_hash="old-password-hash",
            active=True,
        )
        setup.add(user)
        await setup.flush()
        token = await issue_password_reset_grant(setup, user=user)
        claims = token_data_for_user(user)
        for _ in range(2):
            await issue_refresh_session(
                setup,
                user_id=user.id,
                token_data=claims,
            )
        await setup.commit()
        user_id = user.id

    ready = asyncio.Event()
    waiting = 0
    waiting_lock = asyncio.Lock()

    async def reset(password_hash: str) -> tuple[str, str]:
        nonlocal waiting
        async with sessions() as db:
            async with waiting_lock:
                waiting += 1
                if waiting == 2:
                    ready.set()
            await ready.wait()
            try:
                await reset_password_with_grant(
                    db,
                    token=token,
                    password_hash=password_hash,
                )
                await db.commit()
                return "changed", password_hash
            except InvalidPasswordResetError:
                await db.rollback()
                return "rejected", password_hash

    results = await asyncio.gather(reset("winner-a"), reset("winner-b"))
    assert sorted(status for status, _password_hash in results) == [
        "changed",
        "rejected",
    ]
    winner_hash = next(
        password_hash
        for status, password_hash in results
        if status == "changed"
    )

    async with sessions() as verify:
        user = await verify.get(User, user_id)
        assert user is not None
        assert user.password_hash == winner_hash
        assert user.auth_version == 1
        grants = (
            await verify.scalars(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == user_id
                )
            )
        ).all()
        sessions_for_user = (
            await verify.scalars(
                select(RefreshSession).where(RefreshSession.user_id == user_id)
            )
        ).all()
        assert len(grants) == 1
        assert grants[0].consumed_at is not None
        assert len(sessions_for_user) == 2
        assert all(row.revoked_at is not None for row in sessions_for_user)
    await engine.dispose()


async def test_password_reset_racing_refresh_leaves_no_surviving_family() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    async with sessions() as setup:
        user = User(
            email=f"reset-refresh-race-{suffix}@example.com",
            username=f"reset_refresh_race_{suffix}",
            password_hash="old-password-hash",
            active=True,
        )
        setup.add(user)
        await setup.flush()
        token = await issue_password_reset_grant(setup, user=user)
        refresh_token = await issue_refresh_session(
            setup,
            user_id=user.id,
            token_data=token_data_for_user(user),
        )
        await setup.commit()
        user_id = user.id

    refresh_payload = decode_refresh_token(refresh_token)
    assert refresh_payload is not None
    ready = asyncio.Event()
    waiting = 0
    waiting_lock = asyncio.Lock()

    async def rendezvous() -> None:
        nonlocal waiting
        async with waiting_lock:
            waiting += 1
            if waiting == 2:
                ready.set()
        await ready.wait()

    async def reset() -> None:
        async with sessions() as db:
            await rendezvous()
            await reset_password_with_grant(
                db,
                token=token,
                password_hash="new-password-hash",
            )
            await db.commit()

    async def refresh() -> str:
        async with sessions() as db:
            await rendezvous()
            locked_user = await db.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            assert locked_user is not None
            if not token_auth_version_matches(
                refresh_payload,
                locked_user.auth_version,
            ):
                await db.rollback()
                return "rejected"
            await rotate_refresh_session(
                db,
                refresh_token=refresh_token,
                payload=refresh_payload,
                user_id=user_id,
            )
            return "rotated"

    _reset_result, refresh_result = await asyncio.gather(reset(), refresh())
    assert refresh_result in {"rejected", "rotated"}

    async with sessions() as verify:
        user = await verify.get(User, user_id)
        session = await verify.get(RefreshSession, refresh_payload["sid"])
        assert user is not None
        assert session is not None
        assert user.auth_version == 1
        assert session.revoked_at is not None
    await engine.dispose()
