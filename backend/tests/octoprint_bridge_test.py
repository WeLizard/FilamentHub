"""Native OctoPrint Bridge pairing, snapshot and usage contract."""

import math

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.octoprint_bridge import OctoPrintBridgeEvent
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_usage_event import PresetUsageEvent
from app.models.print_job import PrintJob
from app.models.user import User
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
            "capabilities": [
                "read",
                "write",
                "presence",
                "spool_identity",
                "consumption",
            ],
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
    preset = Preset(
        filament_id=filament.id,
        user_id=auth_user.id,
        name="Bridge PLA profile",
        extruder_temp=210,
        bed_temp=60,
        active=True,
        is_official=False,
        is_weighted=False,
        moderation_status=PresetModerationStatus.APPROVED,
    )
    spool = UserSpool(
        user_id=auth_user.id,
        filament_id=filament.id,
        initial_weight_g=1000.0,
        used_weight_g=0.0,
        state=UserSpoolState.shelf,
    )
    db_session.add_all([preset, spool])
    await db_session.commit()
    await db_session.refresh(spool)

    printer_response = await auth_client.get(f"/api/v1/physical-printers/{printer_id}")
    slot = printer_response.json()["material_systems"][0]["slots"][0]
    slot_id = slot["id"]
    assignment_response = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slot_id}",
        json={
            "expected_revision": slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": spool.id,
            "preset_id": preset.id,
        },
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
    assert snapshot["slots"][0]["material_slot_id"] == slot_id
    assert snapshot["slots"][0]["assignment_revision"] == 1
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
            "plugin_version": "0.1.1",
            "octoprint_version": "1.11.8",
            "capabilities": ["read", "write", "spool_identity", "consumption"],
            "active_slot_index": 0,
            "routing_mode": "manual",
            "tool_slot_map": [],
            "routing_revision": 0,
        },
    )
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["active_slot_index"] == 0
    assert heartbeat_response.json()["routing"] == {
        "mode": "manual",
        "tool_slot_map": [],
        "revision": 1,
        "applied_revision": 1,
    }
    printer_after_heartbeat = await auth_client.get(f"/api/v1/physical-printers/{printer_id}")
    assert printer_after_heartbeat.status_code == 200
    expected_capabilities = ["consumption", "read", "spool_identity", "write"]
    assert (
        printer_after_heartbeat.json()["material_systems"][0]["capabilities"]
        == expected_capabilities
    )
    assert printer_after_heartbeat.json()["connectors"][0]["capabilities"] == expected_capabilities

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
    assert usage_events[0].preset_id == preset.id

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
async def test_bridge_spool_picker_and_assignment_use_canonical_desired_state(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user,
) -> None:
    printer_id, system_id = await _create_octoprint_system(auth_client)
    token = await _pair(auth_client, printer_id, system_id)
    bridge_headers = {"X-FilamentHub-Bridge-Token": token}

    brand = Brand(name="Picker Brand", slug="picker-brand")
    db_session.add(brand)
    await db_session.flush()
    pla = Filament(
        brand_id=brand.id,
        name="Picker PLA Red",
        slug="picker-pla-red",
        material_type="PLA",
        color_name="Red",
        color_hex="#FF0000",
    )
    petg = Filament(
        brand_id=brand.id,
        name="Picker PETG Blue",
        slug="picker-petg-blue",
        material_type="PETG",
        color_name="Blue",
        color_hex="#0000FF",
    )
    foreign_user = User(
        email="bridge-foreign@example.com",
        username="bridgeforeign",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
    )
    db_session.add_all([pla, petg, foreign_user])
    await db_session.flush()
    first_spool = UserSpool(
        user_id=auth_user.id,
        filament_id=pla.id,
        initial_weight_g=1000.0,
        used_weight_g=100.0,
        state=UserSpoolState.shelf,
    )
    second_spool = UserSpool(
        user_id=auth_user.id,
        filament_id=petg.id,
        initial_weight_g=750.0,
        used_weight_g=50.0,
        state=UserSpoolState.shelf,
    )
    archived_spool = UserSpool(
        user_id=auth_user.id,
        filament_id=petg.id,
        initial_weight_g=750.0,
        used_weight_g=50.0,
        state=UserSpoolState.archived,
    )
    foreign_spool = UserSpool(
        user_id=foreign_user.id,
        filament_id=petg.id,
        initial_weight_g=750.0,
        used_weight_g=50.0,
        state=UserSpoolState.shelf,
    )
    db_session.add_all([first_spool, second_spool, archived_spool, foreign_spool])
    await db_session.commit()

    first_page = await auth_client.get(
        "/api/v1/octoprint-bridge/spools",
        headers=bridge_headers,
        params={"limit": 1},
    )
    assert first_page.status_code == 200
    assert len(first_page.json()["items"]) == 1
    assert first_page.json()["next_offset"] == 1

    searched = await auth_client.get(
        "/api/v1/octoprint-bridge/spools",
        headers=bridge_headers,
        params={"query": "blue"},
    )
    assert searched.status_code == 200
    assert [item["id"] for item in searched.json()["items"]] == [second_spool.id]
    assert searched.json()["items"][0]["location"] is None

    printer = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    first_slot, second_slot = printer["material_systems"][0]["slots"]
    first_command = {
        "expected_revision": first_slot["assignment_revision"],
        "expected_spool_id": None,
        "spool_id": first_spool.id,
    }
    assigned = await auth_client.patch(
        f"/api/v1/octoprint-bridge/material-slots/{first_slot['id']}",
        headers=bridge_headers,
        json=first_command,
    )
    assert assigned.status_code == 200
    assigned_slot = assigned.json()["slots"][0]
    assert assigned_slot["assignment_revision"] == 1
    assert assigned_slot["spool"]["id"] == first_spool.id

    canonical = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    canonical_first = canonical["material_systems"][0]["slots"][0]
    assert canonical_first["assignment_revision"] == 1
    assert canonical_first["assignment"]["spool_id"] == first_spool.id

    located = await auth_client.get(
        "/api/v1/octoprint-bridge/spools",
        headers=bridge_headers,
        params={"query": "red"},
    )
    assert located.status_code == 200
    assert located.json()["items"][0]["location"] == {
        "material_slot_id": first_slot["id"],
        "slot_index": first_slot["provider_index"],
        "slot_label": first_slot["label"],
        "system_name": "OctoPrint",
        "printer_name": "OctoPrint Virtual Printer",
    }

    other_printer_id, _ = await _create_octoprint_system(auth_client)
    other_printer = (await auth_client.get(f"/api/v1/physical-printers/{other_printer_id}")).json()
    other_slot = other_printer["material_systems"][0]["slots"][0]
    wrong_connection = await auth_client.patch(
        f"/api/v1/octoprint-bridge/material-slots/{other_slot['id']}",
        headers=bridge_headers,
        json={
            "expected_revision": other_slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": second_spool.id,
        },
    )
    assert wrong_connection.status_code == 404
    assert wrong_connection.json()["detail"]["code"] == "ERR_MATERIAL_SLOT_NOT_FOUND"

    replayed = await auth_client.patch(
        f"/api/v1/octoprint-bridge/material-slots/{first_slot['id']}",
        headers=bridge_headers,
        json=first_command,
    )
    assert replayed.status_code == 200
    assert replayed.json()["slots"][0]["assignment_revision"] == 1

    second_assigned = await auth_client.patch(
        f"/api/v1/octoprint-bridge/material-slots/{second_slot['id']}",
        headers=bridge_headers,
        json={
            "expected_revision": second_slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": second_spool.id,
        },
    )
    assert second_assigned.status_code == 200
    current_slots = second_assigned.json()["slots"]

    moved = await auth_client.patch(
        f"/api/v1/octoprint-bridge/material-slots/{first_slot['id']}",
        headers=bridge_headers,
        json={
            "expected_revision": current_slots[0]["assignment_revision"],
            "expected_spool_id": first_spool.id,
            "spool_id": second_spool.id,
        },
    )
    assert moved.status_code == 200
    moved_slots = moved.json()["slots"]
    assert moved_slots[0]["spool"]["id"] == second_spool.id
    assert moved_slots[0]["assignment_revision"] == 2
    assert moved_slots[1]["spool"] is None
    assert moved_slots[1]["assignment_revision"] == 2

    await db_session.refresh(first_spool)
    await db_session.refresh(second_spool)
    assert first_spool.state == UserSpoolState.shelf
    assert second_spool.state == UserSpoolState.active
    assignments = list(
        (
            await db_session.scalars(
                select(MaterialSlotAssignment).where(
                    MaterialSlotAssignment.spool_id == second_spool.id
                )
            )
        ).all()
    )
    assert [assignment.material_slot_id for assignment in assignments] == [first_slot["id"]]

    stale = await auth_client.patch(
        f"/api/v1/octoprint-bridge/material-slots/{first_slot['id']}",
        headers=bridge_headers,
        json={
            "expected_revision": 1,
            "expected_spool_id": first_spool.id,
            "spool_id": None,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "ERR_MATERIAL_ASSIGNMENT_CONFLICT"

    foreign = await auth_client.patch(
        f"/api/v1/octoprint-bridge/material-slots/{first_slot['id']}",
        headers=bridge_headers,
        json={
            "expected_revision": moved_slots[0]["assignment_revision"],
            "expected_spool_id": second_spool.id,
            "spool_id": foreign_spool.id,
        },
    )
    assert foreign.status_code == 404
    assert foreign.json()["detail"]["code"] == "ERR_SPOOL_NOT_ACCESSIBLE"

    clear_command = {
        "expected_revision": moved_slots[0]["assignment_revision"],
        "expected_spool_id": second_spool.id,
        "spool_id": None,
    }
    cleared = await auth_client.patch(
        f"/api/v1/octoprint-bridge/material-slots/{first_slot['id']}",
        headers=bridge_headers,
        json=clear_command,
    )
    assert cleared.status_code == 200
    assert cleared.json()["slots"][0]["spool"] is None
    assert cleared.json()["slots"][0]["assignment_revision"] == 3
    retried_clear = await auth_client.patch(
        f"/api/v1/octoprint-bridge/material-slots/{first_slot['id']}",
        headers=bridge_headers,
        json=clear_command,
    )
    assert retried_clear.status_code == 200
    assert retried_clear.json()["slots"][0]["assignment_revision"] == 3
    await db_session.refresh(second_spool)
    assert second_spool.state == UserSpoolState.shelf


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
async def test_bridge_credential_can_revoke_its_own_connection(
    auth_client: AsyncClient,
) -> None:
    printer_id, system_id = await _create_octoprint_system(auth_client)
    token = await _pair(auth_client, printer_id, system_id)
    bridge_headers = {"X-FilamentHub-Bridge-Token": token}

    revoke_response = await auth_client.delete(
        "/api/v1/octoprint-bridge/connection",
        headers=bridge_headers,
    )

    assert revoke_response.status_code == 204
    rejected = await auth_client.get(
        "/api/v1/octoprint-bridge/snapshot",
        headers=bridge_headers,
    )
    assert rejected.status_code == 401
    status_response = await auth_client.get(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}"
    )
    assert status_response.status_code == 200
    assert status_response.json()["paired"] is False


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


@pytest.mark.asyncio
async def test_bridge_routing_round_trips_between_octoprint_and_site(
    auth_client: AsyncClient,
) -> None:
    printer_id, system_id = await _create_octoprint_system(auth_client)
    token = await _pair(auth_client, printer_id, system_id)
    bridge_headers = {"X-FilamentHub-Bridge-Token": token}

    seeded = await auth_client.post(
        "/api/v1/octoprint-bridge/heartbeat",
        headers=bridge_headers,
        json={
            "instance_id": "octoprint-test-instance",
            "plugin_version": "0.1.0",
            "octoprint_version": "1.11.8",
            "capabilities": ["read", "write", "presence", "consumption"],
            "active_slot_index": None,
            "routing_mode": "tools",
            "tool_slot_map": [
                {"tool_index": 0, "slot_index": 0},
                {"tool_index": 7, "slot_index": 0},
            ],
            "routing_revision": 0,
        },
    )
    assert seeded.status_code == 200
    assert seeded.json()["routing"] == {
        "mode": "tools",
        "tool_slot_map": [
            {"tool_index": 0, "slot_index": 0},
            {"tool_index": 7, "slot_index": 0},
        ],
        "revision": 1,
        "applied_revision": 1,
    }

    site_update = await auth_client.put(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}/routing",
        json={
            "mode": "tools",
            "tool_slot_map": [
                {"tool_index": 0, "slot_index": 0},
                {"tool_index": 1, "slot_index": 1},
            ],
            "expected_revision": 1,
        },
    )
    assert site_update.status_code == 200
    assert site_update.json()["revision"] == 2
    assert site_update.json()["applied_revision"] == 1

    old_bridge_state = await auth_client.post(
        "/api/v1/octoprint-bridge/heartbeat",
        headers=bridge_headers,
        json={
            "instance_id": "octoprint-test-instance",
            "plugin_version": "0.1.0",
            "octoprint_version": "1.11.8",
            "capabilities": ["read", "write", "presence", "consumption"],
            "active_slot_index": None,
            "routing_mode": "tools",
            "tool_slot_map": [
                {"tool_index": 0, "slot_index": 0},
                {"tool_index": 7, "slot_index": 0},
            ],
            "routing_revision": 1,
        },
    )
    assert old_bridge_state.status_code == 200
    assert old_bridge_state.json()["routing"]["revision"] == 2
    assert old_bridge_state.json()["routing"]["applied_revision"] == 1

    applied = await auth_client.post(
        "/api/v1/octoprint-bridge/heartbeat",
        headers=bridge_headers,
        json={
            "instance_id": "octoprint-test-instance",
            "plugin_version": "0.1.0",
            "octoprint_version": "1.11.8",
            "capabilities": ["read", "write", "presence", "consumption"],
            "active_slot_index": None,
            "routing_mode": "tools",
            "tool_slot_map": [
                {"tool_index": 0, "slot_index": 0},
                {"tool_index": 1, "slot_index": 1},
            ],
            "routing_revision": 2,
        },
    )
    assert applied.status_code == 200
    assert applied.json()["routing"]["applied_revision"] == 2

    bridge_update = await auth_client.put(
        "/api/v1/octoprint-bridge/routing",
        headers=bridge_headers,
        json={"mode": "manual", "tool_slot_map": [], "expected_revision": 2},
    )
    assert bridge_update.status_code == 200
    assert bridge_update.json()["revision"] == 3

    site_status = await auth_client.get(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}"
    )
    assert site_status.status_code == 200
    assert site_status.json()["routing"]["mode"] == "manual"
    assert site_status.json()["routing"]["revision"] == 3

    stale_update = await auth_client.put(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}/routing",
        json={
            "mode": "tools",
            "tool_slot_map": [{"tool_index": 0, "slot_index": 0}],
            "expected_revision": 2,
        },
    )
    assert stale_update.status_code == 409
    assert stale_update.json()["detail"] == {
        "code": "ERR_OCTOPRINT_BRIDGE_ROUTING_CONFLICT",
        "params": {"current_revision": 3},
    }

    invalid_slot = await auth_client.put(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}/routing",
        json={
            "mode": "tools",
            "tool_slot_map": [{"tool_index": 0, "slot_index": 99}],
            "expected_revision": 3,
        },
    )
    assert invalid_slot.status_code == 404
    assert invalid_slot.json()["detail"]["code"] == "ERR_MATERIAL_SLOT_NOT_FOUND"

    duplicate_tool = await auth_client.put(
        f"/api/v1/octoprint-bridge/connections/{printer_id}/{system_id}/routing",
        json={
            "mode": "tools",
            "tool_slot_map": [
                {"tool_index": 0, "slot_index": 0},
                {"tool_index": 0, "slot_index": 1},
            ],
            "expected_revision": 3,
        },
    )
    assert duplicate_tool.status_code == 422
