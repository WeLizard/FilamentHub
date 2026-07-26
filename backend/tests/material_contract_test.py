"""Regression tests for the provider-neutral physical printer contract."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.preset_gate_state import PresetGateState
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.material_contract_service import ensure_material_topology


async def _profile(
    db: AsyncSession,
    *,
    slug: str,
    owner_user_id: int | None,
    is_official: bool = False,
) -> PrinterProfile:
    profile = PrinterProfile(
        name=slug,
        slug=slug,
        owner_user_id=owner_user_id,
        is_official=is_official,
        active=True,
        orcaslicer_settings={},
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@pytest.mark.asyncio
async def test_physical_printer_groups_multiple_owned_or_official_configs(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    nozzle_04 = await _profile(
        db_session, slug="voron-04", owner_user_id=auth_user.id
    )
    nozzle_06 = await _profile(
        db_session, slug="voron-06", owner_user_id=auth_user.id
    )
    official = await _profile(
        db_session, slug="voron-official", owner_user_id=None, is_official=True
    )

    response = await auth_client.post(
        "/api/v1/physical-printers",
        json={
            "name": "Voron at home",
            "printer_profile_ids": [nozzle_04.id, nozzle_06.id, official.id],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Voron at home"
    assert len(body["logical_id"]) == 36
    assert body["printer_profile_ids"] == sorted(
        [nozzle_04.id, nozzle_06.id, official.id]
    )
    assert body["material_systems"] == []
    assert body["connectors"] == []


@pytest.mark.asyncio
async def test_identical_models_remain_distinct_physical_printers(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    catalog_printer = Printer(
        name="Bambu Lab X1C",
        manufacturer="Bambu Lab",
        model="X1C",
        slug="bambu-lab-x1c-material-contract",
        active=True,
    )
    db_session.add(catalog_printer)
    await db_session.commit()
    await db_session.refresh(catalog_printer)
    first = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "X1C office", "printer_id": catalog_printer.id},
    )
    second = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "X1C workshop", "printer_id": catalog_printer.id},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["logical_id"] != second.json()["logical_id"]


@pytest.mark.asyncio
async def test_foreign_configuration_and_printer_are_fail_closed(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    foreign_user = User(
        email="foreign-material@example.com",
        username="foreign-material",
        password_hash="$2b$12$test",
        active=True,
    )
    db_session.add(foreign_user)
    await db_session.commit()
    await db_session.refresh(foreign_user)
    foreign_profile = await _profile(
        db_session, slug="foreign-machine", owner_user_id=foreign_user.id
    )

    rejected = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "Invalid", "printer_profile_ids": [foreign_profile.id]},
    )
    assert rejected.status_code == 404

    foreign_printer = UserPrinterDevice(
        user_id=foreign_user.id,
        name="Foreign printer",
        device_fingerprint=None,
        supports_hh=False,
    )
    db_session.add(foreign_printer)
    await db_session.commit()
    await db_session.refresh(foreign_printer)

    hidden = await auth_client.get(f"/api/v1/physical-printers/{foreign_printer.id}")
    assert hidden.status_code == 404

    foreign_system = MaterialSystem(
        user_id=foreign_user.id,
        physical_printer_id=foreign_printer.id,
        name="Foreign feeder",
        kind="direct_feed",
        provider="manual",
        capabilities=[],
    )
    foreign_slot = MaterialSlot(
        user_id=foreign_user.id,
        provider_index=0,
        kind="slot",
    )
    foreign_system.slots = [foreign_slot]
    db_session.add(foreign_system)
    await db_session.commit()
    await db_session.refresh(foreign_slot)

    hidden_assignment = await auth_client.patch(
        f"/api/v1/physical-printers/{foreign_printer.id}/material-slots/"
        f"{foreign_slot.id}",
        json={"spool_id": None},
    )
    assert hidden_assignment.status_code == 404
    hidden_clear = await auth_client.post(
        f"/api/v1/physical-printers/{foreign_printer.id}/material-systems/"
        f"{foreign_system.id}/clear"
    )
    assert hidden_clear.status_code == 404


@pytest.mark.asyncio
async def test_manual_material_system_and_connector_are_separate(
    auth_client: AsyncClient,
) -> None:
    created = await auth_client.post(
        "/api/v1/physical-printers", json={"name": "Manual printer"}
    )
    printer_id = created.json()["id"]

    system_response = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "ERCF",
            "kind": "mmu",
            "provider": "manual",
            "capabilities": [],
            "slots": [
                {"provider_index": 0, "label": "Gate 0"},
                {"provider_index": 1, "label": "Gate 1"},
            ],
        },
    )
    assert system_response.status_code == 201
    system = system_response.json()["material_systems"][0]
    assert system["provider"] == "manual"
    assert [slot["provider_index"] for slot in system["slots"]] == [0, 1]
    assert [slot["assignment"] for slot in system["slots"]] == [None, None]
    assert [slot["legacy_projection"] for slot in system["slots"]] == [None, None]
    assert system_response.json()["connectors"] == []

    connector_response = await auth_client.put(
        f"/api/v1/physical-printers/{printer_id}/connectors",
        json={
            "provider": "happy_hare",
            "transport": "spoolman_compat",
            "material_system_id": system["id"],
            "capabilities": ["read", "write", "presence", "spool_identity"],
        },
    )
    assert connector_response.status_code == 200
    connector = connector_response.json()["connectors"][0]
    assert connector["material_system_id"] == system["id"]
    assert connector["provider"] == "happy_hare"

    repeated = await auth_client.put(
        f"/api/v1/physical-printers/{printer_id}/connectors",
        json={
            "provider": "happy_hare",
            "transport": "spoolman_compat",
            "material_system_id": system["id"],
            "capabilities": ["read"],
        },
    )
    assert repeated.status_code == 200
    assert len(repeated.json()["connectors"]) == 1
    assert repeated.json()["connectors"][0]["id"] == connector["id"]
    assert repeated.json()["connectors"][0]["capabilities"] == ["read"]


@pytest.mark.asyncio
async def test_legacy_devices_endpoint_excludes_manual_registry_only_rows(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    manual = await auth_client.post(
        "/api/v1/physical-printers", json={"name": "No connector"}
    )
    legacy = UserPrinterDevice(
        user_id=auth_user.id,
        name="HH adapter",
        device_fingerprint="legacy-test-device",
        supports_hh=True,
    )
    db_session.add(legacy)
    await db_session.commit()
    await db_session.refresh(legacy)

    response = await auth_client.get("/api/v1/devices")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [legacy.id]
    assert manual.json()["id"] != legacy.id


@pytest.mark.asyncio
async def test_duplicate_provider_indices_are_rejected_before_write(
    auth_client: AsyncClient,
) -> None:
    created = await auth_client.post(
        "/api/v1/physical-printers", json={"name": "Duplicate slot test"}
    )
    response = await auth_client.post(
        f"/api/v1/physical-printers/{created.json()['id']}/material-systems",
        json={
            "name": "AMS",
            "kind": "ams",
            "provider": "manual",
            "slots": [{"provider_index": 0}, {"provider_index": 0}],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_legacy_hh_flow_dual_writes_system_slots_and_connector(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    created = await auth_client.post(
        "/api/v1/devices/create-with-key", json={"name": "Legacy HH"}
    )
    assert created.status_code == 200
    device_id = created.json()["device"]["id"]

    updated = await auth_client.patch(
        f"/api/v1/devices/{device_id}",
        json={"supports_hh": True, "gate_count": 2},
    )
    assert updated.status_code == 200
    spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)
    assigned = await auth_client.patch(
        f"/api/v1/preset-slots/{device_id}/1", json={"spool_id": spool.id}
    )
    assert assigned.status_code == 200

    system = await db_session.scalar(
        select(MaterialSystem).where(
            MaterialSystem.physical_printer_id == device_id
        )
    )
    assert system is not None
    assert system.provider == "happy_hare"
    slots = (
        await db_session.execute(
            select(MaterialSlot)
            .where(MaterialSlot.material_system_id == system.id)
            .order_by(MaterialSlot.provider_index)
        )
    ).scalars().all()
    assert [slot.provider_index for slot in slots] == [0, 1]
    connector = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.physical_printer_id == device_id
        )
    )
    assert connector is not None
    assert connector.material_system_id == system.id
    gate_state = await db_session.scalar(
        select(PresetGateState).where(
            PresetGateState.device_id == device_id,
            PresetGateState.gate_index == 1,
        )
    )
    assert gate_state is not None
    assert gate_state.material_slot_id == slots[1].id

    physical = await auth_client.get(f"/api/v1/physical-printers/{device_id}")
    assert physical.status_code == 200
    physical_slots = physical.json()["material_systems"][0]["slots"]
    assert physical_slots[0]["legacy_projection"] is None
    projection = physical_slots[1]["legacy_projection"]
    assert projection == {
        "gate_state_id": gate_state.id,
        "preset_id": None,
        "spool_id": spool.id,
        "source": "web_manual",
        "source_ts": gate_state.source_ts.isoformat().replace("+00:00", "Z"),
        "is_active": True,
        "hh_material": None,
        "hh_color_hex": None,
        "hh_status": None,
        "updated_at": gate_state.updated_at.isoformat().replace("+00:00", "Z"),
    }
    assert physical_slots[1]["assignment"]["spool_id"] == spool.id


@pytest.mark.asyncio
async def test_slots_sharing_a_provider_index_assign_by_slot_id(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    """Slot zero exists on every printer, so a spool moves by slot id, not index."""
    left = await auth_client.post(
        "/api/v1/physical-printers", json={"name": "Left printer"}
    )
    right = await auth_client.post(
        "/api/v1/physical-printers", json={"name": "Right printer"}
    )
    left_id = left.json()["id"]
    right_id = right.json()["id"]

    first = await auth_client.post(
        f"/api/v1/physical-printers/{left_id}/material-systems",
        json={
            "name": "Left feeder",
            "kind": "direct_feed",
            "provider": "manual",
            "slots": [{"provider_index": 0, "label": "Left"}],
        },
    )
    first_slot_id = first.json()["material_systems"][0]["slots"][0]["id"]
    second = await auth_client.post(
        f"/api/v1/physical-printers/{right_id}/material-systems",
        json={
            "name": "Right feeder",
            "kind": "direct_feed",
            "provider": "manual",
            "slots": [{"provider_index": 0, "label": "Right"}],
        },
    )
    second_system = second.json()["material_systems"][0]
    second_slot_id = second_system["slots"][0]["id"]

    spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)

    assigned_first = await auth_client.patch(
        f"/api/v1/physical-printers/{left_id}/material-slots/{first_slot_id}",
        json={"spool_id": spool.id},
    )
    assert assigned_first.status_code == 200
    systems = assigned_first.json()["material_systems"]
    assert systems[0]["slots"][0]["assignment"]["spool_id"] == spool.id

    assigned_second = await auth_client.patch(
        f"/api/v1/physical-printers/{right_id}/material-slots/{second_slot_id}",
        json={"spool_id": spool.id},
    )
    assert assigned_second.status_code == 200
    both = await auth_client.get("/api/v1/physical-printers")
    systems = [
        system
        for printer in both.json()
        if printer["id"] in (left_id, right_id)
        for system in printer["material_systems"]
    ]
    slots_by_id = {
        slot["id"]: slot
        for system in systems
        for slot in system["slots"]
    }
    assert slots_by_id[first_slot_id]["assignment"] is None
    assert slots_by_id[second_slot_id]["assignment"]["spool_id"] == spool.id
    assert all(
        slot["provider_index"] == 0
        for system in systems
        for slot in system["slots"]
    )
    assert await db_session.scalar(select(PresetGateState.id)) is None

    cleared = await auth_client.post(
        f"/api/v1/physical-printers/{right_id}/material-systems/"
        f"{second_system['id']}/clear"
    )
    assert cleared.status_code == 200
    cleared_slot = next(
        slot
        for system in cleared.json()["material_systems"]
        for slot in system["slots"]
        if slot["id"] == second_slot_id
    )
    assert cleared_slot["assignment"] is None
    await db_session.refresh(spool)
    assert spool.state == UserSpoolState.shelf


@pytest.mark.asyncio
async def test_a_printer_takes_only_one_feed_system(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    """Two systems on one printer would race to describe the same slots."""
    created = await auth_client.post(
        "/api/v1/physical-printers", json={"name": "One feed only"}
    )
    printer_id = created.json()["id"]
    payload = {"name": "Happy Hare", "kind": "mmu", "provider": "happy_hare", "slot_count": 8}

    first = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems", json=payload
    )
    assert first.status_code == 201

    second = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={"name": "OctoPrint", "kind": "mmu", "provider": "octoprint", "slot_count": 1},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ERR_MATERIAL_SYSTEM_EXISTS"

    physical = await auth_client.get(f"/api/v1/physical-printers/{printer_id}")
    assert [s["provider"] for s in physical.json()["material_systems"]] == ["happy_hare"]

    # The rule holds below the API too, so no other path can slip a second one in.
    with pytest.raises(IntegrityError):
        db_session.add(
            MaterialSystem(
                user_id=auth_user.id,
                physical_printer_id=printer_id,
                name="Sneaked in",
                kind="mmu",
                provider="octoprint",
                capabilities=[],
            )
        )
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_issuing_a_key_leaves_another_providers_system_alone(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    """A system that names its own way of reporting is not relabelled by Klipper."""
    created = await auth_client.post(
        "/api/v1/physical-printers", json={"name": "OctoPrint printer"}
    )
    printer_id = created.json()["id"]

    system_response = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "OctoPrint",
            "kind": "mmu",
            "provider": "octoprint",
            "slot_count": 2,
        },
    )
    assert system_response.status_code == 201

    device = await db_session.get(UserPrinterDevice, printer_id)
    device.gate_count = 7
    await db_session.commit()

    reissued = await auth_client.post(f"/api/v1/devices/{printer_id}/regenerate-key")
    assert reissued.status_code == 200

    physical = await auth_client.get(f"/api/v1/physical-printers/{printer_id}")
    systems = physical.json()["material_systems"]
    assert [system["provider"] for system in systems] == ["octoprint"]
    assert len(systems[0]["slots"]) == 2
    assert systems[0]["declared_slot_count"] == 2


@pytest.mark.asyncio
async def test_reported_gate_fills_the_slots_below_it(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    created = await auth_client.post(
        "/api/v1/devices/create-with-key", json={"name": "ERCF"}
    )
    assert created.status_code == 200
    device_id = created.json()["device"]["id"]

    spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)

    assigned = await auth_client.patch(
        f"/api/v1/preset-slots/{device_id}/4", json={"spool_id": spool.id}
    )
    assert assigned.status_code == 200

    physical = await auth_client.get(f"/api/v1/physical-printers/{device_id}")
    assert physical.status_code == 200
    system = physical.json()["material_systems"][0]
    assert [slot["provider_index"] for slot in system["slots"]] == [0, 1, 2, 3, 4]
    assert system["declared_slot_count"] is None


@pytest.mark.asyncio
async def test_declared_slot_count_resizes_and_protects_occupied_slots(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    created = await auth_client.post(
        "/api/v1/devices/create-with-key", json={"name": "MMU", "gate_count": 2}
    )
    assert created.status_code == 200
    device_id = created.json()["device"]["id"]

    physical = await auth_client.get(f"/api/v1/physical-printers/{device_id}")
    system = physical.json()["material_systems"][0]
    assert system["declared_slot_count"] == 2

    grown = await auth_client.patch(
        f"/api/v1/physical-printers/{device_id}/material-systems/{system['id']}",
        json={"slot_count": 5},
    )
    assert grown.status_code == 200
    assert [
        slot["provider_index"] for slot in grown.json()["material_systems"][0]["slots"]
    ] == [0, 1, 2, 3, 4]

    spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)
    assigned = await auth_client.patch(
        f"/api/v1/preset-slots/{device_id}/4", json={"spool_id": spool.id}
    )
    assert assigned.status_code == 200

    refused = await auth_client.patch(
        f"/api/v1/physical-printers/{device_id}/material-systems/{system['id']}",
        json={"slot_count": 3},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "ERR_MATERIAL_SLOT_IN_USE"

    shrunk = await auth_client.patch(
        f"/api/v1/physical-printers/{device_id}/material-systems/{system['id']}",
        json={"slot_count": 5},
    )
    assert shrunk.status_code == 200
    assert shrunk.json()["material_systems"][0]["declared_slot_count"] == 5


@pytest.mark.asyncio
async def test_a_gate_beyond_the_declared_count_asks_the_question_again(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    created = await auth_client.post(
        "/api/v1/devices/create-with-key", json={"name": "MMU", "gate_count": 2}
    )
    assert created.status_code == 200
    device_id = created.json()["device"]["id"]

    device = await db_session.get(UserPrinterDevice, device_id)
    assert device is not None
    # Happy Hare reports gates over the Spoolman-compatible API, which is not
    # bound by the legacy gate map the manual endpoint checks.
    await ensure_material_topology(db_session, device, gate_indices={6})
    await db_session.commit()

    physical = await auth_client.get(f"/api/v1/physical-printers/{device_id}")
    system = physical.json()["material_systems"][0]
    assert system["declared_slot_count"] is None
    assert len(system["slots"]) == 7


@pytest.mark.asyncio
async def test_deleting_a_system_returns_spools_and_keeps_the_printer(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    created = await auth_client.post(
        "/api/v1/devices/create-with-key", json={"name": "ERCF", "gate_count": 8}
    )
    assert created.status_code == 200
    device_id = created.json()["device"]["id"]
    system_id = (
        await auth_client.get(f"/api/v1/physical-printers/{device_id}")
    ).json()["material_systems"][0]["id"]

    spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)
    assigned = await auth_client.patch(
        f"/api/v1/preset-slots/{device_id}/3", json={"spool_id": spool.id}
    )
    assert assigned.status_code == 200
    await db_session.refresh(spool)
    assert spool.state == UserSpoolState.active

    removed = await auth_client.delete(
        f"/api/v1/physical-printers/{device_id}/material-systems/{system_id}"
    )
    assert removed.status_code == 200
    assert removed.json()["material_systems"] == []
    assert removed.json()["has_api_key"] is True

    assert (await db_session.execute(select(MaterialSlot))).scalars().all() == []
    assert (
        await db_session.execute(select(MaterialSlotAssignment))
    ).scalars().all() == []
    assert (
        await db_session.execute(
            select(PresetGateState).where(PresetGateState.device_id == device_id)
        )
    ).scalars().all() == []

    await db_session.refresh(spool)
    assert spool.state == UserSpoolState.shelf


@pytest.mark.asyncio
async def test_manual_system_spools_are_shelved_and_protected_like_legacy_ones(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer = await auth_client.post(
        "/api/v1/physical-printers", json={"name": "AMS printer"}
    )
    printer_id = printer.json()["id"]
    created = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={
            "name": "AMS",
            "kind": "mmu",
            "provider": "manual",
            "capabilities": [],
            "slots": [{"provider_index": index} for index in range(4)],
        },
    )
    assert created.status_code == 201
    system = created.json()["material_systems"][0]
    last_slot_id = system["slots"][3]["id"]

    spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)

    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{last_slot_id}",
        json={"spool_id": spool.id},
    )
    assert assigned.status_code == 200
    await db_session.refresh(spool)
    assert spool.state == UserSpoolState.active

    shrunk = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-systems/{system['id']}",
        json={"slot_count": 2},
    )
    assert shrunk.status_code == 409
    assert shrunk.json()["detail"]["code"] == "ERR_MATERIAL_SLOT_IN_USE"

    removed = await auth_client.delete(
        f"/api/v1/physical-printers/{printer_id}/material-systems/{system['id']}"
    )
    assert removed.status_code == 200
    assert removed.json()["material_systems"] == []

    await db_session.refresh(spool)
    assert spool.state == UserSpoolState.shelf
