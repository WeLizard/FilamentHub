"""Vertical contract checks for the provider-neutral Edge bridge."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, PhysicalPrinterConnector
from app.models.printer_bridge_observation import MaterialSlotObservation
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState


@pytest.mark.asyncio
async def test_edge_sync_keeps_desired_assignment_separate_from_observation(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    created = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "Workshop Voron"},
    )
    assert created.status_code == 201
    printer_id = created.json()["id"]
    system_response = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "Happy Hare",
            "kind": "mmu",
            "provider": "happy_hare",
            "capabilities": ["read", "presence", "spool_identity"],
            "slot_count": 2,
        },
    )
    assert system_response.status_code == 201
    system = system_response.json()["material_systems"][0]
    system_id = system["id"]
    first_slot = min(system["slots"], key=lambda item: item["provider_index"])

    spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=125,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)

    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{first_slot['id']}",
        json={
            "expected_revision": first_slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": spool.id,
        },
    )
    assert assigned.status_code == 200

    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
        params={"transport": "edge_agent"},
    )
    assert pairing.status_code == 200
    source_instance_id = "edge-fixture-instance-0001"
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "happy_hare",
            "transport": "edge_agent",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.1.0-test",
            "capabilities": ["read", "presence", "spool_identity", "admin"],
        },
    )
    assert paired.status_code == 200
    headers = {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]}

    desired = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
    assert desired.status_code == 200
    assert desired.headers["etag"] == f'"{desired.json()["revision"]}"'
    desired_slot = next(item for item in desired.json()["slots"] if item["index"] == 0)
    assert desired_slot["spool"]["id"] == spool.id
    assert desired_slot["spool"]["remaining_weight_g"] == 875

    unchanged = await auth_client.get(
        "/api/v1/printer-bridge/snapshot",
        headers={**headers, "If-None-Match": desired.headers["etag"]},
    )
    assert unchanged.status_code == 304

    observed = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            "material_system_id": system_id,
            "provider": "happy_hare",
            "transport": "edge_agent",
            "source_instance_id": source_instance_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "printer": {"state": "idle"},
            "slots": [
                {
                    "provider_index": 0,
                    "present": True,
                    "active_feed": True,
                    "material": "PETG",
                    "color_hex": "3366cc",
                }
            ],
            "slot_topology_complete": True,
        },
    )
    assert observed.status_code == 200
    assert observed.json()["accepted"] is True

    assignment = await db_session.scalar(
        select(MaterialSlotAssignment).where(
            MaterialSlotAssignment.material_slot_id == first_slot["id"]
        )
    )
    assert assignment is not None
    assert assignment.spool_id == spool.id
    observation = await db_session.scalar(
        select(MaterialSlotObservation).where(
            MaterialSlotObservation.material_slot_id == first_slot["id"]
        )
    )
    assert observation is not None
    assert observation.source == "happy_hare_edge"
    assert observation.material == "PETG"
    assert observation.color_hex == "3366CC"

    heartbeat = await auth_client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers=headers,
        json={
            "material_system_id": system_id,
            "provider": "happy_hare",
            "transport": "edge_agent",
            "source_instance_id": source_instance_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "capabilities": ["read", "presence", "spool_identity", "admin"],
        },
    )
    assert heartbeat.status_code == 200

    connector = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.physical_printer_id == printer_id,
            PhysicalPrinterConnector.transport == "edge_agent",
        )
    )
    assert connector is not None
    assert connector.capabilities == ["presence", "read", "spool_identity"]
    slot = await db_session.get(MaterialSlot, first_slot["id"])
    assert slot is not None and slot.assignment_revision == 1


@pytest.mark.asyncio
async def test_edge_token_rejects_provider_or_transport_confusion(
    auth_client: AsyncClient,
) -> None:
    created = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "Edge auth boundary"},
    )
    printer_id = created.json()["id"]
    system_response = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "Happy Hare",
            "kind": "mmu",
            "provider": "happy_hare",
            "slot_count": 1,
        },
    )
    system_id = system_response.json()["material_systems"][0]["id"]
    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
        params={"transport": "edge_agent"},
    )
    source_instance_id = "edge-fixture-instance-0002"
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "happy_hare",
            "transport": "edge_agent",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.1.0-test",
        },
    )
    headers = {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]}

    confused = await auth_client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers=headers,
        json={
            "material_system_id": system_id,
            "provider": "bambu",
            "transport": "edge_agent",
            "source_instance_id": source_instance_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert confused.status_code == 401
    assert confused.json()["detail"]["code"] == "ERR_PRINTER_BRIDGE_UNAUTHORIZED"
