"""Conflict and replay contract for canonical desired slot assignments."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import PhysicalPrinterConnector
from app.models.preset_gate_state import PresetGateState
from app.models.preset_usage_event import PresetUsageEvent
from app.models.print_job import PrintJob, PrintJobMaterial, PrintJobStatus
from app.models.printer_bridge_observation import MaterialSlotObservation
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState


def _slot(printer: dict, slot_id: int) -> dict:
    return next(
        slot
        for system in printer["material_systems"]
        for slot in system["slots"]
        if slot["id"] == slot_id
    )


def _update(slot: dict, **changes) -> dict:
    return {
        "expected_revision": slot["assignment_revision"],
        "expected_spool_id": (
            slot["assignment"]["spool_id"] if slot["assignment"] else None
        ),
        **changes,
    }


async def _printer_with_slots(
    client: AsyncClient,
    *,
    slot_count: int = 1,
) -> tuple[int, int, dict]:
    printer = await client.post(
        "/api/v1/physical-printers",
        json={"name": f"Revision printer {slot_count}"},
    )
    assert printer.status_code == 201
    printer_id = printer.json()["id"]
    created = await client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "Revision feed",
            "kind": "mmu" if slot_count > 1 else "direct_feed",
            "provider": "manual",
            "capabilities": ["read", "write"],
            "slot_count": slot_count,
        },
    )
    assert created.status_code == 201
    system = created.json()["material_systems"][0]
    return printer_id, system["id"], created.json()


async def _spools(
    db: AsyncSession,
    user: User,
    count: int,
) -> list[UserSpool]:
    rows = [
        UserSpool(
            user_id=user.id,
            initial_weight_g=1000,
            used_weight_g=0,
            state=UserSpoolState.shelf,
            source="manual",
        )
        for _ in range(count)
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


@pytest.mark.asyncio
async def test_assignment_revision_rejects_stale_displacement_and_deduplicates_retry(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer_id, system_id, printer = await _printer_with_slots(auth_client)
    slot = printer["material_systems"][0]["slots"][0]
    first_spool, second_spool = await _spools(db_session, auth_user, 2)

    connector = PhysicalPrinterConnector(
        user_id=auth_user.id,
        physical_printer_id=printer_id,
        material_system_id=system_id,
        provider="test_observer",
        transport="test",
        capabilities=["presence"],
    )
    db_session.add(connector)
    await db_session.flush()
    observation = MaterialSlotObservation(
        user_id=auth_user.id,
        connector_id=connector.id,
        material_slot_id=slot["id"],
        source="test_observer",
        observed_at=datetime.now(timezone.utc),
        present=True,
        active_feed=True,
        material="PLA",
        color_hex="112233",
    )
    db_session.add(observation)
    await db_session.commit()

    slot_url = (
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slot['id']}"
    )
    first_command = _update(slot, spool_id=first_spool.id)
    accepted = await auth_client.patch(slot_url, json=first_command)
    assert accepted.status_code == 200
    accepted_slot = _slot(accepted.json(), slot["id"])
    assert accepted_slot["assignment_revision"] == 1
    assert accepted_slot["assignment"]["spool_id"] == first_spool.id
    assert accepted_slot["observation"]["material"] == "PLA"

    replayed = await auth_client.patch(slot_url, json=first_command)
    assert replayed.status_code == 200
    assert _slot(replayed.json(), slot["id"])["assignment_revision"] == 1

    stale = await auth_client.patch(
        slot_url,
        json={**first_command, "spool_id": second_spool.id},
    )
    assert stale.status_code == 409
    stale_detail = stale.json()["detail"]
    assert stale_detail["code"] == "ERR_MATERIAL_ASSIGNMENT_CONFLICT"
    assert stale_detail["params"]["current_revision"] == 1
    assert stale_detail["params"]["current_spool_id"] == first_spool.id

    wrong_displaced_identity = await auth_client.patch(
        slot_url,
        json={
            "expected_revision": 1,
            "expected_spool_id": None,
            "spool_id": second_spool.id,
        },
    )
    assert wrong_displaced_identity.status_code == 409

    print_job = PrintJob(
        user_id=auth_user.id,
        physical_printer_id=printer_id,
        title="Active revision test",
        status=PrintJobStatus.printing,
        source="manual",
        source_ref="assignment-revision-active-job",
        source_payload_hash="0" * 64,
    )
    print_job.materials.append(
        PrintJobMaterial(
            spool_id=first_spool.id,
            spool_snapshot={"id": first_spool.id, "name": f"Spool #{first_spool.id}"},
        )
    )
    db_session.add(print_job)
    await db_session.commit()

    replaced = await auth_client.patch(
        slot_url,
        json={
            "expected_revision": 1,
            "expected_spool_id": first_spool.id,
            "spool_id": second_spool.id,
        },
    )
    assert replaced.status_code == 200
    replaced_slot = _slot(replaced.json(), slot["id"])
    assert replaced_slot["assignment_revision"] == 2
    assert replaced_slot["assignment"]["spool_id"] == second_spool.id
    assert replaced_slot["observation"]["material"] == "PLA"

    await db_session.refresh(first_spool)
    await db_session.refresh(second_spool)
    assert first_spool.state == UserSpoolState.shelf
    assert second_spool.state == UserSpoolState.active
    assert await db_session.scalar(
        select(PrintJob.status).where(PrintJob.id == print_job.id)
    ) == PrintJobStatus.printing
    assert await db_session.scalar(
        select(PrintJobMaterial.spool_id).where(
            PrintJobMaterial.print_job_id == print_job.id
        )
    ) == first_spool.id
    assert await db_session.scalar(select(func.count(PresetUsageEvent.id))) == 0
    assignments = list((await db_session.scalars(select(MaterialSlotAssignment))).all())
    assert [(item.material_slot_id, item.spool_id) for item in assignments] == [
        (slot["id"], second_spool.id)
    ]


@pytest.mark.asyncio
async def test_bulk_clear_conflicts_with_assign_and_preserves_created_spool(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer_id, system_id, printer = await _printer_with_slots(
        auth_client,
        slot_count=2,
    )
    slots = printer["material_systems"][0]["slots"]
    first_spool, created_spool = await _spools(db_session, auth_user, 2)
    clear_from_first_client = {
        "slots": [
            {
                "material_slot_id": slot["id"],
                "expected_revision": slot["assignment_revision"],
                "expected_spool_id": None,
            }
            for slot in slots
        ]
    }

    first_slot_url = (
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slots[0]['id']}"
    )
    assigned = await auth_client.patch(
        first_slot_url,
        json=_update(slots[0], spool_id=first_spool.id),
    )
    assert assigned.status_code == 200
    assigned_slot = _slot(assigned.json(), slots[0]["id"])

    stale_clear = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems/{system_id}/clear",
        json=clear_from_first_client,
    )
    assert stale_clear.status_code == 409
    assert stale_clear.json()["detail"]["params"]["slots"][0][
        "current_revision"
    ] == 1

    current_printer = (await auth_client.get(
        f"/api/v1/physical-printers/{printer_id}"
    )).json()
    current_slots = current_printer["material_systems"][0]["slots"]
    current_clear = {
        "slots": [
            {
                "material_slot_id": slot["id"],
                "expected_revision": slot["assignment_revision"],
                "expected_spool_id": (
                    slot["assignment"]["spool_id"] if slot["assignment"] else None
                ),
            }
            for slot in current_slots
        ]
    }
    cleared = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems/{system_id}/clear",
        json=current_clear,
    )
    assert cleared.status_code == 200
    cleared_slot = _slot(cleared.json(), slots[0]["id"])
    assert cleared_slot["assignment"] is None
    assert cleared_slot["assignment_revision"] == 2

    retried_clear = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems/{system_id}/clear",
        json=current_clear,
    )
    assert retried_clear.status_code == 200
    assert _slot(retried_clear.json(), slots[0]["id"])["assignment_revision"] == 2

    stale_assign_after_clear = await auth_client.patch(
        first_slot_url,
        json={
            "expected_revision": assigned_slot["assignment_revision"],
            "expected_spool_id": first_spool.id,
            "spool_id": created_spool.id,
        },
    )
    assert stale_assign_after_clear.status_code == 409
    missing_guard = await auth_client.patch(
        first_slot_url,
        json={"spool_id": created_spool.id},
    )
    assert missing_guard.status_code == 422

    await db_session.refresh(created_spool)
    assert created_spool.state == UserSpoolState.shelf
    assert await db_session.get(UserSpool, created_spool.id) is not None


@pytest.mark.asyncio
async def test_happy_hare_bypass_route_is_not_forced_into_legacy_gate_map(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "HH bypass revision printer"},
    )
    assert printer.status_code == 201
    printer_id = printer.json()["id"]
    created = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "Happy Hare with bypass",
            "kind": "mmu",
            "provider": "happy_hare",
            "capabilities": ["read", "write", "presence"],
            "slots": [
                {
                    "provider_index": 1023,
                    "label": "Bypass",
                    "kind": "bypass",
                }
            ],
        },
    )
    assert created.status_code == 201
    route = created.json()["material_systems"][0]["slots"][0]
    spool = (await _spools(db_session, auth_user, 1))[0]

    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{route['id']}",
        json=_update(route, spool_id=spool.id),
    )

    assert assigned.status_code == 200
    assigned_route = _slot(assigned.json(), route["id"])
    assert assigned_route["kind"] == "bypass"
    assert assigned_route["assignment_revision"] == 1
    assert assigned_route["assignment"]["spool_id"] == spool.id
    assert await db_session.scalar(
        select(func.count(PresetGateState.id)).where(
            PresetGateState.device_id == printer_id
        )
    ) == 0
