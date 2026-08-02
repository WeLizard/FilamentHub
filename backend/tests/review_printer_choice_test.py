"""A review can name the machine it is about, so the answers can be counted.

The printer was free text: the same machine arrived as "Voron 2.4", "voron 2.4"
and "Ворон 2.4", and the question the field exists for — how does this material
behave on the printer I own — could never be answered from it.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_review import FilamentReview
from app.models.printer import Printer
from app.models.user import User
from tests.conftest import registration_payload


async def _material(db: AsyncSession) -> Filament:
    brand = Brand(name="Printer Choice Brand", slug="printer-choice-brand", active=True)
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Choice PLA",
        slug="choice-pla",
        material_type="PLA",
        active=True,
    )
    db.add(filament)
    await db.commit()
    return filament


async def _machine(db: AsyncSession) -> Printer:
    printer = Printer(
        name="Voron 2.4 350",
        manufacturer="Voron",
        model="2.4 350",
        slug="voron-2-4-350-review",
        source="system",
        active=True,
    )
    db.add(printer)
    await db.commit()
    return printer


async def _signed_in(client: AsyncClient, db: AsyncSession, suffix: str) -> dict:
    email = f"{suffix}@example.com"
    password = "testpassword123"
    registered = await client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            email=email, username=f"user_{suffix}", password=password
        ),
    )
    assert registered.status_code == 201

    person = await db.scalar(select(User).where(User.email == email))
    person.email_verified = True
    await db.commit()

    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


@pytest.mark.asyncio
async def test_a_chosen_machine_names_itself(client: AsyncClient, db_session: AsyncSession):
    """Picking from the catalogue fixes the spelling, whatever was typed."""
    headers = await _signed_in(client, db_session, "review-printer-pick")
    filament = await _material(db_session)
    printer = await _machine(db_session)

    created = await client.post(
        "/api/v1/filament-reviews/",
        headers=headers,
        json={
            "filament_id": filament.id,
            "success": True,
            "rating": 5,
            "printer_id": printer.id,
            "printer_model": "воРОн 2.4 как-то так",
        },
    )

    assert created.status_code == 201
    assert created.json()["printer_id"] == printer.id
    assert created.json()["printer_model"] == "Voron 2.4 350"


@pytest.mark.asyncio
async def test_a_self_build_may_still_be_typed(client: AsyncClient, db_session: AsyncSession):
    """No catalogue lists a machine somebody welded together."""
    headers = await _signed_in(client, db_session, "review-printer-typed")
    filament = await _material(db_session)

    created = await client.post(
        "/api/v1/filament-reviews/",
        headers=headers,
        json={
            "filament_id": filament.id,
            "success": True,
            "rating": 4,
            "printer_model": "Самосбор на линейных рельсах",
        },
    )

    assert created.status_code == 201
    assert created.json()["printer_id"] is None
    assert created.json()["printer_model"] == "Самосбор на линейных рельсах"


@pytest.mark.asyncio
async def test_a_machine_that_does_not_exist_is_refused(
    client: AsyncClient, db_session: AsyncSession
):
    headers = await _signed_in(client, db_session, "review-printer-missing")
    filament = await _material(db_session)

    refused = await client.post(
        "/api/v1/filament-reviews/",
        headers=headers,
        json={
            "filament_id": filament.id,
            "success": True,
            "rating": 4,
            "printer_id": 999999,
        },
    )

    assert refused.status_code == 404
    assert refused.json()["detail"]["code"] == "ERR_PRINTER_NOT_FOUND"
    assert await db_session.scalar(select(FilamentReview)) is None


@pytest.mark.asyncio
async def test_changing_the_machine_updates_the_name_with_it(
    client: AsyncClient, db_session: AsyncSession
):
    """The two fields must not be able to fall out of step."""
    headers = await _signed_in(client, db_session, "review-printer-edit")
    filament = await _material(db_session)
    printer = await _machine(db_session)

    created = await client.post(
        "/api/v1/filament-reviews/",
        headers=headers,
        json={
            "filament_id": filament.id,
            "success": True,
            "rating": 4,
            "printer_model": "что-то своё",
        },
    )
    review_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/filament-reviews/{review_id}",
        headers=headers,
        json={"printer_id": printer.id},
    )

    assert updated.status_code == 200
    assert updated.json()["printer_id"] == printer.id
    assert updated.json()["printer_model"] == "Voron 2.4 350"
