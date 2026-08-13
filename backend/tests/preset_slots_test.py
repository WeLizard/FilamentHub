"""Tests for preset-slot assignment behavior."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.printer_connection_binding import PrinterConnectionBinding
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


@pytest.mark.asyncio
async def test_hh_snapshot_cannot_target_another_users_physical_printer(
    client: AsyncClient,
):
    owner_headers, _ = await _register_and_login(client, "hh-owned-printer")
    intruder_headers, _ = await _register_and_login(client, "hh-foreign-printer")

    heartbeat_response = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/device/heartbeat",
        json={
            "device_fingerprint": "device-hh-owned-printer",
            "device_name": "Owned Happy Hare",
            "supports_hh": True,
            "gate_count": 6,
        },
        headers=owner_headers,
    )
    assert heartbeat_response.status_code == 200
    physical_printer_id = heartbeat_response.json()["device_id"]

    response = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/hh/snapshot",
        json={
            "physical_printer_id": physical_printer_id,
            "gate_count": 6,
            "snapshot_ts": "2026-08-13T00:00:00Z",
            "gates": [],
        },
        headers=intruder_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_DEVICE_NOT_OWNER"


@pytest.mark.asyncio
async def test_plugin_material_topology_is_minimal_scoped_and_owned(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner_headers, owner_email = await _register_and_login(
        client, "plugin-topology-owner"
    )
    foreign_headers, _ = await _register_and_login(
        client, "plugin-topology-foreign"
    )
    source_instance_id = "orca-plugin-instance-123456"

    owner_device = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/device/heartbeat",
        json={
            "device_fingerprint": "plugin-topology-owned-device",
            "device_name": "Workshop Voron",
            "supports_hh": True,
            "gate_count": 2,
        },
        headers=owner_headers,
    )
    assert owner_device.status_code == 200
    owner_device_id = owner_device.json()["device_id"]

    foreign_device = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/device/heartbeat",
        json={
            "device_fingerprint": "plugin-topology-foreign-device",
            "device_name": "Foreign Voron",
            "supports_hh": True,
            "gate_count": 4,
        },
        headers=foreign_headers,
    )
    assert foreign_device.status_code == 200
    foreign_device_id = foreign_device.json()["device_id"]

    owner = (
        await db_session.execute(select(User).where(User.email == owner_email))
    ).scalar_one()
    db_session.add(
        PrinterConnectionBinding(
            user_id=owner.id,
            physical_printer_id=owner_device_id,
            source="orcaslicer_plugin",
            source_instance_id=source_instance_id,
            connection_ref="fh-local-profile-ref-1",
            normalized_endpoint="ref:fixture-owned-binding",
            provider="moonraker",
        )
    )
    await db_session.commit()

    issued = await client.post(
        "/api/v1/auth/plugin-session", json={}, headers=owner_headers
    )
    assert issued.status_code == 200
    plugin_headers = {
        "Authorization": f"Bearer {issued.json()['plugin_token']}"
    }
    context = await client.get(
        "/api/v1/orcaslicer/preset-slot-sync/plugin-context",
        params={"source_instance_id": source_instance_id},
        headers=plugin_headers,
    )

    assert context.status_code == 200
    payload = context.json()
    assert payload["source_instance_id"] == source_instance_id
    assert [printer["id"] for printer in payload["printers"]] == [owner_device_id]
    printer = payload["printers"][0]
    assert printer["connection_refs"] == ["fh-local-profile-ref-1"]
    assert [slot["provider_index"] for slot in printer["material_systems"][0]["slots"]] == [0, 1]
    serialized = str(payload)
    assert "Workshop Voron" not in serialized
    assert "normalized_endpoint" not in serialized
    assert "print_host" not in serialized
    assert "printer_hostname" not in serialized

    other_install = await client.get(
        "/api/v1/orcaslicer/preset-slot-sync/plugin-context",
        params={"source_instance_id": "another-orca-instance-654321"},
        headers=plugin_headers,
    )
    assert other_install.status_code == 200
    assert other_install.json()["printers"][0]["connection_refs"] == []

    browser_context = await client.get(
        "/api/v1/orcaslicer/preset-slot-sync/plugin-context",
        params={"source_instance_id": source_instance_id},
        headers=owner_headers,
    )
    assert browser_context.status_code == 200

    from app.core.security import create_plugin_token

    old_scope_token = create_plugin_token(
        {"sub": owner.email, "user_id": owner.id},
        ["presets:read", "presets:write", "printer-bundles:read"],
    )
    missing_scope = await client.get(
        "/api/v1/orcaslicer/preset-slot-sync/plugin-context",
        params={"source_instance_id": source_instance_id},
        headers={"Authorization": f"Bearer {old_scope_token}"},
    )
    assert missing_scope.status_code == 403
    assert missing_scope.json()["detail"]["code"] == "ERR_ACCESS_DENIED"

    broad_account_api = await client.get(
        "/api/v1/physical-printers", headers=plugin_headers
    )
    assert broad_account_api.status_code == 401

    owned_snapshot = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/hh/snapshot",
        json={
            "physical_printer_id": owner_device_id,
            "gate_count": 2,
            "snapshot_ts": "2026-08-13T00:00:00Z",
            "gates": [],
        },
        headers=plugin_headers,
    )
    assert owned_snapshot.status_code == 200

    foreign_snapshot = await client.post(
        "/api/v1/orcaslicer/preset-slot-sync/hh/snapshot",
        json={
            "physical_printer_id": foreign_device_id,
            "gate_count": 4,
            "snapshot_ts": "2026-08-13T00:00:00Z",
            "gates": [],
        },
        headers=plugin_headers,
    )
    assert foreign_snapshot.status_code == 403
    assert foreign_snapshot.json()["detail"]["code"] == "ERR_DEVICE_NOT_OWNER"
