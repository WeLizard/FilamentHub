"""Slices reported by the plugin, and the printer each belongs to."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.print_profile import PrintProfile
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.printer_connection_observation import PrinterConnectionObservationIn
from app.services.physical_printer_discovery_service import normalize_endpoint
from app.services.printer_connection_observation_service import record_observations


def _slice(**overrides) -> dict:
    payload = {
        "file_name": "Orca Head_PETG.gcode",
        "printer_settings_id": "Voron 2.4 350 0.4 nozzle",
        "print_settings_id": "0.20mm Standard @Voron",
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
    """A configuration does not identify hardware, even with only one linked printer."""
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
    assert reported["physical_printer_id"] is None
    assert reported["physical_printer_name"] is None
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
async def test_native_orca_child_name_resolves_through_same_plugin_observation(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Workshop P2S",
        device_fingerprint=None,
        supports_hh=False,
    )
    profile = PrinterProfile(
        owner_user_id=None,
        is_official=True,
        name="Bambu Lab P2S 0.4 nozzle",
        slug="bambu-lab-p2s-04-observed-slice",
        source="system",
        vendor="BambuLab",
        active=True,
        extra_metadata={"orca_vendor_id": "BBL"},
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

    source_instance_id = "fixture-plugin-instance-0002"
    db_session.add(PrinterConnectionBinding(
        user_id=auth_user.id, physical_printer_id=printer.id,
        source_instance_id=source_instance_id, connection_ref="p2s-connection",
        normalized_endpoint="fixture-p2s-connection", status="bound",
    ))
    await db_session.commit()
    await record_observations(
        db_session,
        auth_user.id,
        source_instance_id,
        [
            PrinterConnectionObservationIn(
                preset_name="Workshop P2S",
                connection_ref="p2s-connection",
                printer_settings_id="Workshop P2S",
                inherits=profile.name,
                vendor_id="BBL",
                has_technical_changes=False,
                print_host="192.168.1.31",
            )
        ],
    )

    response = await auth_client.post(
        "/api/v1/orcaslicer/slices",
        json={
            "slices": [
                _slice(
                    printer_settings_id="Workshop P2S",
                    source_instance_id=source_instance_id,
                )
            ]
        },
    )

    assert response.status_code == 200
    reported = (await auth_client.get("/api/v1/orcaslicer/slices")).json()[0]
    assert reported["printer_profile_id"] == profile.id
    assert reported["physical_printer_id"] == printer.id


@pytest.mark.asyncio
async def test_observed_endpoint_selects_one_of_two_printers_using_the_same_profile(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    home = UserPrinterDevice(
        user_id=auth_user.id,
        name="Home Voron",
        device_fingerprint=None,
        supports_hh=False,
    )
    workshop = UserPrinterDevice(
        user_id=auth_user.id,
        name="Workshop Voron",
        device_fingerprint=None,
        supports_hh=False,
    )
    profile = PrinterProfile(
        owner_user_id=None,
        is_official=True,
        name="Voron shared profile",
        slug="voron-shared-observed-endpoint",
        source="system",
        vendor="Voron",
        active=True,
        extra_metadata={"orca_vendor_id": "Voron"},
    )
    db_session.add_all([home, workshop, profile])
    await db_session.flush()
    db_session.add_all(
        [
            UserPrinterProfileLink(
                user_id=auth_user.id,
                physical_printer_id=printer.id,
                printer_profile_id=profile.id,
            )
            for printer in (home, workshop)
        ]
    )
    endpoint = normalize_endpoint("192.168.1.31:7125", "moonraker")
    source_instance_id = "fixture-plugin-instance-endpoint"
    db_session.add(
        PrinterConnectionBinding(
            user_id=auth_user.id,
            physical_printer_id=workshop.id,
            source_instance_id=source_instance_id,
            connection_ref="workshop-connection",
            normalized_endpoint=endpoint["normalized"],
            provider=endpoint["provider"],
            scheme=endpoint["scheme"],
            host=endpoint["host"],
            port=endpoint["port"],
            path=endpoint["path"],
            print_host="192.168.1.31:7125",
        )
    )
    await db_session.commit()

    await record_observations(
        db_session,
        auth_user.id,
        source_instance_id,
        [
            PrinterConnectionObservationIn(
                preset_name="Workshop connection",
                connection_ref="workshop-connection",
                printer_settings_id="Workshop connection",
                inherits=profile.name,
                vendor_id="Voron",
                has_technical_changes=False,
                print_host="192.168.1.31:7125",
                host_type="moonraker",
            )
        ],
    )

    response = await auth_client.post(
        "/api/v1/orcaslicer/slices",
        json={
            "slices": [
                _slice(
                    printer_settings_id="Workshop connection",
                    source_instance_id=source_instance_id,
                )
            ]
        },
    )

    assert response.status_code == 200
    reported = (await auth_client.get("/api/v1/orcaslicer/slices")).json()[0]
    assert reported["printer_profile_id"] == profile.id
    assert reported["physical_printer_id"] == workshop.id


@pytest.mark.asyncio
async def test_managed_machine_and_process_ids_win_over_mutable_orca_names(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Managed Voron",
        device_fingerprint=None,
        supports_hh=False,
    )
    machine = PrinterProfile(
        owner_user_id=auth_user.id,
        is_official=False,
        name="Managed machine",
        slug="managed-machine-slice-identity",
        setting_id="original-machine-name",
        active=True,
        source="user",
    )
    process = PrintProfile(
        owner_user_id=auth_user.id,
        is_official=False,
        name="Managed process",
        slug="managed-process-slice-identity",
        setting_id="original-process-name",
        active=True,
        source="user",
    )
    db_session.add_all([printer, machine, process])
    await db_session.flush()
    db_session.add(
        UserPrinterProfileLink(
            user_id=auth_user.id,
            physical_printer_id=printer.id,
            printer_profile_id=machine.id,
        )
    )
    await db_session.commit()

    response = await auth_client.post(
        "/api/v1/orcaslicer/slices",
        json={
            "slices": [
                _slice(
                    printer_settings_id="renamed-machine",
                    print_settings_id="renamed-process",
                    fhub_printer_profile_id=machine.id,
                    fhub_print_profile_id=process.id,
                )
            ]
        },
    )

    assert response.status_code == 200
    reported = (await auth_client.get("/api/v1/orcaslicer/slices")).json()[0]
    assert reported["printer_profile_id"] == machine.id
    assert reported["physical_printer_id"] is None
    assert reported["print_profile_id"] == process.id
    assert reported["print_settings_id"] == "renamed-process"


@pytest.mark.asyncio
async def test_private_foreign_profile_ids_are_not_trusted(
    auth_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    machine = PrinterProfile(
        owner_user_id=admin_user.id,
        is_official=False,
        name="Someone else's machine",
        slug="foreign-private-machine-slice-identity",
        setting_id="foreign-machine",
        active=False,
        source="user",
    )
    process = PrintProfile(
        owner_user_id=admin_user.id,
        is_official=False,
        name="Someone else's process",
        slug="foreign-private-process-slice-identity",
        setting_id="foreign-process",
        active=False,
        source="user",
    )
    db_session.add_all([machine, process])
    await db_session.commit()

    response = await auth_client.post(
        "/api/v1/orcaslicer/slices",
        json={
            "slices": [
                _slice(
                    printer_settings_id="foreign-machine",
                    print_settings_id="foreign-process",
                    fhub_printer_profile_id=machine.id,
                    fhub_print_profile_id=process.id,
                )
            ]
        },
    )

    assert response.status_code == 200
    reported = (await auth_client.get("/api/v1/orcaslicer/slices")).json()[0]
    assert reported["printer_profile_id"] is None
    assert reported["physical_printer_id"] is None
    assert reported["print_profile_id"] is None


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
