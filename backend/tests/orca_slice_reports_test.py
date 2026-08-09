"""Slices reported by the plugin, and the printer each belongs to."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice


def _slice(**overrides) -> dict:
    payload = {
        "file_name": "Orca Head_PETG.gcode",
        "printer_settings_id": "Voron 2.4 350 0.4 nozzle",
        "printer_model": "Voron 2.4 350",
        "target_host": "File",
        "slicer_version": "2.4.2",
        "source_key": "9f1c2ad4e7b30512",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_the_same_slice_arriving_twice_is_stored_once(
    auth_client: AsyncClient,
) -> None:
    """Exporting to a file and uploading to a printer both fire the plugin."""
    first = await auth_client.post("/api/v1/orcaslicer/slices", json={"slices": [_slice()]})
    assert first.status_code == 200
    assert first.json() == {"accepted": 1, "duplicates": 0}

    again = await auth_client.post(
        "/api/v1/orcaslicer/slices", json={"slices": [_slice(target_host="OctoPrint")]}
    )
    assert again.status_code == 200
    assert again.json() == {"accepted": 0, "duplicates": 1}

    listed = await auth_client.get("/api/v1/orcaslicer/slices")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Re-slicing the same model gives the plugin a new handle for a new file.
    changed = await auth_client.post(
        "/api/v1/orcaslicer/slices", json={"slices": [_slice(source_key="0b77e5c1aa249d38")]}
    )
    assert changed.json() == {"accepted": 1, "duplicates": 0}


@pytest.mark.asyncio
async def test_a_slice_only_selects_an_unambiguous_printer_configuration(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    """An official preset can identify one machine, but never guesses between two."""
    printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Voron at home",
        device_fingerprint=None,
        supports_hh=False,
    )
    profile = PrinterProfile(
        owner_user_id=None,
        is_official=True,
        name="Voron 2.4 350 0.4 nozzle",
        slug="voron-2-4-350-0-4-slice-test",
        setting_id="Voron 2.4 350 0.4 nozzle",
        active=True,
        source="catalog",
    )
    db_session.add_all([printer, profile])
    await db_session.flush()
    db_session.add(
        UserPrinterProfileLink(
            user_id=auth_user.id,
            physical_printer_id=printer.id,
            printer_profile_id=profile.id,
        )
    )
    await db_session.commit()

    await auth_client.post("/api/v1/orcaslicer/slices", json={"slices": [_slice()]})

    reported = (await auth_client.get("/api/v1/orcaslicer/slices")).json()[0]
    assert reported["physical_printer_id"] == printer.id
    assert reported["physical_printer_name"] == "Voron at home"
    assert reported["printer_profile_id"] == profile.id
    assert reported["source_key"] == "9f1c2ad4e7b30512"

    second_printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Voron at work",
        device_fingerprint=None,
        supports_hh=False,
    )
    db_session.add(second_printer)
    await db_session.flush()
    db_session.add(
        UserPrinterProfileLink(
            user_id=auth_user.id,
            physical_printer_id=second_printer.id,
            printer_profile_id=profile.id,
        )
    )
    await db_session.commit()

    await auth_client.post(
        "/api/v1/orcaslicer/slices",
        json={"slices": [_slice(source_key="second-printer-slice")]},
    )

    ambiguous = (await auth_client.get("/api/v1/orcaslicer/slices")).json()[0]
    assert ambiguous["physical_printer_id"] is None
    assert ambiguous["physical_printer_name"] is None
    assert ambiguous["printer_profile_id"] == profile.id


@pytest.mark.asyncio
async def test_a_slice_for_an_unknown_preset_is_still_kept(
    auth_client: AsyncClient,
) -> None:
    """A machine we know nothing about still produced a real slice."""
    await auth_client.post(
        "/api/v1/orcaslicer/slices",
        json={"slices": [_slice(printer_settings_id="Nothing We Know 0.4")]},
    )
    reported = (await auth_client.get("/api/v1/orcaslicer/slices")).json()[0]
    assert reported["physical_printer_id"] is None
    assert reported["printer_model"] == "Voron 2.4 350"


@pytest.mark.asyncio
async def test_a_slice_can_be_removed_from_the_list(auth_client: AsyncClient) -> None:
    """An old slice is clutter; a person decides when it goes."""
    await auth_client.post("/api/v1/orcaslicer/slices", json={"slices": [_slice()]})
    reported = (await auth_client.get("/api/v1/orcaslicer/slices")).json()[0]

    removed = await auth_client.delete(f"/api/v1/orcaslicer/slices/{reported['id']}")
    assert removed.status_code == 204
    assert (await auth_client.get("/api/v1/orcaslicer/slices")).json() == []

    again = await auth_client.delete(f"/api/v1/orcaslicer/slices/{reported['id']}")
    assert again.status_code == 404


@pytest.mark.asyncio
async def test_one_persons_slice_is_not_anothers_to_remove(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The list is per account, and so is dropping from it."""
    from app.core.security import create_access_token
    from app.services.legal_acceptance_service import (
        CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        CURRENT_TERMS_VERSION,
    )

    await auth_client.post("/api/v1/orcaslicer/slices", json={"slices": [_slice()]})
    reported = (await auth_client.get("/api/v1/orcaslicer/slices")).json()[0]

    stranger = User(
        email="stranger@example.com",
        username="stranger",
        password_hash="$2b$12$test",
        active=True,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db_session.add(stranger)
    await db_session.commit()

    owners_token = auth_client.headers["Authorization"]
    auth_client.headers["Authorization"] = (
        f"Bearer {create_access_token({'sub': stranger.email})}"
    )
    refused = await auth_client.delete(f"/api/v1/orcaslicer/slices/{reported['id']}")
    assert refused.status_code == 404

    auth_client.headers["Authorization"] = owners_token
    assert len((await auth_client.get("/api/v1/orcaslicer/slices")).json()) == 1
