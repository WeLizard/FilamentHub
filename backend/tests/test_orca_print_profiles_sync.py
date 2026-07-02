"""Regression tests for Orca print profile import links."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.print_profile import PrintProfile
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User


async def _register_and_login(
    client: AsyncClient,
    suffix: str,
) -> tuple[dict[str, str], str]:
    """Register a user and return auth headers + email."""
    email = f"{suffix}@example.com"
    password = "testpassword123"

    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": f"user_{suffix}",
            "password": password,
            "role": "user",
        },
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
async def test_import_print_profile_creates_printer_and_filament_links(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Import from Orca should materialize compatibility links, not only raw JSON arrays."""
    headers, email = await _register_and_login(client, "orca-print-links")

    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()

    printer = Printer(
        name="Voron 2.4 350",
        manufacturer="Voron",
        model="2.4 350",
        slug="voron-2-4-350",
        source="user",
        active=True,
    )
    db_session.add(printer)
    await db_session.flush()

    printer_profile = PrinterProfile(
        printer_id=printer.id,
        owner_user_id=user.id,
        name="Voron 2.4 350 0.4 nozzle",
        slug="voron-2-4-350-0-4-nozzle",
        active=True,
        source="user",
    )
    db_session.add(printer_profile)

    brand = Brand(name="Proto Brand", slug="proto-brand", active=True)
    db_session.add(brand)
    await db_session.flush()

    filament = Filament(
        brand_id=brand.id,
        name="Proto PLA",
        slug="proto-pla",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()

    response = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={
            "profiles": [
                {
                    "external_id": "orca-process-1",
                    "name": "0.20mm Standard @FilamentHub",
                    "slug": "0-20mm-standard-filamenthub",
                    "category": "quality",
                    "quality_tier": "standard",
                    "default_nozzle": "0.4",
                    "layer_height_mm": 0.2,
                    "compatible_printers": ["Voron 2.4 350 0.4 nozzle"],
                    "compatible_filaments": ["Proto PLA"],
                    "orcaslicer_settings": {
                        "compatible_printers": ["Voron 2.4 350 0.4 nozzle"],
                        "compatible_filaments": ["Proto PLA"],
                    },
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "created"

    profile = (
        await db_session.execute(
            select(PrintProfile)
            .options(
                selectinload(PrintProfile.printer_links),
                selectinload(PrintProfile.filament_links),
            )
            .where(PrintProfile.external_id == "orca-process-1")
        )
    ).scalar_one()

    assert profile.compatible_printers == ["Voron 2.4 350 0.4 nozzle"]
    assert len(profile.printer_links) == 1
    assert profile.printer_links[0].printer_id == printer.id
    assert profile.printer_links[0].printer_slug == printer.slug

    assert profile.compatible_filaments == ["Proto PLA"]
    assert len(profile.filament_links) == 1
    assert profile.filament_links[0].filament_id == filament.id
    assert profile.filament_links[0].filament_slug == filament.slug


async def _create_official_print_profile(db_session: AsyncSession) -> PrintProfile:
    profile = PrintProfile(
        name="Official 0.20mm Standard",
        slug="official-0-20mm-standard",
        owner_user_id=None,
        is_official=True,
        active=True,
        source="official",
        layer_height_mm=0.2,
    )
    db_session.add(profile)
    await db_session.flush()
    profile.orcaslicer_settings = {
        "fhub_id": profile.id,
        "fhub_source": "filamenthub",
        "layer_height": "0.2",
    }
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


@pytest.mark.asyncio
async def test_import_official_print_profile_forks_personal_copy(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Editing an official profile must fork a personal copy, never touch the original."""
    headers, email = await _register_and_login(client, "orca-fork-official")
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()

    official = await _create_official_print_profile(db_session)

    response = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={
            "profiles": [
                {
                    "external_id": "orca-fork-official-1",
                    "fhub_id": official.id,
                    "name": "Official 0.20mm Standard - tuned",
                    "slug": official.slug,
                    "layer_height_mm": 0.24,
                    "orcaslicer_settings": {
                        "fhub_id": official.id,
                        "fhub_source": "filamenthub",
                        "layer_height": "0.24",
                    },
                }
            ]
        },
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "created"
    assert result["fhub_id"] != official.id

    copy = await db_session.get(PrintProfile, result["fhub_id"])
    assert copy is not None
    assert copy.owner_user_id == user.id
    assert copy.is_official is False
    assert copy.slug != official.slug
    assert copy.name == "Official 0.20mm Standard - tuned"
    assert copy.orcaslicer_settings["fhub_id"] == copy.id
    assert copy.orcaslicer_settings["bundle_id"] == f"filamenthub:{copy.id}"

    await db_session.refresh(official)
    assert official.name == "Official 0.20mm Standard"
    assert official.owner_user_id is None
    assert official.is_official is True
    assert official.layer_height_mm == 0.2


@pytest.mark.asyncio
async def test_import_foreign_print_profile_forks_personal_copy(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Editing another user's profile must fork a copy instead of skipping the changes."""
    owner_headers, owner_email = await _register_and_login(client, "orca-fork-owner")
    del owner_headers
    owner = (
        await db_session.execute(select(User).where(User.email == owner_email))
    ).scalar_one()

    foreign = PrintProfile(
        name="Owner Draft Profile",
        slug="owner-draft-profile",
        owner_user_id=owner.id,
        is_official=False,
        active=True,
        source="user",
    )
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    editor_headers, editor_email = await _register_and_login(client, "orca-fork-editor")
    editor = (
        await db_session.execute(select(User).where(User.email == editor_email))
    ).scalar_one()

    response = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=editor_headers,
        json={
            "profiles": [
                {
                    "external_id": "orca-fork-foreign-1",
                    "fhub_id": foreign.id,
                    "name": "Owner Draft Profile - my edits",
                    "slug": foreign.slug,
                }
            ]
        },
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "created"
    assert result["fhub_id"] != foreign.id

    copy = await db_session.get(PrintProfile, result["fhub_id"])
    assert copy.owner_user_id == editor.id
    assert copy.is_official is False

    await db_session.refresh(foreign)
    assert foreign.name == "Owner Draft Profile"
    assert foreign.owner_user_id == owner.id


@pytest.mark.asyncio
async def test_resync_after_fork_updates_the_copy(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """After a fork the client remaps fhub_id; the next sync must update the copy in place."""
    headers, _email = await _register_and_login(client, "orca-fork-resync")
    official = await _create_official_print_profile(db_session)

    first = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={
            "profiles": [
                {
                    "external_id": "orca-fork-resync-1",
                    "fhub_id": official.id,
                    "name": "Official 0.20mm Standard - tuned",
                    "slug": official.slug,
                }
            ]
        },
    )
    copy_id = first.json()["results"][0]["fhub_id"]

    second = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={
            "profiles": [
                {
                    "external_id": "orca-fork-resync-1",
                    "fhub_id": copy_id,
                    "name": "Official 0.20mm Standard - tuned v2",
                    "slug": official.slug,
                }
            ]
        },
    )

    result = second.json()["results"][0]
    assert result["status"] == "updated"
    assert result["fhub_id"] == copy_id

    total = len(
        (await db_session.execute(select(PrintProfile))).scalars().all()
    )
    assert total == 2

    copy = await db_session.get(PrintProfile, copy_id)
    assert copy.name == "Official 0.20mm Standard - tuned v2"


@pytest.mark.asyncio
async def test_fork_dedup_when_client_resends_original_fhub_id(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """If fhub_id writeback failed client-side, external_id must resolve the existing fork."""
    headers, _email = await _register_and_login(client, "orca-fork-dedup")
    official = await _create_official_print_profile(db_session)

    payload = {
        "external_id": "orca-fork-dedup-1",
        "fhub_id": official.id,
        "name": "Official 0.20mm Standard - tuned",
        "slug": official.slug,
    }

    first = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={"profiles": [payload]},
    )
    copy_id = first.json()["results"][0]["fhub_id"]

    second = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={"profiles": [payload]},
    )

    result = second.json()["results"][0]
    assert result["status"] == "updated"
    assert result["fhub_id"] == copy_id

    total = len(
        (await db_session.execute(select(PrintProfile))).scalars().all()
    )
    assert total == 2


@pytest.mark.asyncio
async def test_import_official_printer_profile_forks_personal_copy(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Fork-on-edit applies to printer profiles the same way as to print profiles."""
    headers, email = await _register_and_login(client, "orca-fork-printer")
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()

    printer = Printer(
        name="Voron 2.4 300",
        manufacturer="Voron",
        model="2.4 300",
        slug="voron-2-4-300",
        source="official",
        active=True,
    )
    db_session.add(printer)
    await db_session.flush()

    official = PrinterProfile(
        printer_id=printer.id,
        owner_user_id=None,
        is_official=True,
        name="Voron 2.4 300 0.4 nozzle",
        slug="voron-2-4-300-0-4-nozzle",
        active=True,
        source="official",
    )
    db_session.add(official)
    await db_session.commit()
    await db_session.refresh(official)

    response = await client.post(
        "/api/v1/orcaslicer/printer-profiles/import",
        headers=headers,
        json={
            "profiles": [
                {
                    "external_id": "orca-fork-printer-1",
                    "fhub_id": official.id,
                    "printer_id": printer.id,
                    "name": "Voron 2.4 300 0.4 nozzle - custom",
                    "slug": official.slug,
                }
            ]
        },
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "created"
    assert result["fhub_id"] != official.id

    copy = await db_session.get(PrinterProfile, result["fhub_id"])
    assert copy.owner_user_id == user.id
    assert copy.is_official is False
    assert copy.slug != official.slug
    assert copy.printer_id == printer.id

    await db_session.refresh(official)
    assert official.name == "Voron 2.4 300 0.4 nozzle"
    assert official.owner_user_id is None
    assert official.is_official is True


@pytest.mark.asyncio
async def test_admin_updates_official_print_profile_in_place(
    admin_client: AsyncClient,
    db_session: AsyncSession,
):
    """Admins keep editing official profiles in place and must not claim ownership."""
    official = await _create_official_print_profile(db_session)

    response = await admin_client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        json={
            "profiles": [
                {
                    "external_id": "orca-admin-official-1",
                    "fhub_id": official.id,
                    "name": "Official 0.20mm Standard - admin fix",
                    "slug": official.slug,
                }
            ]
        },
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "updated"
    assert result["fhub_id"] == official.id

    await db_session.refresh(official)
    assert official.name == "Official 0.20mm Standard - admin fix"
    assert official.owner_user_id is None
    assert official.is_official is True


@pytest.mark.asyncio
async def test_import_print_profile_rebuilds_links_on_update(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Repeated import should replace stale compatibility links instead of accumulating them."""
    headers, email = await _register_and_login(client, "orca-print-update")

    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()

    printer_a = Printer(
        name="Voron Trident",
        manufacturer="Voron",
        model="Trident",
        slug="voron-trident",
        source="user",
        active=True,
    )
    printer_b = Printer(
        name="RatRig V-Core 3",
        manufacturer="RatRig",
        model="V-Core 3",
        slug="ratrig-v-core-3",
        source="user",
        active=True,
    )
    db_session.add_all([printer_a, printer_b])
    await db_session.flush()

    profile_a = PrinterProfile(
        printer_id=printer_a.id,
        owner_user_id=user.id,
        name="Voron Trident 0.4 nozzle",
        slug="voron-trident-0-4-nozzle",
        active=True,
        source="user",
    )
    profile_b = PrinterProfile(
        printer_id=printer_b.id,
        owner_user_id=user.id,
        name="RatRig V-Core 3 0.4 nozzle",
        slug="ratrig-v-core-3-0-4-nozzle",
        active=True,
        source="user",
    )
    db_session.add_all([profile_a, profile_b])
    await db_session.commit()

    initial_import = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={
            "profiles": [
                {
                    "external_id": "orca-process-update",
                    "name": "0.16mm Balanced @FilamentHub",
                    "slug": "0-16mm-balanced-filamenthub",
                    "compatible_printers": ["Voron Trident 0.4 nozzle"],
                    "orcaslicer_settings": {
                        "compatible_printers": ["Voron Trident 0.4 nozzle"],
                    },
                }
            ]
        },
    )
    assert initial_import.status_code == 200

    update_import = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={
            "profiles": [
                {
                    "external_id": "orca-process-update",
                    "name": "0.16mm Balanced @FilamentHub",
                    "slug": "0-16mm-balanced-filamenthub",
                    "compatible_printers": ["RatRig V-Core 3 0.4 nozzle"],
                    "orcaslicer_settings": {
                        "compatible_printers": ["RatRig V-Core 3 0.4 nozzle"],
                    },
                }
            ]
        },
    )
    assert update_import.status_code == 200
    assert update_import.json()["results"][0]["status"] == "updated"

    profile = (
        await db_session.execute(
            select(PrintProfile)
            .options(selectinload(PrintProfile.printer_links))
            .where(PrintProfile.external_id == "orca-process-update")
        )
    ).scalar_one()

    assert profile.compatible_printers == ["RatRig V-Core 3 0.4 nozzle"]
    assert len(profile.printer_links) == 1
    assert profile.printer_links[0].printer_id == printer_b.id
    assert profile.printer_links[0].printer_slug == printer_b.slug
