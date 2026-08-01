"""Under a crowd, heavy work answers plainly instead of leaving people waiting."""

import asyncio
import time

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.core import password_hashing
from app.core.capacity import Gate
from tests.conftest import registration_payload


def _slow_work(_: str) -> str:
    time.sleep(0.05)
    return "done"


@pytest.mark.asyncio
async def test_a_password_is_hashed_and_recognised():
    hashed = await password_hashing.hash_password("correct horse battery")

    assert await password_hashing.check_password("correct horse battery", hashed)
    assert not await password_hashing.check_password("wrong horse", hashed)


@pytest.mark.asyncio
async def test_only_the_allowed_number_runs_at_once():
    gate = Gate("test", slots=2, wait_seconds=30)
    running = 0
    peak = 0

    def watched(_: str) -> str:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        time.sleep(0.05)
        running -= 1
        return "done"

    await asyncio.gather(*(gate.run(watched, "x") for _ in range(8)))

    assert peak <= 2


@pytest.mark.asyncio
async def test_waiting_too_long_for_a_turn_is_answered_not_endured():
    gate = Gate("test", slots=1, wait_seconds=0.05)

    def very_slow(_: str) -> str:
        time.sleep(0.4)
        return "done"

    async def attempt() -> object:
        try:
            return await gate.run(very_slow, "x")
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
    gate = password_hashing._gate
    slots, wait = gate.slots, gate.wait_seconds
    gate.slots, gate.wait_seconds = 1, 0.01
    gate.reset()

    limiter = gate._limiter()
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
        gate.slots, gate.wait_seconds = slots, wait
        gate.reset()

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ERR_SERVER_BUSY"
