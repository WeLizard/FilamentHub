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
