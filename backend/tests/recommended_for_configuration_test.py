"""Catalog recommendations resolved through the printer→configuration chain.

The configuration (PrinterProfile) resolves the catalog printer context on the
backend; a supplied physical printer must belong to the user and be linked to
the configuration. The connection endpoint is never involved.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.preset import Preset
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice

URL = "/api/v1/presets/recommended-for-configuration"


async def _catalog_printer(db: AsyncSession) -> Printer:
    printer = Printer(
        name="Voron 2.4 350",
        manufacturer="Voron",
        model="2.4 350",
        slug="voron-2-4-350",
        nozzle_diameter=0.4,
        build_volume_x=350,
        build_volume_y=350,
        build_volume_z=350,
    )
    db.add(printer)
    await db.commit()
    await db.refresh(printer)
    return printer


async def _profile(
    db: AsyncSession, user: User, catalog_id: int | None, suffix: str = "04"
) -> PrinterProfile:
    profile = PrinterProfile(
        owner_user_id=user.id,
        printer_id=catalog_id,
        name=f"Voron 2.4 350 · {suffix}",
        slug=f"voron-2-4-350-{suffix}",
        nozzle_diameters=[0.4],
        active=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def _device(db: AsyncSession, user: User, name: str = "My Voron") -> UserPrinterDevice:
    device = UserPrinterDevice(user_id=user.id, name=name)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def _link(db: AsyncSession, user: User, device_id: int, profile_id: int) -> None:
    db.add(
        UserPrinterProfileLink(
            user_id=user.id, physical_printer_id=device_id, printer_profile_id=profile_id
        )
    )
    await db.commit()


async def _preset_for(db: AsyncSession, catalog: Printer) -> Preset:
    preset = Preset(
        name="Voron PLA 210/60",
        extruder_temp=210,
        bed_temp=60,
        is_official=True,
        active=True,
    )
    preset.printer_links = [PresetPrinter(printer=catalog, is_primary=True)]
    db.add(preset)
    await db.commit()
    return preset


@pytest.mark.asyncio
async def test_config_resolves_catalog_and_recommends(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    catalog = await _catalog_printer(db_session)
    await _preset_for(db_session, catalog)
    profile = await _profile(db_session, auth_user, catalog.id)

    resp = await auth_client.get(URL, params={"printer_profile_id": profile.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["printer_id"] == catalog.id
    assert body["printer_name"] == "Voron 2.4 350"
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_unbound_config_still_recommends(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    # No physical printer at all — the config alone drives recommendations.
    catalog = await _catalog_printer(db_session)
    await _preset_for(db_session, catalog)
    profile = await _profile(db_session, auth_user, catalog.id)

    resp = await auth_client.get(URL, params={"printer_profile_id": profile.id})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


@pytest.mark.asyncio
async def test_linked_physical_printer_ok(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    catalog = await _catalog_printer(db_session)
    await _preset_for(db_session, catalog)
    profile = await _profile(db_session, auth_user, catalog.id)
    device = await _device(db_session, auth_user)
    await _link(db_session, auth_user, device.id, profile.id)

    resp = await auth_client.get(
        URL, params={"printer_profile_id": profile.id, "physical_printer_id": device.id}
    )
    assert resp.status_code == 200
    assert resp.json()["printer_id"] == catalog.id


@pytest.mark.asyncio
async def test_physical_printer_must_be_linked(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    catalog = await _catalog_printer(db_session)
    profile = await _profile(db_session, auth_user, catalog.id)
    device = await _device(db_session, auth_user)  # not linked to the profile

    resp = await auth_client.get(
        URL, params={"printer_profile_id": profile.id, "physical_printer_id": device.id}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_LINKED"


@pytest.mark.asyncio
async def test_physical_printer_ownership_enforced(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    other = User(
        email="other@example.com", username="other", password_hash="$2b$12$test", active=True
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    catalog = await _catalog_printer(db_session)
    profile = await _profile(db_session, auth_user, catalog.id)
    foreign_device = await _device(db_session, other, name="Not yours")

    resp = await auth_client.get(
        URL,
        params={"printer_profile_id": profile.id, "physical_printer_id": foreign_device.id},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_foreign_profile_hidden(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    other = User(
        email="other2@example.com", username="other2", password_hash="$2b$12$test", active=True
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    catalog = await _catalog_printer(db_session)
    foreign_profile = await _profile(db_session, other, catalog.id)

    resp = await auth_client.get(URL, params={"printer_profile_id": foreign_profile.id})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_ownerless_official_config_not_selectable(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    # Shared/official configurations (owner_user_id IS NULL) are not selectable
    # here: recommendations run against the user's own configurations only.
    catalog = await _catalog_printer(db_session)
    official = PrinterProfile(
        owner_user_id=None,
        printer_id=catalog.id,
        name="Official Voron",
        slug="official-voron",
        is_official=True,
        active=True,
    )
    db_session.add(official)
    await db_session.commit()
    await db_session.refresh(official)

    resp = await auth_client.get(URL, params={"printer_profile_id": official.id})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_config_without_catalog_model(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    profile = await _profile(db_session, auth_user, None)  # no catalog link

    resp = await auth_client.get(URL, params={"printer_profile_id": profile.id})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_PRINTER_NOT_FOUND"
