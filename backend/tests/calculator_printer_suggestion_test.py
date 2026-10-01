"""Which of a user's printers a sliced job names, from the machine in its G-code."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.calculator import CalculatorGcodeParseResponse
from app.services import subscription_service
from app.services.calculator_printer_suggestion_service import (
    attach_suggested_physical_printers,
)


@pytest.fixture(autouse=True)
def _no_paywall(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(subscription_service._settings_cache, "paywall_enforced", False)


def _job(
    *,
    settings_id: str | None = None,
    model: str | None = None,
    nozzle: float | None = None,
) -> CalculatorGcodeParseResponse:
    return CalculatorGcodeParseResponse(
        file_name="job.gcode",
        file_size_bytes=1,
        printer_settings_id=settings_id,
        printer_model=model,
        nozzle_diameter_mm=nozzle,
    )


async def _suggest(
    db: AsyncSession, user: User, job: CalculatorGcodeParseResponse
) -> list[int]:
    [result] = await attach_suggested_physical_printers(db, [job], user_id=user.id)
    return result.suggested_physical_printer_ids


def _profile(slug: str, name: str, *, owner: User | None = None, **fields) -> PrinterProfile:
    return PrinterProfile(
        slug=slug,
        name=name,
        owner_user_id=owner.id if owner else None,
        source="user" if owner else "system",
        is_official=owner is None,
        active=True,
        **fields,
    )


async def _device(
    db: AsyncSession, user: User, name: str, *profiles: PrinterProfile
) -> UserPrinterDevice:
    device = UserPrinterDevice(user_id=user.id, name=name)
    db.add(device)
    await db.flush()
    db.add_all(
        UserPrinterProfileLink(
            user_id=user.id, physical_printer_id=device.id, printer_profile_id=profile.id
        )
        for profile in profiles
    )
    await db.flush()
    return device


@pytest.fixture
async def fleet(db_session: AsyncSession, auth_user: User) -> dict[str, UserPrinterDevice]:
    stranger = User(
        email="stranger@example.com", username="stranger", password_hash="x", active=True
    )
    db_session.add(stranger)
    await db_session.flush()

    p2s_04 = _profile(
        "p2s-04", "Bambu Lab P2S 0.4 nozzle", setting_id="GM049", nozzle_diameters=[0.4]
    )
    p2s_06 = _profile(
        "p2s-06",
        "Bambu Lab P2S 0.6 nozzle",
        setting_id="GM050",
        orcaslicer_settings={"nozzle_diameter": ["0.6"]},
    )
    voron_own = _profile(
        "voron-own", "Voron 2.4 350", owner=auth_user, setting_id="Voron 2.4 350"
    )
    voron_04 = _profile("voron-04", "Voron 2.4 350 0.4 nozzle", setting_id="Voron 2.4 350 0.4 nozzle")
    db_session.add_all([p2s_04, p2s_06, voron_own, voron_04])
    await db_session.flush()

    return {
        "p2s": await _device(db_session, auth_user, "P2S", p2s_04, p2s_06),
        "voron": await _device(db_session, auth_user, "Voron", voron_own, voron_04),
        "stranger": await _device(db_session, stranger, "Their P2S", p2s_04),
    }


@pytest.mark.asyncio
async def test_a_bambu_printer_linked_only_to_catalog_profiles_is_recognised(
    db_session: AsyncSession, auth_user: User, fleet: dict[str, UserPrinterDevice]
) -> None:
    exact = _job(settings_id="  bambu lab p2s 0.4 NOZZLE ", model="Bambu Lab P2S", nozzle=0.4)
    by_catalog_id = _job(settings_id="GM049")

    assert await _suggest(db_session, auth_user, exact) == [fleet["p2s"].id]
    assert await _suggest(db_session, auth_user, by_catalog_id) == [fleet["p2s"].id]


@pytest.mark.asyncio
async def test_a_renamed_own_profile_still_finds_its_printer_by_the_model(
    db_session: AsyncSession, auth_user: User, fleet: dict[str, UserPrinterDevice]
) -> None:
    exact = _job(settings_id="Voron 2.4 350", model="Voron 2.4 350", nozzle=0.4)
    renamed = _job(settings_id="my old voron preset", model="Voron 2.4 350", nozzle=0.4)

    assert await _suggest(db_session, auth_user, exact) == [fleet["voron"].id]
    assert await _suggest(db_session, auth_user, renamed) == [fleet["voron"].id]


@pytest.mark.asyncio
async def test_unknown_machines_and_other_peoples_printers_are_never_suggested(
    db_session: AsyncSession, auth_user: User, fleet: dict[str, UserPrinterDevice]
) -> None:
    assert await _suggest(db_session, auth_user, _job(settings_id="Prusa MK4", model="Prusa MK4")) == []
    assert await _suggest(db_session, auth_user, _job()) == []
    # "P2" is a prefix of "P2S" but not a model followed by a nozzle suffix.
    assert await _suggest(db_session, auth_user, _job(model="Bambu Lab P2")) == []

    ids = await _suggest(db_session, auth_user, _job(settings_id="Bambu Lab P2S 0.4 nozzle"))
    assert fleet["stranger"].id not in ids


@pytest.mark.asyncio
async def test_the_nozzle_prefers_the_printer_that_has_it_but_never_hides_the_rest(
    db_session: AsyncSession, auth_user: User, fleet: dict[str, UserPrinterDevice]
) -> None:
    only_06 = _profile("p2s-06-only", "Bambu Lab P2S 0.6 nozzle", nozzle_diameters=[0.6])
    db_session.add(only_06)
    await db_session.flush()
    second = await _device(db_session, auth_user, "P2S with a big nozzle", only_06)

    model_only = {"model": "Bambu Lab P2S"}
    both = await _suggest(db_session, auth_user, _job(**model_only))
    assert both == sorted([fleet["p2s"].id, second.id])

    # The first P2S carries a 0.6 as well, the second only a 0.6: both have it.
    assert await _suggest(db_session, auth_user, _job(**model_only, nozzle=0.6)) == both
    # Only the first one carries a 0.4.
    assert await _suggest(db_session, auth_user, _job(**model_only, nozzle=0.4)) == [fleet["p2s"].id]
    # Nobody has 0.2, so the nozzle narrows nothing.
    assert await _suggest(db_session, auth_user, _job(**model_only, nozzle=0.2)) == both


@pytest.mark.asyncio
async def test_many_jobs_cost_one_query_and_a_file_without_a_machine_costs_none(
    db_session: AsyncSession, auth_user: User, fleet: dict[str, UserPrinterDevice]
) -> None:
    statements: list[str] = []

    def count(conn, cursor, statement, *args):  # noqa: ANN001
        statements.append(statement)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", count)
    try:
        jobs = [
            _job(settings_id="Bambu Lab P2S 0.4 nozzle"),
            _job(settings_id="Voron 2.4 350"),
            _job(settings_id="Bambu Lab P2S 0.4 nozzle"),
            _job(),
        ]
        results = await attach_suggested_physical_printers(db_session, jobs, user_id=auth_user.id)
        await attach_suggested_physical_printers(db_session, [_job()], user_id=auth_user.id)
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert [item.suggested_physical_printer_ids for item in results] == [
        [fleet["p2s"].id],
        [fleet["voron"].id],
        [fleet["p2s"].id],
        [],
    ]
    assert len(statements) == 1


@pytest.mark.asyncio
async def test_two_printers_on_one_exact_preset_are_both_suggested(
    db_session: AsyncSession, auth_user: User, fleet: dict[str, UserPrinterDevice]
) -> None:
    profile = _profile("shared-own", "Shared machine", owner=auth_user)
    db_session.add(profile)
    await db_session.flush()
    first = await _device(db_session, auth_user, "One", profile)
    second = await _device(db_session, auth_user, "Two", profile)

    assert await _suggest(db_session, auth_user, _job(settings_id="Shared machine")) == [
        first.id,
        second.id,
    ]


@pytest.mark.asyncio
async def test_excerpt_endpoint_returns_the_printers_the_file_names(
    auth_client: AsyncClient, fleet: dict[str, UserPrinterDevice]
) -> None:
    head = (
        b"; generated by OrcaSlicer 2.3.0 on 2026-09-01 at 10:00:00 UTC\n"
        b"M83\n"
        b"; total filament used [g] = 14.88\n"
        b"; estimated printing time (normal mode) = 1h 0m 0s\n"
        b"; printer_model = Bambu Lab P2S\n"
        b"; printer_settings_id = Bambu Lab P2S 0.4 nozzle\n"
        b"; nozzle_diameter = 0.4\n"
    )

    response = await auth_client.post(
        "/api/v1/calculator/gcode-excerpts/parse",
        data={"file_name": "p2s.gcode", "file_size_bytes": str(len(head)), "container": "plain_gcode"},
        files=[("head", ("p2s.gcode", head, "application/octet-stream"))],
    )

    assert response.status_code == 200
    [job] = response.json()["jobs"]
    assert job["printer_settings_id"] == "Bambu Lab P2S 0.4 nozzle"
    assert job["suggested_physical_printer_ids"] == [fleet["p2s"].id]
