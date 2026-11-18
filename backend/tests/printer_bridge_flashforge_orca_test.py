"""A Flashforge printer linked through the OrcaSlicer plugin's paired bridge."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_system import PhysicalPrinterConnector
from app.models.printer_bridge_observation import MaterialSlotObservation


async def _system(auth_client: AsyncClient, provider: str) -> tuple[int, int]:
    created = await auth_client.post("/api/v1/physical-printers", json={"name": provider})
    printer_id = created.json()["id"]
    response = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "Feed",
            "provider": provider,
            "kind": "mmu",
            "slots": [{"provider_index": index, "kind": "slot"} for index in range(4)],
        },
    )
    assert response.status_code in {200, 201}, response.text
    return printer_id, response.json()["material_systems"][0]["id"]


@pytest.mark.asyncio
async def test_flashforge_station_reports_through_the_orca_plugin_bridge(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    printer_id, system_id = await _system(auth_client, "flashforge")
    source_instance_id = "orca-desktop-instance-01"

    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
    )
    assert pairing.status_code == 200, pairing.text
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "flashforge",
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.2.10",
            # The printer API proves no usage; a wider claim is trimmed.
            "capabilities": ["read", "presence", "consumption", "write"],
        },
    )
    assert paired.status_code == 200, paired.text
    connector = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.material_system_id == system_id,
            PhysicalPrinterConnector.transport == "orca_plugin_lan",
        )
    )
    assert connector is not None and connector.provider == "flashforge"
    assert sorted(connector.capabilities) == ["presence", "read"]

    snapshot = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers={"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]},
        json={
            "material_system_id": system_id,
            "provider": "flashforge",
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "capabilities": ["read", "presence"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "printer": {"state": "printing", "progress_percent": 42},
            "slots": [
                {"provider_index": 0, "label": "Slot 1", "kind": "slot", "present": True,
                 "spool_identity_known": False, "material": "PLA", "color_hex": "4CAAF8"},
                {"provider_index": 1, "label": "Slot 2", "kind": "slot", "present": False,
                 "spool_identity_known": False},
                {"provider_index": 2, "label": "Slot 3", "kind": "slot", "present": False,
                 "spool_identity_known": False},
                {"provider_index": 3, "label": "Slot 4", "kind": "slot", "present": None,
                 "spool_identity_known": False},
            ],
            "slot_topology_complete": True,
        },
    )
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["accepted"] is True
    sources = set(await db_session.scalars(
        select(MaterialSlotObservation.source).where(
            MaterialSlotObservation.connector_id == connector.id
        )
    ))
    # Shown to the person as data that came through OrcaSlicer, not Moonraker.
    assert sources == {"flashforge_orca"}


@pytest.mark.asyncio
async def test_orca_bridge_pairing_stays_closed_to_providers_without_that_path(
    auth_client: AsyncClient,
) -> None:
    printer_id, system_id = await _system(auth_client, "happy_hare")

    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
    )

    assert pairing.status_code == 409
    assert pairing.json()["detail"]["code"] == "ERR_PRINTER_BRIDGE_WRONG_PROVIDER"
