"""A workstation key reports and observes; it cannot edit, and it can be revoked."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_workstation_key_is_scoped_to_observation_and_revocable(
    auth_client: AsyncClient, client: AsyncClient
) -> None:
    created = await auth_client.post("/api/v1/workstation-keys", json={"name": "Office PC"})
    assert created.status_code == 201
    key, key_id = created.json()["key"], created.json()["id"]
    assert key.startswith("fhw_")
    listed = (await auth_client.get("/api/v1/workstation-keys")).json()
    assert [item["name"] for item in listed] == ["Office PC"]
    assert "key" not in listed[0]

    headers = {"Authorization": f"Bearer {key}"}
    # Observation: allowed.
    context = await client.get(
        "/api/v1/orcaslicer/preset-slot-sync/plugin-context",
        params={"source_instance_id": "workstation-aaaaaaaaaaaa"},
        headers=headers,
    )
    assert context.status_code == 200, context.text
    # Preset writes and ordinary account APIs: refused.
    write = await client.post("/api/v1/orcaslicer/slices", headers=headers, json={})
    assert write.status_code == 403
    account = await client.get("/api/v1/auth/me", headers=headers)
    assert account.status_code == 401
    # A workstation cannot mint or revoke keys.
    assert (await client.post("/api/v1/workstation-keys", headers=headers, json={"name": "x"})).status_code == 401

    revoked = await auth_client.delete(f"/api/v1/workstation-keys/{key_id}")
    assert revoked.status_code == 204
    after = await client.get(
        "/api/v1/orcaslicer/preset-slot-sync/plugin-context",
        params={"source_instance_id": "workstation-aaaaaaaaaaaa"},
        headers=headers,
    )
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_workstation_keys_are_limited_per_account(auth_client: AsyncClient) -> None:
    for index in range(10):
        assert (
            await auth_client.post("/api/v1/workstation-keys", json={"name": f"pc-{index}"})
        ).status_code == 201
    over = await auth_client.post("/api/v1/workstation-keys", json={"name": "one-more"})
    assert over.status_code == 409
    assert over.json()["detail"]["code"] == "ERR_WORKSTATION_KEY_LIMIT"
