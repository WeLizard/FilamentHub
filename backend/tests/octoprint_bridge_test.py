"""Native OctoPrint Bridge pairing, snapshot and usage contract."""

import math

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.octoprint_bridge import OctoPrintBridgeEvent
from app.models.preset_usage_event import PresetUsageEvent
from app.models.print_job import PrintJob
from app.models.user_spool import UserSpool, UserSpoolState


async def _create_octoprint_system(auth_client: AsyncClient) -> tuple[int, int]:
    printer_response = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "OctoPrint Virtual Printer"},
    )
    assert printer_response.status_code == 201
    printer_id = printer_response.json()["id"]
    system_response = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "OctoPrint",
            "kind": "mmu",
            "provider": "octoprint",
            "capabilities": ["read", "write", "spool_identity", "consumption"],
            "slot_count": 2,
        },
    )
    assert system_response.status_code == 201
    return printer_id, system_response.json()["material_systems"][0]["id"]


async def _pair(auth_client: AsyncClient, printer_id: int, system_id: int) -> str:
    code_response = await auth_client.post(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}/pairing-code"
    )
    assert code_response.status_code == 200
    code = code_response.json()["pairing_code"]
    pair_response = await auth_client.post(
        "/api/v1/octoprint-bridge/pair",
        json={
            "pairing_code": code,
            "instance_id": "octoprint-test-instance",
            "plugin_version": "0.1.0",
            "octoprint_version": "1.11.8",
            "capabilities": [
                "read",
                "write",
                "presence",
                "spool_identity",
                "consumption",
                "not-a-real-capability",
            ],
        },
    )
    assert pair_response.status_code == 200
    return pair_response.json()["bridge_token"]


@pytest.mark.asyncio
async def test_bridge_pair_snapshot_usage_replay_and_revoke(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user,
) -> None:
    printer_id, system_id = await _create_octoprint_system(auth_client)
    token = await _pair(auth_client, printer_id, system_id)

    status_response = await auth_client.get(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}"
    )
    assert status_response.status_code == 200
    assert status_response.json()["paired"] is True
    assert status_response.json()["instance_id"] == "octoprint-test-instance"
    paired_last_seen_at = status_response.json()["last_seen_at"]

    brand = Brand(name="Bridge Brand", slug="bridge-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Bridge PLA Red",
        slug="bridge-pla-red",
        material_type="PLA",
        color_name="Red",
        color_hex="#FF0000",
        density=1.24,
        diameter=1.75,
    )
    db_session.add(filament)
    await db_session.flush()
    spool = UserSpool(
        user_id=auth_user.id,
        filament_id=filament.id,
        initial_weight_g=1000.0,
        used_weight_g=0.0,
        state=UserSpoolState.shelf,
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)

    printer_response = await auth_client.get(f"/api/v1/physical-printers/{printer_id}")
    slot_id = printer_response.json()["material_systems"][0]["slots"][0]["id"]
    assignment_response = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slot_id}",
        json={"spool_id": spool.id},
    )
    assert assignment_response.status_code == 200

    bridge_headers = {"X-FilamentHub-Bridge-Token": token}
    snapshot_response = await auth_client.get(
        "/api/v1/octoprint-bridge/snapshot", headers=bridge_headers
    )
    assert snapshot_response.status_code == 200
    assert snapshot_response.headers["etag"]
    snapshot = snapshot_response.json()
    assert snapshot["material_system_id"] == system_id
    assert snapshot["slots"][0]["spool"] == {
        "id": spool.id,
        "filament_id": filament.id,
        "name": "Bridge PLA Red",
        "brand": "Bridge Brand",
        "material_type": "PLA",
        "color_hex": "#FF0000",
        "remaining_weight_g": 1000.0,
        "initial_weight_g": 1000.0,
        "density_g_cm3": 1.24,
        "diameter_mm": 1.75,
    }
    unchanged = await auth_client.get(
        "/api/v1/octoprint-bridge/snapshot",
        headers={**bridge_headers, "If-None-Match": snapshot_response.headers["etag"]},
    )
    assert unchanged.status_code == 304
    status_after_snapshot = await auth_client.get(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}"
    )
    assert status_after_snapshot.status_code == 200
    assert status_after_snapshot.json()["last_seen_at"] == paired_last_seen_at

    heartbeat_response = await auth_client.post(
        "/api/v1/octoprint-bridge/heartbeat",
        headers=bridge_headers,
        json={
            "instance_id": "octoprint-test-instance",
            "plugin_version": "0.1.0",
            "octoprint_version": "1.11.8",
            "capabilities": ["read", "write", "presence", "consumption"],
            "active_slot_index": 0,
        },
    )
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["active_slot_index"] == 0

    usage_payload = {
        "event_id": "print-job-1-terminal",
        "job_id": "print-job-1",
        "outcome": "completed",
        "file_name": "bridge-test.gcode",
        "duration_s": 120.0,
        "items": [
            {
                "slot_index": 0,
                "spool_id": spool.id,
                "used_length_mm": 1000.0,
            }
        ],
    }
    usage_response = await auth_client.post(
        "/api/v1/octoprint-bridge/usage",
        headers=bridge_headers,
        json=usage_payload,
    )
    assert usage_response.status_code == 200
    expected_weight = 1000.0 * math.pi * (1.75 / 2.0) ** 2 / 1000.0 * 1.24
    assert usage_response.json()["consumed_weight_g"] == pytest.approx(expected_weight)
    assert usage_response.json()["deduplicated"] is False

    replay_response = await auth_client.post(
        "/api/v1/octoprint-bridge/usage",
        headers=bridge_headers,
        json=usage_payload,
    )
    assert replay_response.status_code == 200
    assert replay_response.json()["deduplicated"] is True
    assert replay_response.json()["consumed_weight_g"] == pytest.approx(expected_weight)

    conflict_payload = dict(usage_payload)
    conflict_payload["items"] = [{"slot_index": 0, "spool_id": spool.id, "used_length_mm": 500.0}]
    conflict_response = await auth_client.post(
        "/api/v1/octoprint-bridge/usage",
        headers=bridge_headers,
        json=conflict_payload,
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"]["code"] == ("ERR_OCTOPRINT_BRIDGE_EVENT_CONFLICT")

    await db_session.refresh(spool)
    assert spool.used_weight_g == pytest.approx(expected_weight)
    events = list((await db_session.execute(select(OctoPrintBridgeEvent))).scalars())
    assert len(events) == 1
    print_jobs = list((await db_session.execute(select(PrintJob))).scalars())
    assert len(print_jobs) == 1
    assert print_jobs[0].status.value == "completed"
    usage_events = list((await db_session.execute(select(PresetUsageEvent))).scalars())
    assert len(usage_events) == 1
    assert usage_events[0].print_job_id == print_jobs[0].id

    # A provider may retry the same physical job under a new transport event id.
    # Job identity, not only the request id, must prevent a second consumption.
    second_transport_event = {**usage_payload, "event_id": "print-job-1-terminal-retry"}
    job_replay = await auth_client.post(
        "/api/v1/octoprint-bridge/usage",
        headers=bridge_headers,
        json=second_transport_event,
    )
    assert job_replay.status_code == 200
    assert job_replay.json()["deduplicated"] is True
    await db_session.refresh(spool)
    assert spool.used_weight_g == pytest.approx(expected_weight)
    usage_events = list((await db_session.execute(select(PresetUsageEvent))).scalars())
    assert len(usage_events) == 1

    revoke_response = await auth_client.delete(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}"
    )
    assert revoke_response.status_code == 204
    rejected = await auth_client.get("/api/v1/octoprint-bridge/snapshot", headers=bridge_headers)
    assert rejected.status_code == 401


@pytest.mark.asyncio
async def test_pairing_code_is_single_use(
    auth_client: AsyncClient,
) -> None:
    printer_id, system_id = await _create_octoprint_system(auth_client)
    response = await auth_client.post(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}/pairing-code"
    )
    code = response.json()["pairing_code"]
    payload = {
        "pairing_code": code,
        "instance_id": "first-instance",
        "plugin_version": "0.1.0",
        "octoprint_version": "1.11.8",
        "capabilities": ["read"],
    }
    first = await auth_client.post("/api/v1/octoprint-bridge/pair", json=payload)
    assert first.status_code == 200
    second = await auth_client.post("/api/v1/octoprint-bridge/pair", json=payload)
    assert second.status_code == 401
    assert second.json()["detail"]["code"] == "ERR_OCTOPRINT_BRIDGE_PAIRING_INVALID"


@pytest.mark.asyncio
async def test_issuing_a_new_pairing_code_keeps_the_live_bridge_connected(
    auth_client: AsyncClient,
) -> None:
    printer_id, system_id = await _create_octoprint_system(auth_client)
    live_token = await _pair(auth_client, printer_id, system_id)

    code_response = await auth_client.post(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}/pairing-code"
    )
    assert code_response.status_code == 200
    still_connected = await auth_client.get(
        "/api/v1/octoprint-bridge/snapshot",
        headers={"X-FilamentHub-Bridge-Token": live_token},
    )

    assert still_connected.status_code == 200
