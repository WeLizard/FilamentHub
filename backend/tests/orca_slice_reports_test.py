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
        "total_weight_g": 168.56,
        "filament_weights_g": [98.4, 52.82, 1.45, 15.89],
        "estimated_seconds": 23050,
        "filament_changes": 299,
        "layer_count": 384,
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

    # A different slice of the same model is not a duplicate.
    changed = await auth_client.post(
        "/api/v1/orcaslicer/slices", json={"slices": [_slice(total_weight_g=170.0)]}
    )
    assert changed.json() == {"accepted": 1, "duplicates": 0}


@pytest.mark.asyncio
async def test_a_slice_finds_the_printer_through_its_configuration(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    """The preset named in the G-code is what ties a slice to a real machine."""
    printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Voron at home",
        device_fingerprint=None,
        supports_hh=False,
    )
    profile = PrinterProfile(
        owner_user_id=auth_user.id,
        is_official=False,
        name="Voron 2.4 350 0.4 nozzle",
        slug="voron-2-4-350-0-4-slice-test",
        setting_id="Voron 2.4 350 0.4 nozzle",
        active=True,
        source="orcaslicer",
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
    assert reported["total_weight_g"] == 168.56


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
