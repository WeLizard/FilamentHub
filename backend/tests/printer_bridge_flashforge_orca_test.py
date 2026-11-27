"""A Flashforge, Creality, Prusa, SDCP, Elegoo MQTT or Anycubic printer linked through the OrcaSlicer plugin."""

import math
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_system import PhysicalPrinterConnector
from app.models.printer_bridge_observation import MaterialSlotObservation
from app.models.user_spool import UserSpool


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
            # The printer names no spool and reads no tag; a wider claim is trimmed.
            "capabilities": [
                "read", "presence", "consumption", "write", "spool_identity", "tag_read",
            ],
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
    assert sorted(connector.capabilities) == ["consumption", "presence", "read", "write"]

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
async def test_creality_cfs_reports_through_the_orca_plugin_bridge(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    printer_id, system_id = await _system(auth_client, "creality")
    source_instance_id = "orca-desktop-instance-02"

    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
    )
    assert pairing.status_code == 200, pairing.text
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "creality",
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.3.0",
            # The plugin only reads a Creality printer; a wider claim is trimmed.
            "capabilities": ["read", "presence", "consumption", "write", "tag_read"],
        },
    )
    assert paired.status_code == 200, paired.text
    connector = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.material_system_id == system_id,
            PhysicalPrinterConnector.transport == "orca_plugin_lan",
        )
    )
    assert connector is not None and connector.provider == "creality"
    assert sorted(connector.capabilities) == ["consumption", "presence", "read"]

    snapshot = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers={"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]},
        json={
            "material_system_id": system_id,
            "provider": "creality",
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "capabilities": ["read", "presence", "consumption"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "printer": {"state": "printing", "progress_percent": 42},
            "slots": [
                {"provider_index": 0, "label": "CFS 1 slot 1", "kind": "slot", "present": True,
                 "active_feed": False, "spool_identity_known": False, "material": "PETG",
                 "color_hex": "7A92AC", "remaining_percent": 64},
                {"provider_index": 1, "label": "CFS 1 slot 2", "kind": "slot", "present": True,
                 "active_feed": True, "spool_identity_known": False, "material": "PLA",
                 "color_hex": "BA552A", "remaining_percent": 81},
                {"provider_index": 2, "label": "CFS 1 slot 3", "kind": "slot", "present": False,
                 "active_feed": False, "spool_identity_known": False},
                {"provider_index": 3, "label": "CFS 1 slot 4", "kind": "slot", "present": True,
                 "active_feed": False, "spool_identity_known": False, "material": "PLA"},
                {"provider_index": 255, "label": "External spool", "kind": "external",
                 "present": True, "active_feed": False, "spool_identity_known": False,
                 "material": "ABS", "color_hex": "000000"},
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
    assert sources == {"creality_orca"}



@pytest.mark.asyncio
async def test_anycubic_ace_reports_through_the_orca_plugin_bridge(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    printer_id, system_id = await _system(auth_client, "anycubic")
    source_instance_id = "orca-desktop-instance-03"

    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
    )
    assert pairing.status_code == 200, pairing.text
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "anycubic",
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.3.0",
            # The plugin charges the slicer's estimate and sets no slot.
            "capabilities": ["read", "presence", "consumption", "write", "tag_read"],
        },
    )
    assert paired.status_code == 200, paired.text
    connector = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.material_system_id == system_id,
            PhysicalPrinterConnector.transport == "orca_plugin_lan",
        )
    )
    assert connector is not None and connector.provider == "anycubic"
    assert sorted(connector.capabilities) == ["consumption", "presence", "read"]

    snapshot = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers={"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]},
        json={
            "material_system_id": system_id,
            "provider": "anycubic",
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "capabilities": ["read", "presence"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "printer": {"state": "printing", "progress_percent": 37},
            "slots": [
                {"provider_index": 0, "label": "ACE 1 slot 1", "kind": "slot", "present": True,
                 "active_feed": False, "spool_identity_known": False, "material": "PLA",
                 "color_hex": "FFFFFF", "remaining_percent": 80},
                {"provider_index": 1, "label": "ACE 1 slot 2", "kind": "slot", "present": False,
                 "active_feed": False, "spool_identity_known": False},
                {"provider_index": 2, "label": "ACE 1 slot 3", "kind": "slot", "present": True,
                 "active_feed": True, "spool_identity_known": False, "material": "PETG",
                 "color_hex": "1A73E8", "remaining_percent": 55},
                {"provider_index": 3, "label": "ACE 1 slot 4", "kind": "slot", "present": True,
                 "active_feed": False, "spool_identity_known": False, "material": "PLA",
                 "color_hex": "E63946", "remaining_percent": 100},
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
    assert sources == {"anycubic_orca"}

@pytest.mark.asyncio
async def test_prusa_printer_reports_its_state_and_one_spool_through_the_orca_plugin_bridge(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    printer_id, system_id = await _system(auth_client, "prusalink")
    source_instance_id = "orca-desktop-instance-03"

    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
    )
    assert pairing.status_code == 200, pairing.text
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "prusalink",
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.3.0",
            # The plugin charges the slicer's estimate and sets nothing on the printer.
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
    assert connector is not None and connector.provider == "prusalink"
    assert sorted(connector.capabilities) == ["consumption", "presence", "read"]

    snapshot = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers={"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]},
        json={
            "material_system_id": system_id,
            "provider": "prusalink",
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "capabilities": ["read", "presence"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "printer": {
                "state": "printing", "progress_percent": 42, "remaining_seconds": 3120,
                "job_name": "3DBenchy_0.4n_0.2mm_PLA_MK4S_42m.bgcode",
                "nozzle_temperature": 215.1, "bed_temperature": 60.0,
            },
            "slots": [
                {"provider_index": 0, "label": "Spool", "kind": "external", "present": True,
                 "active_feed": True, "spool_identity_known": False, "material": "PLA"},
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
    assert sources == {"prusalink_orca"}


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["sdcp", "elegoo_mqtt"])
async def test_canvas_reports_through_the_orca_plugin_bridge(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    provider: str,
) -> None:
    printer_id, system_id = await _system(auth_client, provider)
    source_instance_id = "orca-desktop-instance-03"

    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
    )
    assert pairing.status_code == 200, pairing.text
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": provider,
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.3.0",
            # The plugin charges the slicer's estimate and sets no CANVAS slot.
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
    assert connector is not None and connector.provider == provider
    assert sorted(connector.capabilities) == ["consumption", "presence", "read"]

    snapshot = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers={"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]},
        json={
            "material_system_id": system_id,
            "provider": provider,
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "capabilities": ["read", "presence"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "printer": {"state": "printing", "progress_percent": 42, "remaining_seconds": 1890},
            "slots": [
                {"provider_index": 0, "label": "CANVAS 1 slot 1", "kind": "slot", "present": True,
                 "active_feed": False, "spool_identity_known": False, "material": "PLA",
                 "color_hex": "E8E8E8"},
                {"provider_index": 1, "label": "CANVAS 1 slot 2", "kind": "slot", "present": True,
                 "active_feed": True, "spool_identity_known": False, "material": "PETG",
                 "color_hex": "1F6FB2"},
                {"provider_index": 2, "label": "CANVAS 1 slot 3", "kind": "slot", "present": False,
                 "active_feed": False, "spool_identity_known": False},
                {"provider_index": 3, "label": "CANVAS 1 slot 4", "kind": "slot", "present": True,
                 "active_feed": False, "spool_identity_known": False, "material": "PLA",
                 "color_hex": "C0392B"},
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
    assert sources == {f"{provider}_orca"}


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


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["anycubic", "sdcp", "elegoo_mqtt", "prusalink"])
async def test_a_printer_that_counts_no_filament_is_charged_the_slicer_estimate(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    provider: str,
) -> None:
    printer_id, system_id = await _system(auth_client, provider)
    source_instance_id = "orca-desktop-instance-05"
    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
    )
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": provider,
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.3.0",
            "capabilities": ["read", "presence", "consumption"],
        },
    )
    assert paired.status_code == 200, paired.text
    headers = {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]}
    printer = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    slot = printer["material_systems"][0]["slots"][0]
    spool_id = (await auth_client.post("/api/v1/spools", json={"initial_weight_g": 1000})).json()["id"]
    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slot['id']}",
        json={
            "expected_revision": slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": spool_id,
        },
    )
    assert assigned.status_code == 200, assigned.text
    route = (await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)).json()[
        "slots"
    ][0]
    now = datetime.now(timezone.utc).isoformat()
    job = {"job_id": f"{provider}:job-1", "observed_at": now, "started_at": now,
           "file_name": "bracket.gcode"}
    events = [
        {**job, "contract_version": 2, "event_id": f"{provider}:job-1:1", "segment_sequence": 1,
         "event_type": "checkpoint", "reasons": ["paused"], "items": [{
             "slot_index": route["index"], "spool_id": spool_id, "used_length_mm": 1000,
             "usage_route_proof": route["usage_route_proof"], "evidence": "route_proof",
             "consumption_kind": "estimated", "estimate_source": "slicer_gcode",
         }]},
        # A second job sliced outside this OrcaSlicer: nothing to charge, and why.
        {"job_id": f"{provider}:job-2", "observed_at": now, "started_at": now,
         "contract_version": 2, "event_id": f"{provider}:job-2:1", "segment_sequence": 1,
         "event_type": "terminal", "reasons": ["terminal"], "outcome": "completed",
         "items": [], "skipped": [{"reason": "print_not_sliced_here"}]},
    ]
    accepted = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json={
            "material_system_id": system_id, "provider": provider,
            "transport": "orca_plugin_lan", "source_instance_id": source_instance_id,
            "sequence": 1, "events": events,
        },
    )
    assert accepted.status_code == 200, accepted.text
    charged = accepted.json()["events"][0]["consumed_weight_g"]
    # One metre of 1.75 mm filament at PLA's density.
    assert charged == pytest.approx(math.pi * (1.75 / 2) ** 2 * 1.24, rel=0.01)
    spool = await db_session.scalar(select(UserSpool).where(UserSpool.id == spool_id))
    assert spool.remaining_weight_g == pytest.approx(1000 - charged)
