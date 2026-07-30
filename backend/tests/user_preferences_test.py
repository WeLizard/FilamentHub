"""Account-wide preferences must be available independently of Pro access."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_currency_preference_round_trip_for_regular_user(
    auth_client: AsyncClient,
):
    initial = await auth_client.get("/api/v1/auth/me/preferences")
    assert initial.status_code == 200
    assert initial.json() == {"currency": None}

    updated = await auth_client.patch(
        "/api/v1/auth/me/preferences",
        json={"currency": "EUR"},
    )
    assert updated.status_code == 200
    assert updated.json() == {"currency": "EUR"}

    persisted = await auth_client.get("/api/v1/auth/me/preferences")
    assert persisted.status_code == 200
    assert persisted.json() == {"currency": "EUR"}


@pytest.mark.asyncio
async def test_currency_preference_rejects_non_iso_code(
    auth_client: AsyncClient,
):
    response = await auth_client.patch(
        "/api/v1/auth/me/preferences",
        json={"currency": "€"},
    )
    assert response.status_code == 422
