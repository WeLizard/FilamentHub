"""Tests for the OrcaSlicer printer-connection observation staging (stage A)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orca_printer_connection_observation import OrcaPrinterConnectionObservation
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.schemas.printer_connection_observation import PrinterConnectionObservationIn
from app.services.printer_connection_observation_service import (
    _sanitize_host,
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
    assert row.print_host == "http://192.168.1.21:7125"
    assert row.first_seen_at is not None


@pytest.mark.asyncio
async def test_matched_by_exact_settings_id(db_session: AsyncSession, auth_user: User):
    profile = await _make_profile(db_session, auth_user, "a", "Voron 0.4")
    _, matched, _ = await record_observations(
        db_session, auth_user.id, "inst-1",
        [_obs(printer_settings_id="Voron 0.4", preset_name="My Voron",
              print_host="192.168.1.21", host_type="moonraker")],
    )
    assert matched == 1
    row = (await db_session.execute(select(OrcaPrinterConnectionObservation))).scalar_one()
    assert row.matched_printer_profile_id == profile.id


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
    assert row.print_host == "http://192.168.1.21:990"
