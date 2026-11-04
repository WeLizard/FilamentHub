"""Regression coverage for printer profile updates and response serialization."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User


@pytest.mark.asyncio
@pytest.mark.parametrize("binding", ["unchanged", "replaced", "removed"])
async def test_patch_bound_profile_returns_committed_catalog_fields(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
    binding: str,
) -> None:
    original = Printer(
        name="Original machine",
        manufacturer="Original vendor",
        model="Original",
        slug="original-machine",
        source="system",
    )
    replacement = Printer(
        name="Replacement machine",
        manufacturer="Replacement vendor",
        model="Replacement",
        slug="replacement-machine",
        source="system",
    )
    db_session.add_all([original, replacement])
    await db_session.flush()
    profile = PrinterProfile(
        name="Bound profile",
        slug="bound-profile",
        printer_id=original.id,
        owner_user_id=auth_user.id,
    )
    db_session.add(profile)
    await db_session.commit()
    profile_id = profile.id
    expected_printer = replacement if binding == "replaced" else original
    expected = {
        "printer_id": expected_printer.id,
        "printer_slug": expected_printer.slug,
        "printer_name": expected_printer.name,
        "printer_manufacturer": expected_printer.manufacturer,
        "printer_model": expected_printer.model,
        "orca_printer_model": expected_printer.name,
    }
    if binding == "removed":
        expected = dict.fromkeys(expected)
    payload = {"notes": "Saved profile change"}
    if binding != "unchanged":
        payload["printer_id"] = expected["printer_id"]

    # The production request has no catalog Printer cached by fixture setup.
    db_session.expunge_all()
    response = await auth_client.patch(
        f"/api/v1/printer-profiles/{profile_id}",
        json=payload,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["notes"] == payload["notes"]
    assert result["updated_at"] is not None
    assert {key: result[key] for key in expected} == expected
    db_session.expunge_all()
    stored = await db_session.get(PrinterProfile, profile_id)
    assert stored.notes == payload["notes"]
    assert stored.printer_id == expected["printer_id"]


@pytest.mark.asyncio
async def test_patch_other_owners_profile_does_not_commit_changes(
    auth_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    profile = PrinterProfile(
        name="Other profile",
        slug="other-profile",
        owner_user_id=admin_user.id,
        notes="Owner notes",
    )
    db_session.add(profile)
    await db_session.commit()
    profile_id = profile.id
    db_session.expunge_all()

    response = await auth_client.patch(
        f"/api/v1/printer-profiles/{profile_id}",
        json={"notes": "Unauthorized edit"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_NO_PERMISSION"
    notes = await db_session.scalar(
        select(PrinterProfile.notes).where(PrinterProfile.id == profile_id)
    )
    assert notes == "Owner notes"
