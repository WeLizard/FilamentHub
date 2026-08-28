"""Vertical contract checks for the provider-neutral Edge bridge."""

import math
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, PhysicalPrinterConnector
from app.models.preset_usage_event import PresetUsageEvent
from app.models.print_job import PrintJob
from app.models.printer_bridge_observation import (
    MaterialSlotObservation,
    PhysicalPrinterStatusObservation,
)
from app.models.printer_bridge_receipt import PrinterBridgeReceipt
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState


@pytest.mark.asyncio
async def test_edge_usage_batches_ack_replay_order_and_atomic_ledger_application(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "Edge usage printer"},
    )
    printer_id = printer.json()["id"]
    system_response = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "Edge feed",
            "kind": "mmu",
            "provider": "happy_hare",
            "capabilities": ["read", "presence", "consumption"],
            "slot_count": 1,
        },
    )
    system = system_response.json()["material_systems"][0]
    system_id = system["id"]
    slot = system["slots"][0]
    assigned_spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    other_spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add_all([assigned_spool, other_spool])
    await db_session.commit()
    await db_session.refresh(assigned_spool)
    await db_session.refresh(other_spool)
    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slot['id']}",
        json={
            "expected_revision": slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": assigned_spool.id,
        },
    )
    assert assigned.status_code == 200

    source_instance_id = "edge-usage-instance-0001"
    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
        params={"transport": "edge_agent"},
    )
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "happy_hare",
            "transport": "edge_agent",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.1.0-test",
            "capabilities": ["read", "presence"],
        },
    )
    headers = {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]}
    context = {
        "material_system_id": system_id,
        "provider": "happy_hare",
        "transport": "edge_agent",
        "source_instance_id": source_instance_id,
    }
    observed_at = datetime.now(timezone.utc).isoformat()
    checkpoint = {
        "event_id": f"{source_instance_id}:1:1",
        "job_id": f"{source_instance_id}:job-1",
        "event_type": "checkpoint",
        "reasons": ["periodic"],
        "file_name": "edge-part.gcode",
        "observed_at": observed_at,
        "items": [
            {
                "slot_index": 0,
                "spool_id": assigned_spool.id,
                "used_length_mm": 1000,
            }
        ],
    }
    first_payload = {**context, "sequence": 1, "events": [checkpoint]}
    unsupported = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json=first_payload,
    )
    assert unsupported.status_code == 409
    assert unsupported.json()["detail"] == {
        "code": "ERR_PRINTER_BRIDGE_CAPABILITY_REQUIRED",
        "params": {"capability": "consumption"},
    }
    capability_update = await auth_client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers=headers,
        json={
            **context,
            "observed_at": observed_at,
            "capabilities": ["read", "presence", "consumption"],
        },
    )
    assert capability_update.status_code == 200

    first = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json=first_payload,
    )
    assert first.status_code == 200
    assert first.json()["ack_sequence"] == 1
    assert first.json()["deduplicated"] is False
    assert first.json()["events"][0]["deduplicated"] is False
    expected_weight = 1000.0 * math.pi * (1.75 / 2.0) ** 2 / 1000.0 * 1.24
    assert first.json()["events"][0]["consumed_weight_g"] == pytest.approx(expected_weight)

    replay = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json=first_payload,
    )
    assert replay.status_code == 200
    assert replay.json()["deduplicated"] is True

    conflicting_payload = {
        **first_payload,
        "events": [
            {
                **checkpoint,
                "items": [
                    {
                        "slot_index": 0,
                        "spool_id": assigned_spool.id,
                        "used_length_mm": 500,
                    }
                ],
            }
        ],
    }
    conflict = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json=conflicting_payload,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "ERR_PRINTER_BRIDGE_BATCH_CONFLICT"

    gap = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json={**context, "sequence": 3, "events": [{**checkpoint, "event_id": "gap-event"}]},
    )
    assert gap.status_code == 409
    assert gap.json()["detail"] == {
        "code": "ERR_PRINTER_BRIDGE_BATCH_OUT_OF_ORDER",
        "params": {"expected_sequence": 2},
    }

    duplicate_event = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json={**context, "sequence": 2, "events": [checkpoint]},
    )
    assert duplicate_event.status_code == 200
    assert duplicate_event.json()["events"][0]["deduplicated"] is True

    terminal = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json={
            **context,
            "sequence": 3,
            "events": [
                {
                    "event_id": f"{source_instance_id}:3:1",
                    "job_id": f"{source_instance_id}:job-1",
                    "event_type": "terminal",
                    "reasons": ["terminal"],
                    "outcome": "completed",
                    "file_name": "edge-part.gcode",
                    "observed_at": observed_at,
                    "items": [],
                }
            ],
        },
    )
    assert terminal.status_code == 200

    partially_invalid = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json={
            **context,
            "sequence": 4,
            "events": [
                {
                    "event_id": f"{source_instance_id}:4:1",
                    "job_id": f"{source_instance_id}:job-2",
                    "event_type": "checkpoint",
                    "items": [
                        {
                            "slot_index": 0,
                            "spool_id": assigned_spool.id,
                            "used_length_mm": 100,
                        }
                    ],
                },
                {
                    "event_id": f"{source_instance_id}:4:2",
                    "job_id": f"{source_instance_id}:job-3",
                    "event_type": "checkpoint",
                    "items": [
                        {
                            "slot_index": 0,
                            "spool_id": other_spool.id,
                            "used_length_mm": 100,
                        }
                    ],
                },
            ],
        },
    )
    assert partially_invalid.status_code == 409
    assert partially_invalid.json()["detail"]["code"] == "ERR_MATERIAL_ASSIGNMENT_CONFLICT"
    await db_session.refresh(assigned_spool)
    await db_session.refresh(other_spool)
    assert assigned_spool.used_weight_g == pytest.approx(expected_weight)
    assert other_spool.used_weight_g == 0

    valid_sequence_four = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json={
            **context,
            "sequence": 4,
            "events": [
                {
                    "event_id": f"{source_instance_id}:4:1",
                    "job_id": f"{source_instance_id}:job-2",
                    "event_type": "checkpoint",
                    "items": [
                        {
                            "slot_index": 0,
                            "spool_id": assigned_spool.id,
                            "used_length_mm": 100,
                        }
                    ],
                }
            ],
        },
    )
    assert valid_sequence_four.status_code == 200
    await db_session.refresh(assigned_spool)
    assert assigned_spool.used_weight_g == pytest.approx(expected_weight * 1.1)

    jobs = list((await db_session.execute(select(PrintJob))).scalars())
    usage_events = list((await db_session.execute(select(PresetUsageEvent))).scalars())
    receipts = list((await db_session.execute(select(PrinterBridgeReceipt))).scalars())
    assert sorted(job.status.value for job in jobs) == ["completed", "printing"]
    assert len(usage_events) == 2
    assert len([row for row in receipts if row.receipt_kind == "usage_batch"]) == 4
    assert len([row for row in receipts if row.receipt_kind == "usage_event"]) == 3


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


@pytest.mark.asyncio
async def test_edge_sequence_orders_snapshots_independently_from_clock_and_liveness(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    created = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "Edge ordering boundary"},
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
    source_instance_id = "edge-ordering-instance-0001"
    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
        params={"transport": "edge_agent"},
    )
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
    context = {
        "material_system_id": system_id,
        "provider": "happy_hare",
        "transport": "edge_agent",
        "source_instance_id": source_instance_id,
    }

    heartbeat = await auth_client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers=headers,
        json={
            **context,
            "observed_at": "2099-01-01T00:00:00+00:00",
        },
    )
    assert heartbeat.status_code == 200

    first = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            **context,
            "sequence": 2,
            "observed_at": "2020-01-01T00:00:00+00:00",
            "printer": {"state": "printing"},
        },
    )
    assert first.status_code == 200
    assert first.json()["accepted"] is True

    out_of_order = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            **context,
            "sequence": 1,
            "observed_at": "2021-01-01T00:00:00+00:00",
            "printer": {"state": "failed"},
        },
    )
    assert out_of_order.status_code == 200
    assert out_of_order.json()["accepted"] is False
    assert out_of_order.json()["stale"] is True

    clock_moved_back = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            **context,
            "sequence": 3,
            "observed_at": "2019-01-01T00:00:00+00:00",
            "printer": {"state": "paused"},
        },
    )
    assert clock_moved_back.status_code == 200
    assert clock_moved_back.json()["accepted"] is True

    connector = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.physical_printer_id == printer_id,
            PhysicalPrinterConnector.transport == "edge_agent",
        )
    )
    assert connector is not None
    await db_session.refresh(connector)
    assert connector.last_snapshot_sequence == 3
    assert connector.last_snapshot_source_instance_id == source_instance_id
    assert connector.last_observation_at.replace(tzinfo=None) == datetime(2020, 1, 1)
    assert connector.last_seen_at is not None
    assert connector.last_seen_at > connector.last_observation_at
    observation = await db_session.scalar(
        select(PhysicalPrinterStatusObservation).where(
            PhysicalPrinterStatusObservation.connector_id == connector.id
        )
    )
    assert observation is not None
    assert observation.state == "paused"
    assert observation.observed_at.replace(tzinfo=None) == datetime(2019, 1, 1)

    next_source = "edge-ordering-instance-0002"
    replacement_pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
        params={"transport": "edge_agent"},
    )
    replacement = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": replacement_pairing.json()["pairing_code"],
            "provider": "happy_hare",
            "transport": "edge_agent",
            "source_instance_id": next_source,
            "plugin_version": "0.1.0-test",
        },
    )
    restarted = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers={"X-FilamentHub-Bridge-Token": replacement.json()["bridge_token"]},
        json={
            **context,
            "source_instance_id": next_source,
            "sequence": 1,
            "observed_at": "2018-01-01T00:00:00+00:00",
            "printer": {"state": "idle"},
        },
    )
    assert restarted.status_code == 200
    assert restarted.json()["accepted"] is True
    await db_session.refresh(connector)
    assert connector.last_snapshot_sequence == 1
    assert connector.last_snapshot_source_instance_id == next_source


@pytest.mark.asyncio
async def test_legacy_edge_snapshot_uses_observation_watermark_not_heartbeat(
    auth_client: AsyncClient,
) -> None:
    created = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "Legacy Edge ordering"},
    )
    printer_id = created.json()["id"]
    system_response = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={"name": "Legacy feed", "provider": "legacy", "slot_count": 1},
    )
    system_id = system_response.json()["material_systems"][0]["id"]
    source_instance_id = "legacy-edge-instance-0001"
    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
        params={"transport": "edge_agent"},
    )
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "legacy",
            "transport": "edge_agent",
            "source_instance_id": source_instance_id,
            "plugin_version": "0.1.0-test",
        },
    )
    headers = {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]}
    context = {
        "material_system_id": system_id,
        "provider": "legacy",
        "transport": "edge_agent",
        "source_instance_id": source_instance_id,
    }
    heartbeat = await auth_client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers=headers,
        json={**context, "observed_at": "2099-01-01T00:00:00+00:00"},
    )
    assert heartbeat.status_code == 200

    first = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            **context,
            "observed_at": "2020-01-01T00:00:00+00:00",
            "printer": {"state": "idle"},
        },
    )
    older = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            **context,
            "observed_at": "2019-01-01T00:00:00+00:00",
            "printer": {"state": "failed"},
        },
    )
    assert first.json()["accepted"] is True
    assert older.json()["stale"] is True
