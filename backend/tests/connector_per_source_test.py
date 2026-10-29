"""Two workstations paired to one printer keep separate, simultaneously valid links."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


async def _pair(client: AsyncClient, printer_id: int, system_id: int, source: str) -> str:
    code = await client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code"
    )
    paired = await client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": code.json()["pairing_code"],
            "provider": "bambu",
            "transport": "orca_plugin_lan",
            "source_instance_id": source,
            "plugin_version": "0.1.0-test",
            "capabilities": ["read", "presence"],
        },
    )
    assert paired.status_code == 200, paired.text
    return paired.json()["bridge_token"]


async def _beat(client: AsyncClient, token: str, system_id: int, source: str, **extra):
    return await client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers={"X-FilamentHub-Bridge-Token": token},
        json={
            "material_system_id": system_id,
            "provider": "bambu",
            "transport": "orca_plugin_lan",
            "source_instance_id": source,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            **extra,
        },
    )


@pytest.mark.asyncio
async def test_pairing_a_second_workstation_does_not_evict_the_first(
    auth_client: AsyncClient,
) -> None:
    printer_id = (await auth_client.post("/api/v1/physical-printers", json={"name": "P2S"})).json()["id"]
    system_id = (
        await auth_client.post(
            f"/api/v1/physical-printers/{printer_id}/material-systems",
            json={"name": "AMS", "kind": "mmu", "provider": "bambu",
                  "capabilities": ["read", "presence"]},
        )
    ).json()["material_systems"][0]["id"]

    first = await _pair(auth_client, printer_id, system_id, "workstation-aaaaaaaaaaaa")
    second = await _pair(auth_client, printer_id, system_id, "workstation-bbbbbbbbbbbb")
    assert first != second

    for token, source in ((first, "workstation-aaaaaaaaaaaa"), (second, "workstation-bbbbbbbbbbbb")):
        heartbeat = await _beat(auth_client, token, system_id, source)
        assert heartbeat.status_code == 200, heartbeat.text

    body = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    sources = sorted(c["source_instance_id"] for c in body["connectors"])
    assert sources == ["workstation-aaaaaaaaaaaa", "workstation-bbbbbbbbbbbb"]
    assert len([c for c in body["contact_channels"] if c["kind"] == "connector"]) == 2

    # The same workstation pairing again replaces its own token, not a new row.
    again = await _pair(auth_client, printer_id, system_id, "workstation-bbbbbbbbbbbb")
    body = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    assert len(body["connectors"]) == 2
    stale = await _beat(auth_client, second, system_id, "workstation-bbbbbbbbbbbb")
    assert stale.status_code == 401
    assert (await _beat(auth_client, first, system_id, "workstation-aaaaaaaaaaaa")).status_code == 200
    assert again != second


@pytest.mark.asyncio
async def test_one_connector_per_system_holds_usage_authority(
    auth_client: AsyncClient, db_session
) -> None:
    from datetime import timedelta

    from sqlalchemy import select

    from app.models.material_system import PhysicalPrinterConnector
    from app.services.printer_usage_route_service import hold_usage_authority

    printer_id = (await auth_client.post("/api/v1/physical-printers", json={"name": "P2S"})).json()["id"]
    system_id = (
        await auth_client.post(
            f"/api/v1/physical-printers/{printer_id}/material-systems",
            json={"name": "AMS", "kind": "mmu", "provider": "bambu",
                  "capabilities": ["read", "presence"]},
        )
    ).json()["material_systems"][0]["id"]
    await _pair(auth_client, printer_id, system_id, "workstation-aaaaaaaaaaaa")
    await _pair(auth_client, printer_id, system_id, "workstation-bbbbbbbbbbbb")
    first, second = (
        await db_session.scalars(
            select(PhysicalPrinterConnector)
            .where(PhysicalPrinterConnector.physical_printer_id == printer_id)
            .order_by(PhysicalPrinterConnector.id)
        )
    ).all()
    first.last_seen_at = second.last_seen_at = datetime.now(timezone.utc)

    assert await hold_usage_authority(db_session, first) is True
    assert await hold_usage_authority(db_session, second) is False  # first is fresh
    assert await hold_usage_authority(db_session, first) is True

    first.last_seen_at = datetime.now(timezone.utc) - timedelta(hours=1)
    assert await hold_usage_authority(db_session, second) is True  # first went silent
    await db_session.refresh(first)
    assert first.usage_authority is False and second.usage_authority is True


@pytest.mark.asyncio
async def test_heartbeat_with_an_unreachable_printer_is_a_live_helper_not_a_dead_link(
    auth_client: AsyncClient,
) -> None:
    printer_id = (await auth_client.post("/api/v1/physical-printers", json={"name": "P2S"})).json()["id"]
    system_id = (
        await auth_client.post(
            f"/api/v1/physical-printers/{printer_id}/material-systems",
            json={"name": "AMS", "kind": "mmu", "provider": "bambu",
                  "capabilities": ["read", "presence"]},
        )
    ).json()["material_systems"][0]["id"]
    source = "workstation-aaaaaaaaaaaa"
    token = await _pair(auth_client, printer_id, system_id, source)

    beat = await _beat(
        auth_client, token, system_id, source, provider_reachable=False, contact_interval_s=60
    )
    assert beat.status_code == 200, beat.text
    body = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    channel = next(c for c in body["contact_channels"] if c["kind"] == "connector")
    assert channel["state"] == "executor_only"
