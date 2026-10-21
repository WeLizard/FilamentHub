"""Client contract regressions for inventory compatibility."""

import json
import math

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.preset_gate_state import PresetGateState
from app.models.preset_usage_event import PresetUsageEvent
from app.models.user_spool import UserSpool
from tests.spool_compat_test import _seed_spool_context


async def _pending_chain(client, device):
    base = f"/api/v1/spool_compat/{device.api_key}/v1"
    vendor = await client.post(f"{base}/vendor", json={"name": "Private NFC supplier"})
    assert vendor.status_code in {200, 201}, vendor.text
    filament = await client.post(f"{base}/filament", json={
        "name": "Unknown NFC PETG", "vendor_id": vendor.json()["id"],
        "material": "PETG", "density": 1.27, "diameter": 2.85,
        "weight": 750, "spool_weight": 220, "external_id": "nonunique-sku",
        "extra": {"orca_flow_ratio": "0.98"},
    })
    assert filament.status_code in {200, 201}, filament.text
    spool = await client.post(f"{base}/spool", json={
        "filament_id": filament.json()["id"], "price": 14.5,
        "first_used": "2026-10-01T12:00:00Z", "last_used": "2026-10-02T12:00:00Z",
    })
    assert spool.status_code in {200, 201}, spool.text
    return base, filament.json(), spool.json()


@pytest.mark.asyncio
async def test_legacy_unmatched_vendor_name_filter_uses_preserved_source(client, db_session):
    user, _, device = await _seed_spool_context(db_session)
    spool = UserSpool(
        user_id=user.id, filament_id=None, initial_weight_g=1000, used_weight_g=0,
        source="spoolmanager", extra={"vendor": "Legacy Private Supplier", "material": "PLA"},
    )
    db_session.add(spool)
    await db_session.commit()
    base = f"/api/v1/spool_compat/{device.api_key}/v1"
    found = await client.get(f"{base}/spool", params={"vendor_name": "Legacy Private Supplier"})
    assert found.status_code == 200
    assert [row["id"] for row in found.json()] == [spool.id]
    missing = await client.get(f"{base}/spool", params={"vendor_name": "Absent legacy vendor"})
    assert missing.status_code == 200 and missing.json() == []


@pytest.mark.asyncio
async def test_hh_pending_chain_usage_resolution_preserves_ids_and_evidence(client, db_session):
    user, original, device = await _seed_spool_context(db_session)
    from tests.conftest import accepted_legal

    for key, value in accepted_legal().items():
        setattr(user, key, value)
    await db_session.commit()
    base, material, spool = await _pending_chain(client, device)
    assert spool["filament"]["id"] == material["id"]
    assert spool["price"] == 14.5
    assert spool["first_used"].startswith("2026-10-01T12:00:00")
    assert spool["last_used"].startswith("2026-10-02T12:00:00")
    assert spool["spool_weight"] == 220
    used = await client.put(f"{base}/spool/{spool['id']}/use", json={"use_length": 1000})
    assert used.status_code == 200, used.text
    expected = math.pi * (2.85 / 2) ** 2 * 1.27
    assert used.json()["used_weight"] == pytest.approx(expected, abs=.001)
    event = await db_session.scalar(select(PresetUsageEvent).where(
        PresetUsageEvent.spool_id == spool["id"]
    ))
    assert event.meta["density_g_cm3"] == 1.27
    assert event.meta["diameter_mm"] == 2.85
    saved_delta = event.delta_weight_g
    physical = await db_session.get(UserSpool, spool["id"])
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}
    detail = await client.get(f"/api/v1/spools/imports/{physical.compat_filament_ref_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    endpoint = f"/api/v1/spools/imports/{physical.compat_filament_ref_id}/resolve"
    resolved = await client.post(endpoint, headers=headers, json={
        "filament_id": original.filament_id, "expected_revision": detail.json()["revision"],
    })
    assert resolved.status_code == 200, resolved.text
    stale = await client.post(endpoint, headers=headers, json={
        "filament_id": original.filament_id, "expected_revision": detail.json()["revision"],
    })
    assert stale.status_code == 409
    read = await client.get(f"{base}/spool/{spool['id']}")
    assert read.json()["filament"]["id"] == material["id"]
    assert read.json()["filament"]["extra"]["orca_flow_ratio"] == "0.98"
    await db_session.refresh(event)
    assert event.delta_weight_g == saved_delta
    assert event.meta["diameter_mm"] == 2.85


@pytest.mark.asyncio
async def test_individual_tare_precedes_import_and_unknown_tare_rejects_measurement(client, db_session):
    _, original, device = await _seed_spool_context(db_session)
    base, _, spool = await _pending_chain(client, device)
    patched = await client.patch(f"{base}/spool/{spool['id']}", json={"spool_weight": 180})
    assert patched.status_code == 200, patched.text
    measured = await client.put(f"{base}/spool/{spool['id']}/measure", json={"weight": 500})
    assert measured.status_code == 200, measured.text
    assert measured.json()["remaining_weight"] == 320
    no_tare = await client.put(f"{base}/spool/{original.id}/measure", json={"weight": 500})
    assert no_tare.status_code == 400
    await db_session.refresh(original)
    assert original.used_weight_g == 100


@pytest.mark.asyncio
async def test_pending_material_filters_and_sql_pagination(client, db_session):
    _, _, device = await _seed_spool_context(db_session)
    base, material, spool = await _pending_chain(client, device)
    response = await client.get(f"{base}/spool", params={
        "filament.id": str(material["id"]), "filament.vendor.name": "Private NFC",
        "limit": 1, "offset": 0,
    })
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()] == [spool["id"]]
    assert response.headers["x-total-count"] == "1"
    empty = await client.get(f"{base}/spool", params={
        "filament.id": str(material["id"]), "limit": 1, "offset": 1,
    })
    assert empty.json() == []
    assert empty.headers["x-total-count"] == "1"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["catalog", "group"])
async def test_preview_token_rejects_changed_catalog_or_spool_group(client, db_session, change):
    from app.models.filament import Filament
    from tests.conftest import accepted_legal

    user, target_spool, device = await _seed_spool_context(db_session)
    for key, value in accepted_legal().items():
        setattr(user, key, value)
    await db_session.commit()
    base, material, spool = await _pending_chain(client, device)
    physical = await db_session.get(UserSpool, spool["id"])
    endpoint = f"/api/v1/spools/imports/{physical.compat_filament_ref_id}"
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}
    target = {"filament_id": target_spool.filament_id}
    preview = await client.post(f"{endpoint}/preview", headers=headers, json=target)
    assert preview.status_code == 200, preview.text
    if change == "catalog":
        catalog = await db_session.get(Filament, target_spool.filament_id)
        catalog.density = 1.6
        await db_session.commit()
    else:
        added = await client.post(f"{base}/spool", json={"filament_id": material["id"]})
        assert added.status_code == 200, added.text
    rejected = await client.post(f"{endpoint}/resolve", headers=headers, json={
        **target, "expected_revision": preview.json()["revision"],
        "preview_token": preview.json()["preview_token"],
    })
    assert rejected.status_code == 409, rejected.text
    await db_session.refresh(physical)
    assert physical.filament_id is None
    fresh = await client.post(f"{endpoint}/preview", headers=headers, json=target)
    accepted = await client.post(f"{endpoint}/resolve", headers=headers, json={
        **target, "expected_revision": fresh.json()["revision"],
        "preview_token": fresh.json()["preview_token"],
    })
    assert accepted.status_code == 200, accepted.text


@pytest.mark.asyncio
async def test_custom_extra_patch_keeps_the_physical_assignment(
    client: AsyncClient, db_session: AsyncSession
):
    _, spool, device = await _seed_spool_context(db_session)
    url = f"/api/v1/spool_compat/{device.api_key}/v1/spool/{spool.id}"
    assert (await client.patch(url, json={"location": "voron:Gate0"})).status_code == 200
    # Assignment is canonical; imported metadata need not contain HH's mirror.
    await db_session.refresh(spool)
    spool.extra = {}
    await db_session.commit()

    response = await client.patch(url, json={"extra": {"note": json.dumps("keep this spool")}})

    assert response.status_code == 200
    gate = await db_session.scalar(
        select(PresetGateState).where(
            PresetGateState.device_id == device.id, PresetGateState.gate_index == 0
        )
    )
    assert gate is not None and gate.spool_id == spool.id


@pytest.mark.asyncio
@pytest.mark.parametrize("gate_value", ["999", '"broken"', "1.5", "true", "-2"])
async def test_invalid_extra_gate_rejects_the_entire_patch(
    client: AsyncClient, db_session: AsyncSession, gate_value: str
):
    _, spool, device = await _seed_spool_context(db_session)
    url = f"/api/v1/spool_compat/{device.api_key}/v1/spool/{spool.id}"
    assert (await client.patch(url, json={"location": "voron:Gate0"})).status_code == 200
    response = await client.patch(
        url,
        json={
            "remaining_weight": 123,
            "extra": {"printer_name": '"voron"', "mmu_gate_map": gate_value},
        },
    )
    assert response.status_code == 400
    await db_session.refresh(spool)
    assert spool.used_weight_g == 100
    gate = await db_session.scalar(
        select(PresetGateState).where(
            PresetGateState.device_id == device.id, PresetGateState.gate_index == 0
        )
    )
    assert gate is not None and gate.spool_id == spool.id


@pytest.mark.asyncio
async def test_null_extra_value_removes_only_the_named_key(
    client: AsyncClient, db_session: AsyncSession
):
    _, spool, device = await _seed_spool_context(db_session)
    spool.extra = {"keep": '"a"', "remove": '"b"'}
    await db_session.commit()
    response = await client.patch(
        f"/api/v1/spool_compat/{device.api_key}/v1/spool/{spool.id}",
        json={"extra": {"remove": None}},
    )
    assert response.status_code == 200
    assert response.json()["extra"]["keep"] == '"a"'
    assert "remove" not in response.json()["extra"]
