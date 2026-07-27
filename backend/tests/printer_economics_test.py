"""What a machine costs to run: the sums, the guards, and the awkward inputs."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calculator_profile import UserCalculatorProfile
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.services.printer_economics_service import resolve_economics, suggest_economics


async def _printer(
    db: AsyncSession, user: User, name: str = "Voron at home", **fields
) -> UserPrinterDevice:
    printer = UserPrinterDevice(
        user_id=user.id, name=name, device_fingerprint=None, supports_hh=False, **fields
    )
    db.add(printer)
    await db.commit()
    await db.refresh(printer)
    return printer


async def _profile(db: AsyncSession, user: User, **overrides) -> UserCalculatorProfile:
    profile = UserCalculatorProfile(
        user_id=user.id,
        electricity_cost_per_kwh=overrides.get("electricity_cost_per_kwh", 6.0),
        printer_power_w=overrides.get("printer_power_w", 350.0),
        printing_rate_per_hour=overrides.get("printing_rate_per_hour", 170.0),
        amortization_rate_per_hour=overrides.get("amortization_rate_per_hour", 16.0),
    )
    db.add(profile)
    await db.commit()
    return profile


@pytest.mark.asyncio
async def test_a_machine_nobody_configured_changes_nothing(
    db_session: AsyncSession, auth_user: User
) -> None:
    """The whole point: existing accounts must keep their numbers to the kopeck."""
    await _profile(db_session, auth_user)
    printer = await _printer(db_session, auth_user)

    resolved = await resolve_economics(db_session, printer)

    assert resolved.printer_power_w == 350.0
    assert resolved.printing_rate_per_hour == 170.0
    assert resolved.amortization_rate_per_hour == 16.0
    assert resolved.sources["rate"] == "account"
    assert resolved.rate_below_cost is False


@pytest.mark.asyncio
async def test_the_rate_splits_without_counting_anything_twice(
    db_session: AsyncSession, auth_user: User
) -> None:
    """Electricity and wear are their own lines, so the rate cannot carry them too."""
    await _profile(db_session, auth_user, electricity_cost_per_kwh=6.9)
    printer = await _printer(
        db_session,
        auth_user,
        purchase_cost=120_000.0,
        useful_life_hours=7000,
        average_power_watts=350.0,
        maintenance_cost_per_hour=6.6,
        machine_hour_rate=45.0,
    )

    resolved = await resolve_economics(db_session, printer)

    assert round(resolved.depreciation_per_hour, 2) == 17.14
    assert round(resolved.electricity_per_hour, 2) == 2.42
    assert resolved.maintenance_per_hour == 6.6
    hourly = (
        resolved.electricity_per_hour
        + resolved.amortization_rate_per_hour
        + resolved.printing_rate_per_hour
    )
    assert round(hourly, 2) == 45.0


@pytest.mark.asyncio
async def test_a_rate_under_its_own_cost_never_pushes_the_order_down(
    db_session: AsyncSession, auth_user: User
) -> None:
    """Charging below cost is a person's right; making the order cheaper than
    its parts by way of a negative line is not."""
    await _profile(db_session, auth_user)
    printer = await _printer(
        db_session,
        auth_user,
        purchase_cost=200_000.0,
        useful_life_hours=1000,
        average_power_watts=400.0,
        maintenance_cost_per_hour=10.0,
        machine_hour_rate=5.0,
    )

    resolved = await resolve_economics(db_session, printer)

    assert resolved.printing_rate_per_hour == 0.0
    assert resolved.rate_below_cost is True


@pytest.mark.asyncio
async def test_a_life_of_zero_hours_is_refused_before_it_can_divide(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    printer = await _printer(db_session, auth_user)

    refused = await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/economics",
        json={"purchase_cost": 90_000, "useful_life_hours": 0},
    )
    assert refused.status_code == 422

    negative = await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/economics",
        json={"purchase_cost": -5},
    )
    assert negative.status_code == 422

    absurd = await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/economics",
        json={"average_power_watts": 999_999},
    )
    assert absurd.status_code == 422


@pytest.mark.asyncio
async def test_a_trade_in_value_cannot_exceed_what_the_machine_cost(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    printer = await _printer(db_session, auth_user)

    refused = await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/economics",
        json={"purchase_cost": 50_000, "residual_value": 60_000},
    )
    assert refused.status_code == 422


@pytest.mark.asyncio
async def test_economics_of_someone_elses_machine_stay_out_of_reach(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    from app.services.legal_acceptance_service import (
        CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        CURRENT_TERMS_VERSION,
    )

    stranger = User(
        email="other-owner@example.com",
        username="otherowner",
        password_hash="$2b$12$test",
        active=True,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db_session.add(stranger)
    await db_session.commit()
    theirs = await _printer(db_session, stranger, name="Not yours")

    read = await auth_client.get(f"/api/v1/physical-printers/{theirs.id}/economics")
    assert read.status_code == 404

    write = await auth_client.patch(
        f"/api/v1/physical-printers/{theirs.id}/economics",
        json={"machine_hour_rate": 1000},
    )
    assert write.status_code == 404


@pytest.mark.asyncio
async def test_a_value_can_be_cleared_back_to_the_account(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    await _profile(db_session, auth_user)
    printer = await _printer(db_session, auth_user)

    await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/economics",
        json={"average_power_watts": 500, "machine_hour_rate": 60},
    )
    cleared = await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/economics",
        json={"average_power_watts": None},
    )

    assert cleared.status_code == 200
    body = cleared.json()
    assert body["average_power_watts"] is None
    assert body["machine_hour_rate"] == 60.0
    assert body["calculator_printer_power_w"] == 350.0
    assert body["sources"]["power"] == "account"


@pytest.mark.asyncio
async def test_orcaslicer_own_hourly_cost_wins_when_a_person_filled_it(
    db_session: AsyncSession, auth_user: User
) -> None:
    """time_cost is Orca's own field; if they set it there, they meant it."""
    await _profile(db_session, auth_user)
    printer = await _printer(db_session, auth_user, machine_hour_rate=45.0)
    configuration = PrinterProfile(
        owner_user_id=auth_user.id,
        is_official=False,
        name="Voron 2.4 350 0.4",
        slug="voron-2-4-350-economics-test",
        active=True,
        source="orcaslicer",
        orcaslicer_settings={"time_cost": "80"},
    )
    db_session.add(configuration)
    await db_session.flush()
    db_session.add(
        UserPrinterProfileLink(
            user_id=auth_user.id,
            physical_printer_id=printer.id,
            printer_profile_id=configuration.id,
        )
    )
    await db_session.commit()

    resolved = await resolve_economics(db_session, printer)

    assert resolved.machine_hour_rate == 80.0
    assert resolved.sources["rate"] == "orca"


@pytest.mark.asyncio
async def test_garbage_in_the_orca_field_is_ignored_quietly(
    db_session: AsyncSession, auth_user: User
) -> None:
    await _profile(db_session, auth_user)
    printer = await _printer(db_session, auth_user, machine_hour_rate=45.0)
    for index, value in enumerate(["0", "", "  ", "abc", None, ["0"]]):
        configuration = PrinterProfile(
            owner_user_id=auth_user.id,
            is_official=False,
            name=f"Broken {index}",
            slug=f"broken-time-cost-{index}",
            active=True,
            source="orcaslicer",
            orcaslicer_settings={"time_cost": value},
        )
        db_session.add(configuration)
        await db_session.flush()
        db_session.add(
            UserPrinterProfileLink(
                user_id=auth_user.id,
                physical_printer_id=printer.id,
                printer_profile_id=configuration.id,
            )
        )
    await db_session.commit()

    resolved = await resolve_economics(db_session, printer)

    assert resolved.machine_hour_rate == 45.0
    assert resolved.sources["rate"] == "printer"


@pytest.mark.asyncio
async def test_suggestions_follow_the_machine_and_how_hard_it_works(
    db_session: AsyncSession, auth_user: User
) -> None:
    catalog = Printer(
        name="Voron 2.4 350",
        manufacturer="Voron",
        model="2.4 350",
        slug="voron-2-4-350-suggestion-test",
        build_volume_x=350,
        build_volume_y=350,
        build_volume_z=250,
        technology="FFF",
    )
    db_session.add(catalog)
    await db_session.flush()
    printer = await _printer(db_session, auth_user, printer_id=catalog.id)

    intensive = await suggest_economics(db_session, printer, "intensive")
    occasional = await suggest_economics(db_session, printer, "occasional")
    nonsense = await suggest_economics(db_session, printer, "лягушка")

    assert intensive.useful_life_hours > occasional.useful_life_hours
    assert nonsense.useful_life_hours == 7000
    assert intensive.average_power_watts >= 350
    # A machine people build themselves is a guess, and we say so.
    assert intensive.machine.confidence == "modified"


@pytest.mark.asyncio
async def test_a_machine_we_know_nothing_about_still_gets_numbers(
    db_session: AsyncSession, auth_user: User
) -> None:
    printer = await _printer(db_session, auth_user, name="Безымянная")

    suggestion = await suggest_economics(db_session, printer)

    assert suggestion.average_power_watts > 0
    assert suggestion.useful_life_hours > 0
    assert suggestion.machine.machine_class == "unknown"
