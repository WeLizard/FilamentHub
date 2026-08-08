"""Tests for preset-slot assignment behavior."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from tests.conftest import registration_payload


async def _register_and_login(
    client: AsyncClient,
    suffix: str,
) -> tuple[dict[str, str], str]:
    email = f"{suffix}@example.com"
    password = "testpassword123"

    register_response = await client.post(
        "/api/v1/auth/register",
        json=registration_payload(email=email, username=f"user_{suffix}", password=password, role="user"),
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


@pytest.mark.asyncio
async def test_slot_spool_update_does_not_clear_existing_preset(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers, email = await _register_and_login(client, "slot-preserve-preset")

    user_result = await db_session.execute(select(User).where(User.email == email))
    user = user_result.scalar_one()

    brand = Brand(name="HH Test Brand", slug="hh-test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name="HH Test Filament",
        slug="hh-test-filament",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    preset = Preset(
        filament_id=filament.id,
        user_id=user.id,
        name="HH Slot Preset",
        is_official=False,
        extruder_temp=210.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add(preset)

    spool = UserSpool(
        user_id=user.id,
        filament_id=filament.id,
        initial_weight_g=1000.0,
        used_weight_g=0.0,
        state=UserSpoolState.active,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(preset)
    await db_session.refresh(spool)

    heartbeat_response = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/device/heartbeat",
        json={
            "device_fingerprint": "device-slot-test-1",
            "device_name": "Device Slot Test",
            "supports_hh": True,
            "gate_count": 8,
        },
        headers=headers,
    )
    assert heartbeat_response.status_code == 200
    device_id = heartbeat_response.json()["device_id"]

    # 1) Assign preset only.
    assign_preset_response = await client.patch(
        f"/api/v1/preset-slots/{device_id}/0",
        json={"preset_id": preset.id},
        headers=headers,
    )
    assert assign_preset_response.status_code == 200
    assert assign_preset_response.json()["preset_id"] == preset.id
    assert assign_preset_response.json()["spool_id"] is None

    # 2) Update spool only (preset must be preserved).
    assign_spool_response = await client.patch(
        f"/api/v1/preset-slots/{device_id}/0",
        json={"spool_id": spool.id},
        headers=headers,
    )
    assert assign_spool_response.status_code == 200
    assert assign_spool_response.json()["preset_id"] == preset.id
    assert assign_spool_response.json()["spool_id"] == spool.id

    list_response = await client.get(
        f"/api/v1/preset-slots?device_id={device_id}",
        headers=headers,
    )
    assert list_response.status_code == 200
    state_gate_0 = next((s for s in list_response.json() if s["gate_index"] == 0), None)
    assert state_gate_0 is not None
    assert state_gate_0["preset_id"] == preset.id
    assert state_gate_0["spool_id"] == spool.id

    # 3) Explicit clear should null both preset and spool.
    clear_response = await client.patch(
        f"/api/v1/preset-slots/{device_id}/0",
        json={"preset_id": None, "spool_id": None},
        headers=headers,
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["preset_id"] is None
    assert clear_response.json()["spool_id"] is None


@pytest.mark.asyncio
async def test_assign_slot_rejects_foreign_spool_id(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner_headers, _ = await _register_and_login(client, "slot-owner")
    foreign_headers, foreign_email = await _register_and_login(client, "slot-foreign")

    foreign_result = await db_session.execute(select(User).where(User.email == foreign_email))
    foreign_user = foreign_result.scalar_one()

    brand = Brand(name="HH Foreign Brand", slug="hh-foreign-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name="HH Foreign Filament",
        slug="hh-foreign-filament",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)

    foreign_spool = UserSpool(
        user_id=foreign_user.id,
        filament_id=filament.id,
        initial_weight_g=750.0,
        used_weight_g=10.0,
        state=UserSpoolState.active,
        source="manual",
    )
    db_session.add(foreign_spool)
    await db_session.commit()
    await db_session.refresh(foreign_spool)

    heartbeat_response = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/device/heartbeat",
        json={
            "device_fingerprint": "device-owner-foreign-spool",
            "device_name": "Device Owner",
            "supports_hh": True,
            "gate_count": 4,
        },
        headers=owner_headers,
    )
    assert heartbeat_response.status_code == 200
    device_id = heartbeat_response.json()["device_id"]

    assign_response = await client.patch(
        f"/api/v1/preset-slots/{device_id}/1",
        json={"spool_id": foreign_spool.id},
        headers=owner_headers,
    )

    assert assign_response.status_code == 404
    detail = assign_response.json()["detail"]
    assert detail["code"] == "ERR_SPOOL_NOT_ACCESSIBLE"

    # Foreign user still can use their own spool without errors.
    foreign_heartbeat = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/device/heartbeat",
        json={
            "device_fingerprint": "device-foreign-self",
            "device_name": "Device Foreign",
            "supports_hh": True,
            "gate_count": 4,
        },
        headers=foreign_headers,
    )
    assert foreign_heartbeat.status_code == 200


@pytest.mark.asyncio
async def test_usage_estimate_rejects_foreign_spool_id(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner_headers, owner_email = await _register_and_login(client, "usage-owner")
    _, foreign_email = await _register_and_login(client, "usage-foreign")

    owner_result = await db_session.execute(select(User).where(User.email == owner_email))
    owner = owner_result.scalar_one()
    foreign_result = await db_session.execute(select(User).where(User.email == foreign_email))
    foreign_user = foreign_result.scalar_one()

    brand = Brand(name="HH Usage Brand", slug="hh-usage-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name="HH Usage Filament",
        slug="hh-usage-filament",
        material_type="PETG",
        active=True,
    )
    db_session.add(filament)

    preset = Preset(
        filament_id=filament.id,
        user_id=owner.id,
        name="HH Usage Preset",
        is_official=False,
        extruder_temp=235.0,
        bed_temp=80.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add(preset)

    foreign_spool = UserSpool(
        user_id=foreign_user.id,
        filament_id=filament.id,
        initial_weight_g=1000.0,
        used_weight_g=100.0,
        state=UserSpoolState.active,
        source="manual",
    )
    db_session.add(foreign_spool)
    await db_session.commit()
    await db_session.refresh(preset)
    await db_session.refresh(foreign_spool)

    heartbeat_response = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/device/heartbeat",
        json={
            "device_fingerprint": "device-usage-owner",
            "device_name": "Usage Owner Device",
            "supports_hh": True,
            "gate_count": 8,
        },
        headers=owner_headers,
    )
    assert heartbeat_response.status_code == 200

    estimate_response = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/usage/estimate",
        json={
            "device_fingerprint": "device-usage-owner",
            "preset_id": preset.id,
            "spool_id": foreign_spool.id,
            "delta_weight_g": 12.5,
            "job_ref": "job-123",
        },
        headers=owner_headers,
    )

    assert estimate_response.status_code == 404
    detail = estimate_response.json()["detail"]
    assert detail["code"] == "ERR_SPOOL_NOT_ACCESSIBLE"


@pytest.mark.asyncio
async def test_hh_snapshot_rejects_gate_index_out_of_range(
    client: AsyncClient,
):
    headers, _ = await _register_and_login(client, "hh-range")

    response = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/hh/snapshot",
        json={
            "device_fingerprint": "device-hh-range",
            "gate_count": 2,
            "snapshot_ts": "2026-02-27T00:00:00Z",
            "gates": [
                {"gate": 0, "status": 1, "material": "PLA", "color_hex": "#FFFFFF", "temperature": 210},
                {"gate": 2, "status": 1, "material": "PLA", "color_hex": "#000000", "temperature": 210},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 422
