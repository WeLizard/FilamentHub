"""Regression tests for the provider-neutral physical printer contract."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice


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
