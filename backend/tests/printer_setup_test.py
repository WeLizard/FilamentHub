"""Onboarding retries and attaching local evidence must not multiply printers."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.material_system import MaterialSystem
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool

pytestmark = pytest.mark.asyncio
PATH = "/api/v1/physical-printers"
SOURCE = "setup-test-desktop-instance"


def connection(**overrides):
    return {
        "source_instance_id": SOURCE, "connection_ref": "local-manual-1",
        "origin": "local_manual", "provider": "moonraker", "endpoint_token": "a" * 64,
        "device_identity": {"kind": "moonraker_instance", "token": "b" * 64},
        **overrides,
    }


async def test_creation_retry_keeps_one_printer_and_one_system(auth_client, db_session):
    payload = {
        "name": "Workshop", "request_id": str(uuid4()),
        "material_system": {"name": "External spool", "slot_count": 1},
    }
    first = await auth_client.post(PATH, json=payload)
    assert first.status_code == 201, first.text
    printer = first.json()
    assert len(printer["material_systems"][0]["slots"]) == 1
    await auth_client.patch(f"{PATH}/{printer['id']}", json={"name": "Renamed"})
    replay = await auth_client.post(PATH, json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == printer["id"]
    assert replay.json()["name"] == "Renamed"
    assert replay.json()["material_systems"] == printer["material_systems"]
    assert await db_session.scalar(select(func.count()).select_from(UserPrinterDevice)) == 1
    assert await db_session.scalar(select(func.count()).select_from(MaterialSystem)) == 1


async def test_three_explicit_identical_manual_printers_remain_three(auth_client):
    ids = set()
    for _ in range(3):
        response = await auth_client.post(PATH, json={"name": "Voron", "request_id": str(uuid4())})
        assert response.status_code == 201
        ids.add(response.json()["id"])
    assert len(ids) == 3


async def test_attach_and_reconnect_preserve_existing_manual_slots(auth_client, db_session):
    created = (await auth_client.post(PATH, json={
        "name": "My printer", "material_system": {"name": "Manual MMU", "slot_count": 4},
    })).json()
    system = created["material_systems"][0]
    attached = await auth_client.post(f"{PATH}/{created['id']}/connection-setup", json={
        "connection": connection(),
        "material_system": {"name": "Happy Hare", "provider": "happy_hare", "kind": "mmu"},
    })
    assert attached.status_code == 200, attached.text
    assert attached.json()["material_systems"][0] == system
    # Starting from Add again with the same connection resumes, never duplicates.
    again = await auth_client.post(PATH, json={
        "name": "Another label", "request_id": str(uuid4()), "connection": connection(),
    })
    assert again.status_code == 201, again.text
    assert again.json()["id"] == created["id"]
    assert again.json()["name"] == "My printer"
    assert await db_session.scalar(select(func.count()).select_from(PrinterConnectionBinding)) == 1


async def test_first_hh_observation_keeps_manual_spool_and_slot_identity(
    auth_client, db_session, auth_user,
):
    from datetime import datetime, timezone

    created = (await auth_client.post(PATH, json={
        "name": "Loaded manual printer", "material_system": {"name": "MMU", "slot_count": 4},
    })).json()
    system = created["material_systems"][0]
    slot = system["slots"][0]
    spool = UserSpool(user_id=auth_user.id, initial_weight_g=1000, used_weight_g=123)
    db_session.add(spool)
    await db_session.commit()
    assigned = await auth_client.patch(f"{PATH}/{created['id']}/material-slots/{slot['id']}", json={
        "spool_id": spool.id, "expected_spool_id": None, "expected_revision": 0,
    })
    assert assigned.status_code == 200, assigned.text
    attached = await auth_client.post(f"{PATH}/{created['id']}/connection-setup", json={
        "connection": connection(),
    })
    assert attached.status_code == 200
    observed = await auth_client.post('/api/v1/orcaslicer/preset-slot-sync/hh/snapshot', json={
        "physical_printer_id": created["id"], "gate_count": 4,
        "snapshot_ts": datetime.now(timezone.utc).isoformat(),
        "gates": [{"gate": index, "status": 0} for index in range(4)],
        "spool_ids": [None, None, None, None],
    })
    assert observed.status_code == 200, observed.text
    final = (await auth_client.get(f"{PATH}/{created['id']}")).json()["material_systems"][0]
    assert final["id"] == system["id"] and final["provider"] == "happy_hare"
    actual_slot = next(item for item in final["slots"] if item["id"] == slot["id"])
    assert actual_slot["assignment"]["spool_id"] == spool.id
    await db_session.refresh(spool)
    assert spool.used_weight_g == 123


async def test_cannot_steal_a_connection_from_another_card(auth_client, db_session):
    first = (await auth_client.post(PATH, json={"name": "First", "connection": connection()})).json()
    second = (await auth_client.post(PATH, json={"name": "Second"})).json()
    rejected = await auth_client.post(f"{PATH}/{second['id']}/connection-setup", json={
        "connection": connection(), "material_system": {"name": "Must not be created"},
    })
    assert rejected.status_code == 409
    binding = await db_session.scalar(select(PrinterConnectionBinding))
    assert binding.physical_printer_id == first["id"]
    assert await db_session.scalar(select(func.count()).select_from(MaterialSystem)) == 0


async def test_local_manual_connection_not_retired_by_orca_inventory(auth_client, db_session):
    await auth_client.post(PATH, json={"name": "Local", "connection": connection()})
    response = await auth_client.post("/api/v1/orcaslicer/printer-connections/observe", json={
        "source_instance_id": SOURCE, "observations": [], "snapshot_complete": True,
    })
    assert response.status_code == 200, response.text
    binding = await db_session.scalar(select(PrinterConnectionBinding))
    assert binding.status == "bound" and binding.source == "local_setup"


async def test_context_is_scoped_and_contains_no_local_secrets(auth_client):
    await auth_client.post(PATH, json={"name": "Local", "connection": connection()})
    path = "/api/v1/orcaslicer/printer-connections/setup-context"
    response = await auth_client.get(path, params={"source_instance_id": SOURCE})
    assert response.status_code == 200, response.text
    assert len(response.json()["discovery_key"]) == 64
    assert len(response.json()["bindings"]) == 1
    assert set(response.json()["bindings"][0]) == {"connection_ref", "physical_printer_id", "status"}
    other = await auth_client.get(path, params={"source_instance_id": "other-desktop-instance"})
    assert other.json()["bindings"] == []
    assert other.json()["discovery_key"] == response.json()["discovery_key"]
    assert (await auth_client.get(path, params={"source_instance_id": "x"})).status_code == 422


async def test_connection_setup_requires_ownership(auth_client, db_session, admin_user):
    foreign = UserPrinterDevice(user_id=admin_user.id, name="Private")
    db_session.add(foreign)
    await db_session.commit()
    response = await auth_client.post(f"{PATH}/{foreign.id}/connection-setup", json={
        "connection": connection(),
    })
    assert response.status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(PrinterConnectionBinding)) == 0
