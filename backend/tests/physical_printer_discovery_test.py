"""Stage B tests: physical printers derived from connection observations."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.printer_connection_observation import PrinterConnectionObservationIn
from app.services.physical_printer_discovery_service import (
    normalize_endpoint,
    reconcile_user_printers,
)
from app.services.printer_connection_observation_service import record_observations


async def _make_profile(db: AsyncSession, user: User, suffix: str, setting_id: str) -> PrinterProfile:
    profile = PrinterProfile(
        owner_user_id=user.id, name=f"Voron {suffix}", slug=f"voron-{suffix}",
        setting_id=setting_id, active=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


def _obs(**kw) -> PrinterConnectionObservationIn:
    return PrinterConnectionObservationIn(**kw)


async def _observe(db: AsyncSession, user: User, observations: list[PrinterConnectionObservationIn]) -> None:
    await record_observations(db, user.id, "inst-1", observations)


async def _count(db: AsyncSession, model) -> int:
    return (await db.execute(select(func.count(model.id)))).scalar_one()


@pytest.mark.asyncio
async def test_new_endpoint_creates_physical_printer(db_session: AsyncSession, auth_user: User):
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="Voron 0.4", printer_model="Voron 2.4",
             print_host="192.168.1.21", host_type="moonraker"),
    ])
    created = await reconcile_user_printers(db_session, auth_user.id)
    assert created == 1
    printer = (await db_session.execute(select(UserPrinterDevice))).scalar_one()
    assert printer.name == "Voron 2.4"
    binding = (await db_session.execute(select(PrinterConnectionBinding))).scalar_one()
    assert (binding.provider, binding.host, binding.port) == ("moonraker", "192.168.1.21", 7125)
    assert binding.physical_printer_id == printer.id


@pytest.mark.asyncio
async def test_known_endpoint_is_idempotent(db_session: AsyncSession, auth_user: User):
    obs = [_obs(printer_settings_id="Voron 0.4", print_host="192.168.1.21", host_type="moonraker")]
    for _ in range(2):
        await _observe(db_session, auth_user, obs)
        await reconcile_user_printers(db_session, auth_user.id)
    assert await _count(db_session, UserPrinterDevice) == 1
    assert await _count(db_session, PrinterConnectionBinding) == 1


@pytest.mark.asyncio
async def test_several_presets_one_endpoint_one_printer(db_session: AsyncSession, auth_user: User):
    await _make_profile(db_session, auth_user, "04", "Voron 0.4")
    await _make_profile(db_session, auth_user, "06", "Voron 0.6")
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="Voron 0.4", print_host="192.168.1.21", host_type="moonraker"),
        _obs(printer_settings_id="Voron 0.6", print_host="192.168.1.21", host_type="moonraker"),
    ])
    await reconcile_user_printers(db_session, auth_user.id)
    assert await _count(db_session, UserPrinterDevice) == 1
    assert await _count(db_session, UserPrinterProfileLink) == 2  # both configs on one printer


@pytest.mark.asyncio
async def test_four_ips_become_four_printers(db_session: AsyncSession, auth_user: User):
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="Voron 0.4", printer_model="Voron 2.4",
             print_host=f"192.168.1.{n}", host_type="moonraker")
        for n in (21, 22, 23, 24)
    ])
    created = await reconcile_user_printers(db_session, auth_user.id)
    assert created == 4
    assert await _count(db_session, UserPrinterDevice) == 4
    assert await _count(db_session, PrinterConnectionBinding) == 4


@pytest.mark.asyncio
async def test_same_ip_different_endpoint_is_separate(db_session: AsyncSession, auth_user: User):
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="A", print_host="192.168.1.21", host_type="moonraker"),
        _obs(printer_settings_id="B", print_host="192.168.1.21", host_type="octoprint"),
    ])
    await reconcile_user_printers(db_session, auth_user.id)
    assert await _count(db_session, UserPrinterDevice) == 2  # 7125 vs 5000


@pytest.mark.asyncio
async def test_unmatched_still_creates_printer_without_link(db_session: AsyncSession, auth_user: User):
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="Unknown", print_host="192.168.1.50", host_type="moonraker"),
    ])
    await reconcile_user_printers(db_session, auth_user.id)
    assert await _count(db_session, UserPrinterDevice) == 1
    assert await _count(db_session, UserPrinterProfileLink) == 0


def test_normalize_endpoint():
    assert normalize_endpoint("192.168.1.21", "moonraker")["normalized"] == "moonraker|http|192.168.1.21|7125|"
    assert normalize_endpoint("http://192.168.1.21:5000/x", "octoprint")["normalized"] == "octoprint|http|192.168.1.21|5000|/x"
    assert (
        normalize_endpoint("192.168.1.21", "moonraker")["normalized"]
        != normalize_endpoint("192.168.1.21", "octoprint")["normalized"]
    )
