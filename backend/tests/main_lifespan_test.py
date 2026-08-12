"""Application lifespan regression tests."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from app import main
from app.db import session as session_module
from app.services import (
    inbound_mail_service,
    provisional_account_service,
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
        if len(started) == 3:
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
    monkeypatch.setattr(main, "_warm_pdf_renderer", fake_pdf_warmup)

    test_app = FastAPI(lifespan=main._lifespan)
    async with test_app.router.lifespan_context(test_app):
        await asyncio.wait_for(all_started.wait(), timeout=1)
        assert warm_calls == [
            ("settings", database_session),
            ("provisional-accounts", database_session),
        ]
        assert started == {"sweeper", "mail", "pdf"}

    assert stopped == {"sweeper", "mail", "pdf"}
    assert all(
        getattr(test_app.state, task_name).done()
        for task_name in (
            "provisional_account_sweeper_task",
            "inbound_mail_task",
            "pdf_warmup_task",
        )
    )
