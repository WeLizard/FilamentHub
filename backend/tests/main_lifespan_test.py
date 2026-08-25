"""Application lifespan regression tests."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from app import main
from app.db import session as session_module
from app.services import (
    field_key_guard,
    inbound_mail_service,
    provisional_account_service,
    refresh_session_service,
    subscription_service,
)


@pytest.mark.asyncio
async def test_lifespan_warms_state_and_stops_background_tasks(monkeypatch) -> None:
    database_session = object()
    warm_calls: list[tuple[str, object]] = []
    started: set[str] = set()
    stopped: set[str] = set()
    all_started = asyncio.Event()

    @asynccontextmanager
    async def fake_session_factory():
        yield database_session

    async def record_warm_call(name: str, db: object) -> None:
        warm_calls.append((name, db))

    async def run_until_cancelled(name: str) -> None:
        started.add(name)
        if len(started) == 4:
            all_started.set()
        try:
            await asyncio.Future()
        finally:
            stopped.add(name)

    async def fake_sweeper(session_factory) -> None:
        assert session_factory is fake_session_factory
        await run_until_cancelled("sweeper")

    async def fake_mail_poller(session_factory) -> None:
        assert session_factory is fake_session_factory
        await run_until_cancelled("mail")

    async def fake_auth_sweeper(session_factory) -> None:
        assert session_factory is fake_session_factory
        await run_until_cancelled("auth")

    async def fake_pdf_warmup() -> None:
        await run_until_cancelled("pdf")

    monkeypatch.setattr(session_module, "AsyncSessionLocal", fake_session_factory)
    monkeypatch.setattr(
        subscription_service,
        "refresh_settings_cache",
        lambda db: record_warm_call("settings", db),
    )
    monkeypatch.setattr(
        provisional_account_service,
        "sweep_abandoned_provisional_accounts",
        lambda db: record_warm_call("provisional-accounts", db),
    )
    monkeypatch.setattr(
        provisional_account_service,
        "run_provisional_account_sweeper",
        fake_sweeper,
    )
    monkeypatch.setattr(inbound_mail_service, "run_inbound_mail_poller", fake_mail_poller)
    monkeypatch.setattr(refresh_session_service, "run_auth_state_sweeper", fake_auth_sweeper)
    monkeypatch.setattr(main, "_warm_pdf_renderer", fake_pdf_warmup)
    # Checked against a real database at startup; this test drives the lifespan with a
    # stand-in session and is about which tasks start and stop.
    monkeypatch.setattr(
        field_key_guard,
        "verify_field_encryption_key",
        lambda db: record_warm_call("field-key", db),
    )

    test_app = FastAPI(lifespan=main._lifespan)
    async with test_app.router.lifespan_context(test_app):
        await asyncio.wait_for(all_started.wait(), timeout=1)
        assert warm_calls == [
            ("field-key", database_session),
            ("settings", database_session),
            ("provisional-accounts", database_session),
        ]
        assert started == {"sweeper", "auth", "mail", "pdf"}

    assert stopped == {"sweeper", "auth", "mail", "pdf"}
    assert all(
        getattr(test_app.state, task_name).done()
        for task_name in (
            "provisional_account_sweeper_task",
            "auth_state_sweeper_task",
            "inbound_mail_task",
            "pdf_warmup_task",
        )
    )


@pytest.mark.asyncio
async def test_an_unreachable_database_does_not_block_startup(monkeypatch) -> None:
    """A database still coming up is not a wrong key.

    The encryption check refuses to serve requests under a key that cannot read the
    data, and that has to stay strict. But treating a connection failure the same way
    turns an ordinary restart order — application before database — into an outage.
    """
    from sqlalchemy.exc import OperationalError

    started: set[str] = set()
    all_started = asyncio.Event()

    @asynccontextmanager
    async def fake_session_factory():
        yield object()

    async def run_until_cancelled(name: str) -> None:
        started.add(name)
        if len(started) == 4:
            all_started.set()
        await asyncio.Future()

    async def unreachable(db: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(session_module, "AsyncSessionLocal", fake_session_factory)
    monkeypatch.setattr(field_key_guard, "verify_field_encryption_key", unreachable)
    monkeypatch.setattr(
        subscription_service, "refresh_settings_cache", lambda db: asyncio.sleep(0)
    )
    monkeypatch.setattr(
        provisional_account_service,
        "sweep_abandoned_provisional_accounts",
        lambda db: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        provisional_account_service,
        "run_provisional_account_sweeper",
        lambda factory: run_until_cancelled("sweeper"),
    )
    monkeypatch.setattr(
        inbound_mail_service,
        "run_inbound_mail_poller",
        lambda factory: run_until_cancelled("mail"),
    )
    monkeypatch.setattr(
        refresh_session_service,
        "run_auth_state_sweeper",
        lambda factory: run_until_cancelled("auth"),
    )
    monkeypatch.setattr(main, "_warm_pdf_renderer", lambda: run_until_cancelled("pdf"))

    test_app = FastAPI(lifespan=main._lifespan)
    async with test_app.router.lifespan_context(test_app):
        await asyncio.wait_for(all_started.wait(), timeout=1)


@pytest.mark.asyncio
async def test_a_key_mismatch_still_stops_startup(monkeypatch) -> None:
    """The one failure that must not be tolerated."""
    from app.services.field_key_guard import FieldKeyMismatchError

    @asynccontextmanager
    async def fake_session_factory():
        yield object()

    async def mismatched(db: object) -> None:
        raise FieldKeyMismatchError("wrong key")

    monkeypatch.setattr(session_module, "AsyncSessionLocal", fake_session_factory)
    monkeypatch.setattr(field_key_guard, "verify_field_encryption_key", mismatched)

    test_app = FastAPI(lifespan=main._lifespan)
    with pytest.raises(FieldKeyMismatchError):
        async with test_app.router.lifespan_context(test_app):
            pass
