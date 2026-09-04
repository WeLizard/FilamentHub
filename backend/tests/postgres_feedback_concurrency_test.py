"""PostgreSQL regressions for the shared feedback unread counter."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.endpoints import feedback as endpoint
from app.models.feedback import Feedback, FeedbackMessage, FeedbackStatus, FeedbackType
from app.models.user import User, UserRole
from app.schemas.feedback import FeedbackMarkRead, FeedbackMessageCreate

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="set FH_TEST_POSTGRES_URL to run PostgreSQL concurrency tests",
    ),
]


@pytest.mark.parametrize(
    ("first_action", "second_action", "expected_unread", "expected_messages"),
    [
        ("read", "reply", 1, 2),
        ("reply", "read", 1, 2),
        ("reply", "reply", 3, 3),
        ("reply", "retry", 2, 2),
        ("read_old", "read", 0, 2),
        ("read", "read_old", 0, 2),
    ],
)
async def test_concurrent_feedback_changes_preserve_unread_suffix(
    monkeypatch: pytest.MonkeyPatch,
    first_action: str,
    second_action: str,
    expected_unread: int,
    expected_messages: int,
) -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    release_first = asyncio.Event()
    tasks = []
    try:
        async with sessions() as setup:
            suffix = uuid4().hex[:12]
            owner = User(
                email=f"feedback-race-{suffix}@example.com",
                username=f"feedback_{suffix}",
                password_hash="unused",
                active=True,
            )
            admins = [
                User(
                    email=f"feedback-admin-{index}-{suffix}@example.com",
                    username=f"fb_admin_{index}_{suffix}",
                    password_hash="unused",
                    active=True,
                    role=UserRole.ADMIN,
                )
                for index in range(2)
            ]
            setup.add_all([owner, *admins])
            await setup.flush()
            initial_count = 2 if "read_old" in (first_action, second_action) else 1
            thread = Feedback(
                user_id=owner.id,
                type=FeedbackType.QUESTION,
                subject="Concurrent feedback regression",
                message="Initial question",
                status=FeedbackStatus.OPEN,
                admin_unread_count=initial_count,
            )
            setup.add(thread)
            await setup.flush()
            initial_messages = [
                FeedbackMessage(
                    feedback_id=thread.id,
                    author_user_id=owner.id,
                    author_type="user",
                    message=f"Initial question {index}",
                )
                for index in range(initial_count)
            ]
            setup.add_all(initial_messages)
            await setup.commit()
            feedback_id = thread.id
            first_boundary = initial_messages[0].id
            latest_boundary = initial_messages[-1].id

        first_loaded = asyncio.Event()
        original_load = endpoint._load_feedback_thread
        first_key = uuid4()
        second_key = first_key if second_action == "retry" else uuid4()

        async with sessions() as first_db, sessions() as second_db:
            # Keep an old identity-map snapshot alive in both sessions. Locking
            # must refresh it after another writer commits, not reuse its counter.
            first_snapshot = await original_load(first_db, feedback_id)
            second_snapshot = await original_load(second_db, feedback_id)
            first_pid = await first_db.scalar(text("SELECT pg_backend_pid()"))
            second_pid = await second_db.scalar(text("SELECT pg_backend_pid()"))

            async def pause_first_load(db: AsyncSession, thread_id: int, **kwargs) -> Feedback:
                loaded = await original_load(db, thread_id, **kwargs)
                if db is first_db and not first_loaded.is_set():
                    first_loaded.set()
                    await release_first.wait()
                return loaded

            monkeypatch.setattr(endpoint, "_load_feedback_thread", pause_first_load)

            async def change(action: str, db: AsyncSession, index: int):
                if action.startswith("read"):
                    result = await endpoint.mark_feedback_read(
                        feedback_id,
                        FeedbackMarkRead(
                            through_message_id=(
                                first_boundary if action == "read_old" else latest_boundary
                            )
                        ),
                        admins[index],
                        db,
                    )
                else:
                    result = await endpoint.add_feedback_message(
                        feedback_id,
                        FeedbackMessageCreate(
                            message="Another detail",
                            idempotency_key=first_key if index == 0 else second_key,
                        ),
                        owner,
                        db,
                    )
                # The request dependency also commits idempotent early returns.
                await db.commit()
                return result

            first_task = asyncio.create_task(change(first_action, first_db, 0))
            tasks.append(first_task)
            await asyncio.wait_for(first_loaded.wait(), timeout=10)
            second_task = asyncio.create_task(change(second_action, second_db, 1))
            tasks.append(second_task)

            async def wait_for_second_attempt() -> None:
                async with sessions() as observer:
                    while not second_task.done():
                        blocked = await observer.scalar(
                            text("SELECT :first_pid = ANY(pg_blocking_pids(:second_pid))"),
                            {"first_pid": first_pid, "second_pid": second_pid},
                        )
                        if blocked:
                            return
                        await asyncio.sleep(0.01)

            # Fixed code blocks on the row; the regression finishes the second
            # write against the first request's paused snapshot. No timing guess.
            try:
                await asyncio.wait_for(wait_for_second_attempt(), timeout=10)
            finally:
                release_first.set()
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
            assert first_snapshot.id == second_snapshot.id == feedback_id

        async with sessions() as verify:
            saved = await original_load(verify, feedback_id)
            assert saved.admin_unread_count == expected_unread
            assert len(saved.messages) == expected_messages
            assert all(message.author_type == "user" for message in saved.messages)
            assert saved.status == FeedbackStatus.OPEN
            keys = await verify.scalars(
                select(FeedbackMessage.idempotency_key).where(
                    FeedbackMessage.feedback_id == feedback_id,
                    FeedbackMessage.idempotency_key.is_not(None),
                )
            )
            reply_keys = list(keys)
            assert len(reply_keys) == len(set(reply_keys))
    finally:
        release_first.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()
