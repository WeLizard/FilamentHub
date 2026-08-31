"""Tests for the OrcaSlicer printer-connection observation staging (stage A)."""

import hashlib
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orca_printer_connection_observation import OrcaPrinterConnectionObservation
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.printer_connection_observation import PrinterConnectionObservationIn
from app.services.printer_connection_observation_service import (
    _sanitize_host,
    observed_endpoint,
    record_observations,
)


async def _make_profile(db: AsyncSession, user: User, suffix: str, setting_id: str | None) -> PrinterProfile:
    profile = PrinterProfile(
        owner_user_id=user.id,
        name=f"Voron {suffix}",
        slug=f"voron-{suffix}",
        setting_id=setting_id,
        active=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


def _obs(**kw) -> PrinterConnectionObservationIn:
    return PrinterConnectionObservationIn(**kw)


async def _count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count(OrcaPrinterConnectionObservation.id)))).scalar_one()


@pytest.mark.asyncio
async def test_unmatched_observation_is_accepted_and_stored(db_session: AsyncSession, auth_user: User):
    accepted, matched, unmatched = await record_observations(
        db_session, auth_user.id, "inst-1",
        [_obs(printer_settings_id="Voron 0.4", preset_name="My Voron",
              print_host="http://192.168.1.21:7125", host_type="moonraker")],
    )
    assert (accepted, matched, unmatched) == (1, 0, 1)
    row = (await db_session.execute(select(OrcaPrinterConnectionObservation))).scalar_one()
    assert row.matched_printer_profile_id is None
    assert row.print_host is None
    assert row.endpoint_ciphertext and row.endpoint_ciphertext.startswith("fh1:")
    assert observed_endpoint(row) == "http://192.168.1.21:7125"
    assert row.first_seen_at is not None


@pytest.mark.asyncio
async def test_matched_by_exact_settings_id(db_session: AsyncSession, auth_user: User):
    profile = await _make_profile(db_session, auth_user, "a", "Voron 0.4")
    _, matched, _ = await record_observations(
        db_session, auth_user.id, "inst-1",
        [_obs(printer_settings_id="Voron 0.4", preset_name="Voron a",
              print_host="192.168.1.21", host_type="moonraker")],
    )
    assert matched == 1
    row = (await db_session.execute(select(OrcaPrinterConnectionObservation))).scalar_one()
    assert row.matched_printer_profile_id == profile.id


@pytest.mark.asyncio
async def test_same_settings_id_uses_the_named_user_profile(
    db_session: AsyncSession, auth_user: User
):
    workshop = await _make_profile(db_session, auth_user, "workshop", "shared-id")
    await _make_profile(db_session, auth_user, "home", "shared-id")

    _, matched, unmatched = await record_observations(
        db_session,
        auth_user.id,
        "inst-1",
        [_obs(printer_settings_id="shared-id", preset_name="Voron workshop")],
    )

    assert (matched, unmatched) == (1, 0)
    row = (await db_session.execute(select(OrcaPrinterConnectionObservation))).scalar_one()
    assert row.matched_printer_profile_id == workshop.id


@pytest.mark.asyncio
async def test_shared_setting_id_does_not_match_a_differently_named_user_profile(
    db_session: AsyncSession, auth_user: User
):
    existing = await _make_profile(db_session, auth_user, "workshop", "shared-id")

    accepted, matched, unmatched = await record_observations(
        db_session,
        auth_user.id,
        "inst-1",
        [_obs(printer_settings_id="shared-id", preset_name="Office A1 mini")],
    )

    assert (accepted, matched, unmatched) == (1, 0, 1)
    row = (await db_session.execute(select(OrcaPrinterConnectionObservation))).scalar_one()
    assert row.matched_printer_profile_id is None
    assert row.matched_printer_profile_id != existing.id


@pytest.mark.asyncio
async def test_stock_observation_matches_global_official_profile(
    db_session: AsyncSession, auth_user: User
):
    profile = PrinterProfile(
        owner_user_id=None,
        name="Bambu Lab P2S 0.4 nozzle",
        slug="bambu-lab-p2s-04-nozzle",
        setting_id="BBL-P2S-0.4",
        source="system",
        is_official=True,
        active=True,
        extra_metadata={"printer_model": "Bambu Lab P2S"},
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    _, matched, unmatched = await record_observations(
        db_session,
        auth_user.id,
        "inst-1",
        [
            _obs(
                printer_settings_id="BBL-P2S-0.4",
                preset_name="Bambu Lab P2S 0.4 nozzle",
                printer_model="Bambu Lab P2S",
                is_system=True,
                is_current=True,
            )
        ],
    )

    assert (matched, unmatched) == (1, 0)
    row = (await db_session.execute(select(OrcaPrinterConnectionObservation))).scalar_one()
    assert row.matched_printer_profile_id == profile.id


@pytest.mark.asyncio
async def test_connection_only_user_child_matches_its_official_parent(
    db_session: AsyncSession, auth_user: User
):
    parent = PrinterProfile(
        owner_user_id=None,
        name="Voron 2.4 350 0.4 nozzle",
        slug="voron-2-4-350-04-connection-parent",
        vendor="Voron",
        source="system",
        is_official=True,
        active=True,
        extra_metadata={"orca_vendor_id": "Voron"},
    )
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    _, matched, unmatched = await record_observations(
        db_session,
        auth_user.id,
        "inst-1",
        [
            _obs(
                preset_name="Workshop Voron",
                printer_settings_id="Workshop Voron",
                inherits=parent.name,
                vendor_id="Voron",
                print_host="192.168.1.21:7125",
                host_type="moonraker",
                is_system=False,
                has_technical_changes=False,
            )
        ],
    )

    assert (matched, unmatched) == (1, 0)
    row = (await db_session.execute(select(OrcaPrinterConnectionObservation))).scalar_one()
    assert row.matched_printer_profile_id == parent.id
    assert row.sanitized_payload["has_technical_changes"] is False


@pytest.mark.asyncio
async def test_ambiguous_owned_parents_do_not_fall_back_to_official(
    db_session: AsyncSession, auth_user: User
):
    parent_name = "Shared workshop machine"
    profiles = [
        PrinterProfile(
            owner_user_id=auth_user.id,
            name=parent_name,
            slug=f"shared-workshop-owned-{index}",
            active=True,
        )
        for index in range(2)
    ]
    profiles.append(
        PrinterProfile(
            owner_user_id=None,
            name=parent_name,
            slug="shared-workshop-official",
            source="system",
            is_official=True,
            active=True,
            extra_metadata={"orca_vendor_id": "VendorA"},
        )
    )
    db_session.add_all(profiles)
    await db_session.commit()

    _, matched, unmatched = await record_observations(
        db_session,
        auth_user.id,
        "inst-1",
        [
            _obs(
                preset_name="Connected child",
                inherits=parent_name,
                vendor_id="VendorA",
                has_technical_changes=False,
            )
        ],
    )

    assert (matched, unmatched) == (0, 1)


@pytest.mark.asyncio
async def test_connection_parent_never_crosses_vendor_boundary(
    db_session: AsyncSession, auth_user: User
):
    parent = PrinterProfile(
        owner_user_id=None,
        name="Shared machine name",
        slug="shared-machine-vendor-a",
        source="system",
        is_official=True,
        active=True,
        extra_metadata={"orca_vendor_id": "VendorA"},
    )
    db_session.add(parent)
    await db_session.commit()

    _, matched, unmatched = await record_observations(
        db_session,
        auth_user.id,
        "inst-1",
        [
            _obs(
                preset_name="Connected child",
                inherits=parent.name,
                vendor_id="VendorB",
                has_technical_changes=False,
            )
        ],
    )

    assert (matched, unmatched) == (0, 1)


@pytest.mark.asyncio
async def test_current_and_visible_profile_state_is_replaced_within_one_orca_installation(
    db_session: AsyncSession, auth_user: User
):
    await record_observations(
        db_session,
        auth_user.id,
        "inst-1",
        [
            _obs(
                preset_name="First",
                is_system=True,
                is_visible=True,
                is_current=True,
            )
        ],
    )
    await record_observations(
        db_session,
        auth_user.id,
        "inst-1",
        [
            _obs(
                preset_name="Second",
                is_system=True,
                is_visible=True,
                is_current=True,
            )
        ],
    )

    rows = list(
        (
            await db_session.execute(
                select(OrcaPrinterConnectionObservation).order_by(
                    OrcaPrinterConnectionObservation.id
                )
            )
        ).scalars()
    )
    assert [bool((row.sanitized_payload or {}).get("is_current")) for row in rows] == [
        False,
        True,
    ]
    assert [bool((row.sanitized_payload or {}).get("is_visible")) for row in rows] == [
        False,
        True,
    ]


@pytest.mark.asyncio
async def test_partial_recovery_preserves_current_and_only_refreshes_observed_binding(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
):
    source_instance_id = "partial-recovery-instance"
    observations = [
        {
            "connection_ref": "orca-local-v1:account:printer-a",
            "preset_name": "Printer A",
            "print_host": "192.168.1.21:7125",
            "host_type": "moonraker",
            "is_current": True,
            "is_visible": True,
        },
        {
            "connection_ref": "orca-local-v1:account:printer-b",
            "preset_name": "Printer B",
            "print_host": "192.168.1.22:7125",
            "host_type": "moonraker",
            "is_current": False,
        },
    ]
    first = await auth_client.post(
        "/api/v1/orcaslicer/printer-connections/observe",
        json={
            "source_instance_id": source_instance_id,
            "snapshot_complete": True,
            "observations": observations,
        },
    )
    assert first.status_code == 200

    stale_at = datetime(2026, 1, 1)
    bindings = list(
        (
            await db_session.execute(
                select(PrinterConnectionBinding).where(
                    PrinterConnectionBinding.source_instance_id == source_instance_id
                )
            )
        ).scalars()
    )
    assert len(bindings) == 2
    for binding in bindings:
        binding.last_seen_at = stale_at
    await db_session.commit()

    partial = await auth_client.post(
        "/api/v1/orcaslicer/printer-connections/observe",
        json={
            "source_instance_id": source_instance_id,
            "snapshot_complete": False,
            "observations": [{**observations[0], "is_current": False, "is_visible": False}],
        },
    )
    assert partial.status_code == 200

    refreshed_bindings = {
        binding.connection_ref: binding
        for binding in (
            await db_session.execute(
                select(PrinterConnectionBinding)
                .where(PrinterConnectionBinding.source_instance_id == source_instance_id)
                .execution_options(populate_existing=True)
            )
        ).scalars()
    }
    assert refreshed_bindings["orca-local-v1:account:printer-a"].last_seen_at > stale_at
    assert refreshed_bindings["orca-local-v1:account:printer-b"].last_seen_at == stale_at

    rows = list(
        (
            await db_session.execute(
                select(OrcaPrinterConnectionObservation)
                .where(
                    OrcaPrinterConnectionObservation.source_instance_id
                    == source_instance_id
                )
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )
    current = [row for row in rows if (row.sanitized_payload or {}).get("is_current")]
    assert [row.connection_ref for row in current] == [
        "orca-local-v1:account:printer-a"
    ]
    assert (current[0].sanitized_payload or {}).get("is_visible") is True


@pytest.mark.asyncio
async def test_name_is_not_used_for_matching(db_session: AsyncSession, auth_user: User):
    # A profile that shares only the display name, not the settings id, must not match.
    await _make_profile(db_session, auth_user, "a", setting_id=None)
    _, matched, unmatched = await record_observations(
        db_session, auth_user.id, "inst-1",
        [_obs(printer_settings_id="Voron 0.4", preset_name="Voron a", print_host="192.168.1.21")],
    )
    assert (matched, unmatched) == (0, 1)


@pytest.mark.asyncio
async def test_idempotent_upsert_same_fingerprint(db_session: AsyncSession, auth_user: User):
    args = {"printer_settings_id": "Voron 0.4", "print_host": "192.168.1.21", "host_type": "moonraker"}
    await record_observations(db_session, auth_user.id, "inst-1", [_obs(preset_name="First", **args)])
    await record_observations(db_session, auth_user.id, "inst-1", [_obs(preset_name="Renamed", **args)])
    assert await _count(db_session) == 1
    row = (await db_session.execute(select(OrcaPrinterConnectionObservation))).scalar_one()
    assert row.preset_name == "Renamed"  # display field refreshed on repeat


@pytest.mark.asyncio
async def test_endpoint_change_creates_a_separate_row(db_session: AsyncSession, auth_user: User):
    base = {"printer_settings_id": "Voron 0.4", "host_type": "moonraker"}
    await record_observations(db_session, auth_user.id, "inst-1", [_obs(print_host="192.168.1.21", **base)])
    await record_observations(db_session, auth_user.id, "inst-1", [_obs(print_host="192.168.1.99", **base)])
    assert await _count(db_session) == 2


@pytest.mark.asyncio
async def test_credentials_stripped_from_host():
    assert _sanitize_host("http://bblp:12345678@192.168.1.21:990/x") == "http://192.168.1.21:990/x"
    assert _sanitize_host("user:pass@192.168.1.21:7125") == "192.168.1.21:7125"
    assert _sanitize_host("http://192.168.1.21:7125") == "http://192.168.1.21:7125"
    assert _sanitize_host(None) is None


@pytest.mark.asyncio
async def test_stored_host_has_no_credentials(db_session: AsyncSession, auth_user: User):
    await record_observations(
        db_session, auth_user.id, "inst-1",
        [_obs(printer_settings_id="Voron 0.4", print_host="http://bblp:secret@192.168.1.21:990")],
    )
    row = (await db_session.execute(select(OrcaPrinterConnectionObservation))).scalar_one()
    assert "secret" not in (row.print_host or "")
    assert "secret" not in str(row.sanitized_payload)
    assert "192.168.1.21" not in (row.endpoint_ciphertext or "")
    assert row.endpoint_fingerprint != hashlib.sha256(
        b"moonraker|http://192.168.1.21:990"
    ).hexdigest()
    assert observed_endpoint(row) == "http://192.168.1.21:990"


@pytest.mark.asyncio
async def test_observation_endpoint_respects_disabled_printer_import(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
):
    auth_user.allow_printer_profiles_import = False
    await db_session.commit()

    response = await auth_client.post(
        "/api/v1/orcaslicer/printer-connections/observe",
        json={
            "source_instance_id": "disabled-import-instance",
            "observations": [
                {
                    "preset_name": "Bambu Lab P2S 0.4 nozzle",
                    "printer_model": "Bambu Lab P2S",
                    "is_system": True,
                    "is_current": True,
                }
            ],
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_IMPORT_PRINTER_DISABLED"
    assert await _count(db_session) == 0


@pytest.mark.asyncio
async def test_connection_binding_can_be_explicitly_assigned_to_owned_printer(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
):
    observed_printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Observed shell",
        supports_hh=False,
    )
    target_printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Workshop Voron",
        supports_hh=False,
    )
    db_session.add_all([observed_printer, target_printer])
    await db_session.flush()
    binding = PrinterConnectionBinding(
        user_id=auth_user.id,
        physical_printer_id=observed_printer.id,
        source_instance_id="inst-1",
        connection_ref="orca-local-v1:account:workshop",
        normalized_endpoint="ref:workshop",
        provider="moonraker",
    )
    db_session.add(binding)
    await db_session.commit()
    await record_observations(
        db_session,
        auth_user.id,
        "inst-1",
        [
            _obs(
                connection_ref=binding.connection_ref,
                preset_name="Workshop Voron 0.4",
                host_type="moonraker",
            )
        ],
    )

    listed = await auth_client.get("/api/v1/orcaslicer/printer-connections/bindings")
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": binding.id,
            "physical_printer_id": observed_printer.id,
            "physical_printer_name": "Observed shell",
            "connection_ref": binding.connection_ref,
            "preset_name": "Workshop Voron 0.4",
            "provider": "moonraker",
            "display_endpoint": None,
            "endpoint_shared": False,
            "status": "bound",
            "last_seen_at": listed.json()[0]["last_seen_at"],
        }
    ]

    assigned = await auth_client.patch(
        f"/api/v1/orcaslicer/printer-connections/bindings/{binding.id}",
        json={"physical_printer_id": target_printer.id},
    )
    assert assigned.status_code == 204
    await db_session.refresh(binding)
    assert binding.physical_printer_id == target_printer.id


@pytest.mark.asyncio
async def test_connection_binding_rejects_unknown_target_printer(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
):
    printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Observed shell",
        supports_hh=False,
    )
    db_session.add(printer)
    await db_session.flush()
    binding = PrinterConnectionBinding(
        user_id=auth_user.id,
        physical_printer_id=printer.id,
        normalized_endpoint="ref:unknown-target",
        provider="moonraker",
    )
    db_session.add(binding)
    await db_session.commit()

    response = await auth_client.patch(
        f"/api/v1/orcaslicer/printer-connections/bindings/{binding.id}",
        json={"physical_printer_id": 999999},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_DEVICE_NOT_FOUND"
