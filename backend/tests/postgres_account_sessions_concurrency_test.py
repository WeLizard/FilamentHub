"""Session revocation must win against concurrent refresh without touching the caller."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.core.security import create_refresh_token, decode_refresh_token
from app.models.audit_event import AuditEvent
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.services.account_auth_service import lock_user_auth_state, token_data_for_user
from app.services.account_session_service import (
    revoke_account_session,
    revoke_other_account_sessions,
)
from app.services.refresh_session_service import (
    InvalidRefreshSessionError,
    issue_refresh_session,
    rotate_refresh_session,
)

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL, reason="set FH_TEST_POSTGRES_URL for PostgreSQL concurrency"
    ),
]


def session_request(sid):
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
    request.state.account_session_id = sid
    return request


async def prepare(sessions):
    suffix = uuid4().hex[:12]
    async with sessions() as db:
        user = User(
            email=f"session-race-{suffix}@example.invalid",
            username=f"session_race_{suffix}",
            active=True,
        )
        db.add(user)
        await db.flush()
        claims = token_data_for_user(user)
        first = await issue_refresh_session(db, user_id=user.id, token_data=claims)
        second = await issue_refresh_session(db, user_id=user.id, token_data=claims)
        await db.commit()
        return user.id, first, second, claims


async def test_concurrent_selected_revoke_records_exactly_one_transition():
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        user_id, first, second, _ = await prepare(sessions)
        first_sid, second_sid = (
            decode_refresh_token(first)["sid"],
            decode_refresh_token(second)["sid"],
        )

        async def revoke():
            async with sessions() as db:
                result = await revoke_account_session(
                    db, request=session_request(first_sid), user_id=user_id, session_id=second_sid
                )
                return result.revoked

        results = await asyncio.wait_for(asyncio.gather(revoke(), revoke()), 15)
        assert sorted(results) == [False, True]
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.actor_user_id == user_id)
                )
                == 1
            )
            assert (await db.get(RefreshSession, first_sid)).revoked_at is None
            assert (await db.get(RefreshSession, second_sid)).revoked_at is not None
    finally:
        await engine.dispose()


@pytest.mark.parametrize("first_operation", ["refresh", "revoke"])
async def test_selected_revoke_racing_refresh_never_revives_target_family(first_operation):
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    first_locked, follower_started = asyncio.Event(), asyncio.Event()
    try:
        user_id, caller_refresh, target_refresh, _ = await prepare(sessions)
        caller_sid = decode_refresh_token(caller_refresh)["sid"]
        target_sid = decode_refresh_token(target_refresh)["sid"]

        async def acquire_account(db, operation):
            if operation == first_operation:
                await lock_user_auth_state(db, user_id)
                first_locked.set()
                await follower_started.wait()
            else:
                await first_locked.wait()
                follower_started.set()
                await lock_user_auth_state(db, user_id)

        async def refresh():
            async with sessions() as db:
                await acquire_account(db, "refresh")
                try:
                    return await rotate_refresh_session(
                        db,
                        refresh_token=target_refresh,
                        payload=decode_refresh_token(target_refresh),
                        user_id=user_id,
                    )
                except InvalidRefreshSessionError:
                    await db.rollback()
                    return None

        async def revoke():
            async with sessions() as db:
                await acquire_account(db, "revoke")
                return await revoke_account_session(
                    db,
                    request=session_request(caller_sid),
                    user_id=user_id,
                    session_id=target_sid,
                )

        successor, revoked = await asyncio.wait_for(asyncio.gather(refresh(), revoke()), 15)
        assert revoked.revoked
        assert (successor is not None) == (first_operation == "refresh")
        async with sessions() as db:
            target = await db.get(RefreshSession, target_sid)
            assert target.revoked_at is not None
            assert (await db.get(RefreshSession, caller_sid)).revoked_at is None
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.actor_user_id == user_id,
                        AuditEvent.reason == "session_revoke",
                    )
                )
                == 1
            )

        # Neither the original refresh nor an already-returned successor can
        # undo the winning revoke after both concurrent transactions finish.
        for token in {target_refresh, successor} - {None}:
            async with sessions() as db:
                await lock_user_auth_state(db, user_id)
                with pytest.raises(InvalidRefreshSessionError):
                    await rotate_refresh_session(
                        db,
                        refresh_token=token,
                        payload=decode_refresh_token(token),
                        user_id=user_id,
                    )
                await db.rollback()
        async with sessions() as db:
            await lock_user_auth_state(db, user_id)
            current = await rotate_refresh_session(
                db,
                refresh_token=caller_refresh,
                payload=decode_refresh_token(caller_refresh),
                user_id=user_id,
            )
            assert decode_refresh_token(current)["sid"] == caller_sid
            assert (await db.get(RefreshSession, target_sid)).revoked_at is not None
    finally:
        await engine.dispose()


@pytest.mark.parametrize("refresh_kind", ["bound", "legacy"])
async def test_revoke_others_racing_refresh_leaves_only_callers_family_live(refresh_kind):
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        user_id, first, second, claims = await prepare(sessions)
        first_sid = decode_refresh_token(first)["sid"]
        refreshed_token = second if refresh_kind == "bound" else create_refresh_token(claims)

        async def refresh():
            async with sessions() as db:
                user = await lock_user_auth_state(db, user_id)
                try:
                    return await rotate_refresh_session(
                        db,
                        refresh_token=refreshed_token,
                        payload=decode_refresh_token(refreshed_token),
                        user_id=user_id,
                        legacy_disabled=user.legacy_refresh_disabled_at is not None,
                    )
                except InvalidRefreshSessionError:
                    await db.rollback()
                    return None

        async def revoke():
            async with sessions() as db:
                return await revoke_other_account_sessions(
                    db, request=session_request(first_sid), user_id=user_id
                )

        await asyncio.wait_for(asyncio.gather(refresh(), revoke()), 15)
        async with sessions() as db:
            live = (
                await db.scalars(
                    select(RefreshSession.id).where(
                        RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None)
                    )
                )
            ).all()
            assert live == [first_sid]
            user = await lock_user_auth_state(db, user_id)
            assert user.legacy_refresh_disabled_at is not None and user.auth_version == 0
            current = await rotate_refresh_session(
                db, refresh_token=first, payload=decode_refresh_token(first), user_id=user_id
            )
            assert decode_refresh_token(current)["sid"] == first_sid
    finally:
        await engine.dispose()
