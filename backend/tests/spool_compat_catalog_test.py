"""Vendor and filament transport references stay private and stable."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import spool_compat_catalog
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset
from app.models.spool_compat_resource import SpoolCompatResource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_saved_preset import UserSavedPreset
from app.services.spool_compat_resource_service import CompatRevisionConflict, resolve_import


@pytest.mark.asyncio
async def test_vendor_filament_chain_and_private_extras(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    first = User(email="catalog-wire-first@example.com", username="catalogwirefirst",
                 password_hash="unused", active=True)
    second = User(email="catalog-wire-second@example.com", username="catalogwiresecond",
                  password_hash="unused", active=True)
    devices = [UserPrinterDevice(user=user, name=f"device-{index}",
        device_fingerprint=f"catalog-wire-{index}", api_key=f"catalog-wire-key-{index}", supports_hh=True)
        for index, user in enumerate((first, second))]
    brand = Brand(name="Catalog Wire Brand", slug="catalog-wire-brand", active=True)
    filament = Filament(brand=brand, name="Catalog Wire PLA", slug="catalog-wire-pla",
        material_type="PLA", color_name="Black", color_hex="#111111", diameter=1.75,
        density=1.24, spool_weight=1000, active=True)
    db_session.add_all([first, second, *devices, brand, filament])
    await db_session.commit()
    base = "/api/v1/spool_compat"
    first_key, second_key = (device.api_key for device in devices)

    vendors = (await client.get(f"{base}/{first_key}/v1/vendor")).json()
    catalog_vendor = next(vendor for vendor in vendors if vendor["name"] == brand.name)
    assert catalog_vendor["id"] > 0
    assert (await client.get(f"{base}/api/v1/vendor", headers={"X-API-Key": first_key})).status_code == 200
    assert (await client.get(f"{base}/v1/vendor", params={"api_key": first_key})).status_code == 200
    assert (await client.get(f"{base}/v1/vendor")).status_code == 401
    created_vendor = await client.post(f"{base}/{first_key}/v1/vendor", json={
        "name": "Unmapped Maker", "external_id": "", "extra": {"source": "hh"}})
    assert created_vendor.status_code == 201
    vendor_id = created_vendor.json()["id"]
    created_filament = await client.post(f"{base}/{first_key}/v1/filament", json={
        "name": "Unmapped PLA", "vendor_id": vendor_id, "material": "PLA",
        "external_id": "source-1", "extra": {"source": "hh"}})
    assert created_filament.status_code == 201
    filament_id = created_filament.json()["id"]
    assert created_filament.json()["vendor"]["id"] == vendor_id
    assert (await client.get(f"{base}/{first_key}/api/v1/filament/{filament_id}")).json()["id"] == filament_id
    assert (await client.get(f"{base}/{second_key}/v1/filament/{filament_id}")).status_code == 404
    assert (await client.get(f"{base}/{second_key}/v1/vendor/{vendor_id}")).status_code == 404
    filtered = (await client.get(f"{base}/{first_key}/v1/filament", params={
        "external_id": "source-1", "vendor.id": vendor_id})).json()
    assert [entry["id"] for entry in filtered] == [filament_id]
    by_vendor_name = (await client.get(f"{base}/{first_key}/v1/filament", params={
        "vendor_name": "Unmapped Maker"})).json()
    assert [entry["id"] for entry in by_vendor_name] == [filament_id]
    assert (await client.get(f"{base}/{first_key}/v1/filament", params={"external_id": "missing"})).json() == []
    assert (await client.get(f"{base}/{first_key}/v1/vendor", params={"external_id": ""})).json()[0]["id"] == vendor_id
    assert [item["id"] for item in (await client.get(f"{base}/{first_key}/v1/vendor",
        params={"name": 'Missing,"Unmapped Maker"'})).json()] == [vendor_id]
    assert (await client.get(f"{base}/{first_key}/v1/vendor",
        params={"name": '"Unmapped"'})).json() == []
    assert [item["id"] for item in (await client.get(f"{base}/{first_key}/v1/filament",
        params={"material": 'PETG,"PLA"', "vendor_name": '"Unmapped Maker"'})).json()] == [filament_id]

    patched = await client.patch(f"{base}/{first_key}/v1/vendor/{catalog_vendor['id']}",
        json={"extra": {"private": "yes", "remove": "temporary"}})
    assert patched.status_code == 200
    assert (await client.patch(f"{base}/{first_key}/v1/vendor/{catalog_vendor['id']}",
        json={"extra": {"remove": None}})).json()["extra"] == {"private": "yes"}
    assert (await client.get(f"{base}/{second_key}/v1/vendor/{catalog_vendor['id']}")).json()["extra"] == {}
    assert (await client.patch(f"{base}/{first_key}/v1/vendor/{catalog_vendor['id']}",
        json={"name": "Wrong"})).status_code == 403
    assert brand.name == "Catalog Wire Brand"

    updated = await client.patch(f"{base}/{first_key}/v1/filament/{filament_id}",
        json={"name": "Unmapped PLA revised", "extra": {"private": 1}})
    assert updated.status_code == 200
    ref = await db_session.scalar(select(SpoolCompatResource).where(
        SpoolCompatResource.kind == "filament", SpoolCompatResource.wire_id == filament_id))
    assert ref.original_payload["name"] == "Unmapped PLA"
    assert ref.latest_payload["name"] == "Unmapped PLA revised"
    assert await db_session.scalar(select(Preset.id).where(Preset.user_id == first.id)) is None

    with_settings = await client.post(f"{base}/{first_key}/v1/filament", json={
        "name": "HH tuned", "vendor_id": vendor_id, "settings_extruder_temp": 215})
    assert with_settings.status_code == 201
    draft = await db_session.scalar(select(Preset).where(Preset.user_id == first.id))
    saved = await db_session.scalar(select(UserSavedPreset).where(UserSavedPreset.preset_id == draft.id))
    assert draft.active is False and saved.sync is False
    assert draft.extruder_temp == 215 and draft.bed_temp == 0
    assert (await client.post(f"{base}/{first_key}/v1/filament", json={
        "name": "Invalid", "settings_extruder_temp": "hot"})).status_code == 400

    async def lost_revision(*args, **kwargs):
        raise CompatRevisionConflict("raced")

    monkeypatch.setattr(spool_compat_catalog, "update_import_ref", lost_revision)
    conflict = await client.patch(f"{base}/{first_key}/v1/filament/{filament_id}",
        json={"name": "Concurrent update"})
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_pending_filament_optional_fields_and_vendor_tare(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user = User(email="spool-tare@example.com", username="spooltare",
                password_hash="unused", active=True)
    device = UserPrinterDevice(user=user, name="Tare printer", device_fingerprint="tare-printer",
                               api_key="tare-test-key", supports_hh=True)
    db_session.add_all([user, device])
    await db_session.commit()
    base = f"/api/v1/spool_compat/{device.api_key}/v1"

    vendorless = await client.post(f"{base}/filament", json={
        "name": "Vendorless", "material": "PLA", "extra": {"literal_null": "null"}})
    assert vendorless.status_code == 201
    assert "vendor" not in vendorless.json() and "color_hex" not in vendorless.json()
    assert vendorless.json()["extra"] == {"literal_null": "null"}
    vendor = await client.post(f"{base}/vendor", json={
        "name": "Tare Maker", "empty_spool_weight": 200})
    assert vendor.status_code == 201
    vendor_id = vendor.json()["id"]
    assert "comment" not in vendor.json()
    filament = await client.post(f"{base}/filament", json={
        "name": "Tare PLA", "material": "PLA", "vendor_id": vendor_id,
        "weight": 1000})
    assert filament.status_code == 201
    filament_id = filament.json()["id"]
    assert filament.json()["spool_weight"] == 200
    spool = await client.post(f"{base}/spool", json={
        "filament_id": filament_id, "initial_weight": 1000})
    assert spool.status_code == 200
    spool_id = spool.json()["id"]
    first_measure = await client.put(f"{base}/spool/{spool_id}/measure", json={"weight": 1050})
    assert first_measure.status_code == 200
    assert first_measure.json()["remaining_weight"] == pytest.approx(850)

    vendor_patch = await client.patch(f"{base}/vendor/{vendor_id}", json={"empty_spool_weight": 250})
    assert vendor_patch.status_code == 200
    assert (await client.get(f"{base}/filament/{filament_id}")).json()["spool_weight"] == 250
    second_measure = await client.put(f"{base}/spool/{spool_id}/measure", json={"weight": 1050})
    assert second_measure.status_code == 200
    assert second_measure.json()["remaining_weight"] == pytest.approx(800)

    filament_patch = await client.patch(f"{base}/filament/{filament_id}", json={"spool_weight": 0})
    assert filament_patch.status_code == 200
    assert filament_patch.json()["spool_weight"] == 0
    third_measure = await client.put(f"{base}/spool/{spool_id}/measure", json={"weight": 1000})
    assert third_measure.status_code == 200
    assert third_measure.json()["remaining_weight"] == pytest.approx(1000)

    catalog_brand = Brand(name="Resolved Tare Brand", slug="resolved-tare-brand", active=True)
    catalog_filament = Filament(brand=catalog_brand, name="Resolved PLA", slug="resolved-pla",
        material_type="PLA", color_name="White", color_hex="#FFFFFF", diameter=1.75,
        density=1.24, spool_weight=1000, empty_spool_weight_g=70, active=True)
    db_session.add(catalog_filament)
    await db_session.flush()
    imported_ref = await db_session.scalar(select(SpoolCompatResource).where(
        SpoolCompatResource.kind == "filament", SpoolCompatResource.wire_id == filament_id))
    await resolve_import(db_session, user_id=user.id, import_ref_id=imported_ref.id,
                         target_catalog_id=catalog_filament.id, expected_revision=imported_ref.revision)
    await db_session.commit()
    resolved = await client.get(f"{base}/filament/{filament_id}")
    assert resolved.status_code == 200
    assert resolved.json()["spool_weight"] == 70
