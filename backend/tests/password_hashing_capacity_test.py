"""Under a crowd, a password check answers plainly instead of leaving people waiting."""

import asyncio

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.core import password_hashing
from app.core.config import settings
from tests.conftest import registration_payload


@pytest.fixture(autouse=True)
def _fresh_limiter():
    """Each test starts with its own limiter, sized by that test."""
    password_hashing._limiters.clear()
    concurrency = settings.PASSWORD_HASH_CONCURRENCY
    wait = settings.PASSWORD_HASH_WAIT_SECONDS
    yield
    settings.PASSWORD_HASH_CONCURRENCY = concurrency
    settings.PASSWORD_HASH_WAIT_SECONDS = wait
    password_hashing._limiters.clear()


@pytest.mark.asyncio
async def test_a_password_is_hashed_and_recognised():
    hashed = await password_hashing.hash_password("correct horse battery")

    assert await password_hashing.check_password("correct horse battery", hashed)
    assert not await password_hashing.check_password("wrong horse", hashed)


@pytest.mark.asyncio
async def test_only_the_allowed_number_of_checks_run_at_once():
    settings.PASSWORD_HASH_CONCURRENCY = 2
    settings.PASSWORD_HASH_WAIT_SECONDS = 30
    password_hashing._limiters.clear()

    running = 0
    peak = 0

    def slow_work(_: str) -> str:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        import time

        time.sleep(0.05)
        running -= 1
        return "done"

    await asyncio.gather(*(password_hashing._in_turn(slow_work, "x") for _ in range(8)))

    assert peak <= 2


@pytest.mark.asyncio
async def test_waiting_too_long_for_a_turn_is_answered_not_endured():
    settings.PASSWORD_HASH_CONCURRENCY = 1
    settings.PASSWORD_HASH_WAIT_SECONDS = 0.05
    password_hashing._limiters.clear()

    def slow_work(_: str) -> str:
        import time

        time.sleep(0.4)
        return "done"

    async def attempt() -> object:
        try:
            return await password_hashing._in_turn(slow_work, "x")
        except HTTPException as exc:
            return exc

    results = await asyncio.gather(*(attempt() for _ in range(4)))

    refused = [item for item in results if isinstance(item, HTTPException)]
    assert refused, "перегруженный сервер должен отвечать, а не молчать"
    assert refused[0].status_code == 503
    assert refused[0].detail["code"] == "ERR_SERVER_BUSY"
    assert refused[0].headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_registration_says_it_is_busy_rather_than_hanging(client: AsyncClient):
    settings.PASSWORD_HASH_CONCURRENCY = 1
    settings.PASSWORD_HASH_WAIT_SECONDS = 0.01
    password_hashing._limiters.clear()

    limiter = password_hashing._limiter()
    await limiter.acquire()
    try:
        response = await client.post(
            "/api/v1/auth/register",
            json=registration_payload(
                email="busy@example.com", username="busy_person", password="testpassword123"
            ),
        )
    finally:
        limiter.release()

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ERR_SERVER_BUSY"
