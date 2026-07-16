"""Tests for spool_compat endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.spool_compat import (
    _filament_payload,
    _filament_temps,
    _to_spool_payload,
)
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState


async def _seed_spool_context(db: AsyncSession) -> tuple[User, UserSpool, UserPrinterDevice]:
    user = User(
        email="spool-compat-test@example.com",
        username="spool_compat_test_user",
        password_hash="not-used-in-this-test",
        active=True,
    )
    brand = Brand(name="Spool Compat Test Brand", slug="spool-compat-test-brand", verified=True, active=True)
    filament = Filament(
        brand=brand,
        name="Spool Compat Test PLA Black",
        slug="spool-compat-test-pla-black",
        material_type="PLA",
        color_name="Black",
        color_hex="#111111",
        diameter=1.75,
        density=1.24,
        spool_weight=1000.0,
        active=True,
    )
    spool = UserSpool(
        user=user,
        filament=filament,
        initial_weight_g=1000.0,
        used_weight_g=100.0,
        state=UserSpoolState.active,
        source="manual",
        lot_nr="LOT-1",
        comment="seed spool",
    )
    # spool_compat authenticates by per-device API key, not by User.api_key.
    device = UserPrinterDevice(
        user=user,
        name="Spool Compat Test Printer",
        device_fingerprint="spool-compat-test-fp",
        api_key="spool_compat_test_api_key",
        supports_hh=True,
    )
    db.add_all([user, brand, filament, spool, device])
    await db.commit()
    await db.refresh(user)
    await db.refresh(spool)
    await db.refresh(device)
    return user, spool, device


@pytest.mark.asyncio
async def test_spool_compat_sync_legacy_deprecated(client: AsyncClient):
    """Legacy /sync endpoint should remain available but marked deprecated."""
    response = await client.get("/api/v1/spool_compat/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deprecated"
    assert "v1" in data["message"].lower()


@pytest.mark.asyncio
async def test_spool_compat_v1_health_info(client: AsyncClient):
    """Health/info endpoints should be available for compatibility checks."""
    health = await client.get("/api/v1/spool_compat/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    info = await client.get("/api/v1/spool_compat/v1/info")
    assert info.status_code == 200
    assert "version" in info.json()


@pytest.mark.asyncio
async def test_spool_compat_v1_requires_api_key(client: AsyncClient):
    """Scoped spool endpoints should reject requests without a valid key."""
    response = await client.get("/api/v1/spool_compat/invalid/v1/spool")
    assert response.status_code == 401
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_spool_compat_v1_list_get_use_spool(client: AsyncClient, db_session: AsyncSession):
    """Compatibility spool flow: list -> get -> use."""
    _user, spool, device = await _seed_spool_context(db_session)
    api_key = device.api_key

    list_response = await client.get(f"/api/v1/spool_compat/{api_key}/v1/spool")
    assert list_response.status_code == 200
    assert list_response.headers.get("x-total-count") == "1"
    list_data = list_response.json()
    assert len(list_data) == 1
    assert list_data[0]["id"] == spool.id
    assert list_data[0]["filament"]["material"] == "PLA"

    get_response = await client.get(f"/api/v1/spool_compat/{api_key}/v1/spool/{spool.id}")
    assert get_response.status_code == 200
    assert get_response.json()["used_weight"] == 100.0

    use_response = await client.put(
        f"/api/v1/spool_compat/{api_key}/v1/spool/{spool.id}/use",
        json={"use_weight": 50},
    )
    assert use_response.status_code == 200
    used_weight = use_response.json()["used_weight"]
    assert used_weight == pytest.approx(150.0, rel=1e-6)


@pytest.mark.asyncio
async def test_spool_compat_create_defaults_to_shelf_and_rejects_empty(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Compatibility imports create stock spools, not phantom loaded/empty spools."""
    _user, seed_spool, device = await _seed_spool_context(db_session)
    endpoint = f"/api/v1/spool_compat/{device.api_key}/v1/spool"

    created_response = await client.post(
        endpoint,
        json={"filament_id": seed_spool.filament_id, "initial_weight": 1000},
    )
    assert created_response.status_code == 200
    created = await db_session.get(UserSpool, created_response.json()["id"])
    assert created is not None
    assert created.state == UserSpoolState.shelf

    duplicate_response = await client.post(
        endpoint,
        json={"filament_id": seed_spool.filament_id, "initial_weight": 1000},
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["id"] != created.id

    empty_response = await client.post(
        endpoint,
        json={
            "filament_id": seed_spool.filament_id,
            "initial_weight": 1000,
            "remaining_weight": 0,
        },
    )
    assert empty_response.status_code == 400


@pytest.mark.asyncio
async def test_spool_compat_gate_assignment_moves_one_physical_spool(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, first_spool, device = await _seed_spool_context(db_session)
    second_spool = UserSpool(
        user_id=user.id,
        filament_id=first_spool.filament_id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(second_spool)
    await db_session.commit()
    await db_session.refresh(second_spool)
    location = f"{device.name}:Gate0"

    first_response = await client.patch(
        f"/api/v1/spool_compat/{device.api_key}/v1/spool/{first_spool.id}",
        json={"location": location},
    )
    assert first_response.status_code == 200

    second_response = await client.patch(
        f"/api/v1/spool_compat/{device.api_key}/v1/spool/{second_spool.id}",
        json={"location": location},
    )
    assert second_response.status_code == 200
    await db_session.refresh(first_spool)
    await db_session.refresh(second_spool)
    assert first_spool.state == UserSpoolState.shelf
    assert first_spool.extra["printer_name"] == '""'
    assert first_spool.extra["mmu_gate_map"] == "-1"
    assert second_spool.state == UserSpoolState.active

    gate_spool_id = await db_session.scalar(
        select(PresetGateState.spool_id).where(
            PresetGateState.device_id == device.id,
            PresetGateState.gate_index == 0,
        )
    )
    assert gate_spool_id == second_spool.id

    shelf_response = await client.patch(
        f"/api/v1/spool_compat/{device.api_key}/v1/spool/{second_spool.id}",
        json={"location": None},
    )
    assert shelf_response.status_code == 200
    await db_session.refresh(second_spool)
    assert second_spool.state == UserSpoolState.shelf
    assert second_spool.extra["printer_name"] == '""'
    assert second_spool.extra["mmu_gate_map"] == "-1"


@pytest.mark.asyncio
async def test_hh_patch_bootstraps_hostname_then_exposes_existing_gate_map(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """The one-time HH assignment pairs the endpoint without user-entered hostname."""
    user, spool, device = await _seed_spool_context(db_session)
    gate_state = PresetGateState(
        user_id=user.id,
        device_id=device.id,
        gate_index=0,
        spool_id=spool.id,
        source=PresetGateStateSource.web_manual,
        source_ts=datetime.now(timezone.utc),
        is_active=True,
    )
    # Reproduce the pre-fix data shape: the friendly label was persisted as if
    # it were Happy Hare's actual hostname.
    spool.extra = {
        "printer_name": f'"{device.name}"',
        "mmu_gate_map": "0",
    }
    db_session.add(gate_state)
    await db_session.commit()

    endpoint = f"/api/v1/spool_compat/{device.api_key}/v1/spool/{spool.id}"
    before = await client.get(endpoint)
    assert before.status_code == 200
    assert before.json()["extra"]["printer_name"] == '""'
    assert before.json()["extra"]["mmu_gate_map"] == "-1"

    paired = await client.patch(
        endpoint,
        json={
            "location": "voron @ MMU Gate:0",
            "extra": {"printer_name": '"voron"', "mmu_gate_map": "0"},
        },
    )
    assert paired.status_code == 200
    await db_session.refresh(device)
    assert device.printer_hostname == "voron"

    after = await client.get(endpoint)
    assert after.status_code == 200
    assert after.json()["extra"]["printer_name"] == '"voron"'
    assert after.json()["extra"]["mmu_gate_map"] == "0"


@pytest.mark.asyncio
async def test_spool_compat_finished_spool_clears_gate(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _user, spool, device = await _seed_spool_context(db_session)
    endpoint = f"/api/v1/spool_compat/{device.api_key}/v1/spool/{spool.id}"
    assign_response = await client.patch(
        endpoint,
        json={"location": f"{device.name}:Gate0"},
    )
    assert assign_response.status_code == 200

    use_response = await client.put(f"{endpoint}/use", json={"use_weight": 900})
    assert use_response.status_code == 200
    await db_session.refresh(spool)
    assert spool.state == UserSpoolState.empty
    assert spool.extra["printer_name"] == '""'
    assert spool.extra["mmu_gate_map"] == "-1"
    gate_spool_id = await db_session.scalar(
        select(PresetGateState.spool_id).where(
            PresetGateState.device_id == device.id,
            PresetGateState.gate_index == 0,
        )
    )
    assert gate_spool_id is None


def _approved_preset(**overrides) -> Preset:
    base = {
        "name": "test preset",
        "extruder_temp": 240.0,
        "bed_temp": 80.0,
        "is_official": True,
        "active": True,
        "moderation_status": PresetModerationStatus.APPROVED,
    }
    base.update(overrides)
    return Preset(**base)


def test_filament_temps_uses_representative_preset():
    """Gate map temps must come from the filament's preset, not be None."""
    filament = Filament(name="PETG X", slug="petg-x", material_type="PETG")
    filament.presets = [
        _approved_preset(extruder_temp=245.0, bed_temp=85.0, rating=4.8, usage_count=10),
        _approved_preset(extruder_temp=230.0, bed_temp=70.0, rating=3.0, usage_count=2),
    ]
    assert _filament_temps(filament) == (245.0, 85.0)


def test_filament_temps_prefers_official_over_user_preset():
    filament = Filament(name="PLA Y", slug="pla-y", material_type="PLA")
    filament.presets = [
        _approved_preset(is_official=False, extruder_temp=200.0, bed_temp=55.0, rating=5.0),
        _approved_preset(is_official=True, extruder_temp=215.0, bed_temp=60.0, rating=4.0),
    ]
    assert _filament_temps(filament) == (215.0, 60.0)


def test_filament_temps_falls_back_to_material_defaults():
    """No preset → material defaults so Happy Hare never receives None."""
    filament = Filament(name="PETG Z", slug="petg-z", material_type="PETG")
    filament.presets = []
    extruder, bed = _filament_temps(filament)
    assert extruder == 240.0
    assert bed == 80.0


def test_filament_temps_ignores_unapproved_and_inactive_presets():
    filament = Filament(name="PLA W", slug="pla-w", material_type="PLA")
    filament.presets = [
        _approved_preset(moderation_status=PresetModerationStatus.PENDING, extruder_temp=999.0),
        _approved_preset(active=False, extruder_temp=999.0),
    ]
    # All candidates filtered out → material defaults for PLA.
    assert _filament_temps(filament) == (215.0, 60.0)


def test_filament_payload_never_emits_none_temps():
    """The Spoolman payload fields HH parses with int() must be numeric."""
    filament = Filament(name="ABS Q", slug="abs-q", material_type="ABS")
    filament.presets = []
    payload = _filament_payload(filament, fallback_id=1)
    assert payload["settings_extruder_temp"] is not None
    assert payload["settings_bed_temp"] is not None


def _spool_for_payload(filament: Filament) -> UserSpool:
    return UserSpool(
        id=2,
        filament=filament,
        initial_weight_g=1000.0,
        used_weight_g=100.0,
        state=UserSpoolState.active,
    )


def test_spool_payload_uses_gate_bound_preset_temp():
    """A preset bound to the gate must drive the gate-map temperatures."""
    filament = Filament(name="PETG G", slug="petg-g", material_type="PETG")
    filament.presets = []
    spool = _spool_for_payload(filament)
    gate_preset = _approved_preset(extruder_temp=250.0, bed_temp=90.0)
    location_map = {2: "Voron @ MMU Gate:4"}
    gate_meta_map = {2: ("Voron", 4, "voron", gate_preset)}

    payload = _to_spool_payload(spool, location_map, gate_meta_map)
    assert payload["filament"]["settings_extruder_temp"] == 250.0
    assert payload["filament"]["settings_bed_temp"] == 90.0


def test_spool_payload_gate_without_preset_uses_material_default():
    """Gate with a spool but no bound preset → material default, not the
    filament's representative preset."""
    filament = Filament(name="PETG H", slug="petg-h", material_type="PETG")
    filament.presets = [_approved_preset(extruder_temp=999.0, bed_temp=999.0)]
    spool = _spool_for_payload(filament)
    location_map = {2: "Voron @ MMU Gate:4"}
    gate_meta_map = {2: ("Voron", 4, "voron", None)}

    payload = _to_spool_payload(spool, location_map, gate_meta_map)
    assert payload["filament"]["settings_extruder_temp"] == 240.0
    assert payload["filament"]["settings_bed_temp"] == 80.0


def test_spool_payload_never_uses_display_name_as_hh_printer_name():
    """A friendly device label cannot be used as Happy Hare's hostname."""
    filament = Filament(name="PLA Pairing", slug="pla-pairing", material_type="PLA")
    filament.presets = []
    spool = _spool_for_payload(filament)
    spool.extra = {"printer_name": '"Living Room Voron"', "mmu_gate_map": "3"}
    location_map = {2: "Living Room Voron @ MMU Gate:3"}
    gate_meta_map = {2: ("Living Room Voron", 3, "", None)}

    payload = _to_spool_payload(spool, location_map, gate_meta_map)

    assert payload["extra"]["printer_name"] == '""'
    assert payload["extra"]["mmu_gate_map"] == "-1"


def test_spool_payload_uses_authoritative_hh_hostname_after_pairing():
    filament = Filament(name="PLA Paired", slug="pla-paired", material_type="PLA")
    filament.presets = []
    spool = _spool_for_payload(filament)
    spool.extra = {"printer_name": '"Living Room Voron"', "mmu_gate_map": "3"}
    location_map = {2: "Living Room Voron @ MMU Gate:3"}
    gate_meta_map = {2: ("Living Room Voron", 3, "voron", None)}

    payload = _to_spool_payload(spool, location_map, gate_meta_map)

    assert payload["extra"]["printer_name"] == '"voron"'
    assert payload["extra"]["mmu_gate_map"] == "3"


def test_spool_payload_ungated_uses_representative_preset():
    """A spool not on any gate falls back to the filament's representative preset."""
    filament = Filament(name="PETG I", slug="petg-i", material_type="PETG")
    filament.presets = [_approved_preset(extruder_temp=248.0, bed_temp=88.0)]
    spool = _spool_for_payload(filament)

    payload = _to_spool_payload(spool, {}, {})
    assert payload["filament"]["settings_extruder_temp"] == 248.0
    assert payload["filament"]["settings_bed_temp"] == 88.0
