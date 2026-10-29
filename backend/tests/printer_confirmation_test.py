"""Observed printers are proposals until a person or a real device confirms them."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.printer_connection_observation import PrinterConnectionObservationIn
from app.services.physical_printer_discovery_service import reconcile_user_printers
from app.services.preset_slot_sync_service import touch_device_last_seen
from app.services.printer_connection_observation_service import record_observations
from app.services.printer_merge_service import merge_printers, preview_printer_merge
from app.services.tier_metrics_service import live_printer_counts

BASE = "/api/v1/physical-printers"
ENDPOINT = {
    "printer_settings_id": "Voron 0.4",
    "print_host": "192.168.1.21",
    "host_type": "moonraker",
}


async def _observe(db: AsyncSession, user: User, **fields) -> None:
    await record_observations(
        db, user.id, "inst-1", [PrinterConnectionObservationIn(**{**ENDPOINT, **fields})]
    )
    await reconcile_user_printers(db, user.id)


async def _devices(db: AsyncSession) -> list[UserPrinterDevice]:
    return list((await db.execute(select(UserPrinterDevice).order_by(UserPrinterDevice.id))).scalars())


async def _ghost(db: AsyncSession, user: User) -> UserPrinterDevice:
    await _observe(db, user)
    return (await _devices(db))[0]


@pytest.mark.asyncio
async def test_endpoint_only_observation_is_a_suggestion_not_a_printer(
    auth_client, db_session: AsyncSession, auth_user: User
):
    ghost = await _ghost(db_session, auth_user)
    assert ghost.confirmed_at is None

    listed = await auth_client.get(BASE)
    assert listed.status_code == 200 and listed.json() == []
    feed = await auth_client.get(f"{BASE}/feed")
    assert feed.json()["items"] == [] and feed.json()["total"] == 0

    suggestions = (await auth_client.get(f"{BASE}/suggestions")).json()
    assert [item["id"] for item in suggestions] == [ghost.id]
    assert suggestions[0]["same_model_printer_ids"] == []


@pytest.mark.asyncio
async def test_observation_with_device_identity_creates_a_confirmed_printer(
    auth_client, db_session: AsyncSession, auth_user: User
):
    await _observe(db_session, auth_user, device_identity={"kind": "moonraker_instance", "token": "a" * 64})
    assert (await _devices(db_session))[0].confirmed_at is not None
    assert [item["confirmed"] for item in (await auth_client.get(BASE)).json()] == [True]
    assert (await auth_client.get(f"{BASE}/suggestions")).json() == []


@pytest.mark.asyncio
async def test_confirm_publishes_and_dismiss_hides_without_creating_a_duplicate(
    auth_client, db_session: AsyncSession, auth_user: User
):
    ghost = await _ghost(db_session, auth_user)

    assert (await auth_client.post(f"{BASE}/{ghost.id}/dismiss")).status_code == 204
    assert (await auth_client.post(f"{BASE}/{ghost.id}/dismiss")).status_code == 204
    assert (await auth_client.get(f"{BASE}/suggestions")).json() == []
    assert (await auth_client.get(BASE)).json() == []

    await _observe(db_session, auth_user)
    assert len(await _devices(db_session)) == 1
    assert (await auth_client.get(f"{BASE}/suggestions")).json() == []

    assert (await auth_client.post(f"{BASE}/{ghost.id}/confirm")).status_code == 204
    assert (await auth_client.post(f"{BASE}/{ghost.id}/confirm")).status_code == 204
    listed = (await auth_client.get(BASE)).json()
    assert [(item["id"], item["confirmed"]) for item in listed] == [(ghost.id, True)]
    assert (await auth_client.get(f"{BASE}/feed")).json()["total"] == 1


@pytest.mark.asyncio
async def test_foreign_printer_cannot_be_confirmed_or_dismissed(
    auth_client, db_session: AsyncSession, auth_user: User
):
    other = User(email="o@example.com", username="other", password_hash="x", active=True)
    db_session.add(other)
    await db_session.flush()
    foreign = UserPrinterDevice(user_id=other.id, name="Theirs")
    db_session.add(foreign)
    await db_session.commit()
    for action in ("confirm", "dismiss"):
        assert (await auth_client.post(f"{BASE}/{foreign.id}/{action}")).status_code == 404


@pytest.mark.asyncio
async def test_suggestion_offers_confirmed_printers_of_the_same_model(
    auth_client, db_session: AsyncSession, auth_user: User
):
    model = Printer(name="Voron 2.4", manufacturer="Voron", model="2.4", slug="voron-2-4")
    db_session.add(model)
    await db_session.flush()
    known = UserPrinterDevice(user_id=auth_user.id, name="Known", printer_id=model.id)
    known.confirmed_at = func.now()
    db_session.add(known)
    await db_session.flush()
    ghost = await _ghost(db_session, auth_user)
    ghost = (await _devices(db_session))[-1]
    ghost.printer_id = model.id
    profile = PrinterProfile(
        owner_user_id=auth_user.id, name="Voron 2.4 0.4 nozzle", slug="v24", setting_id="v24",
        active=True,
    )
    db_session.add(profile)
    await db_session.flush()
    db_session.add(UserPrinterProfileLink(
        user_id=auth_user.id, physical_printer_id=ghost.id, printer_profile_id=profile.id
    ))
    await db_session.commit()

    item = (await auth_client.get(f"{BASE}/suggestions")).json()[0]
    assert item["id"] == ghost.id
    assert item["catalog_printer_name"] == "Voron 2.4"
    assert item["profile_names"] == ["Voron 2.4 0.4 nozzle"]
    assert item["same_model_printer_ids"] == [known.id]


@pytest.mark.asyncio
async def test_ghost_merges_into_a_confirmed_printer(db_session: AsyncSession, auth_user: User):
    ghost = await _ghost(db_session, auth_user)
    target = UserPrinterDevice(user_id=auth_user.id, name="Real")
    db_session.add(target)
    await db_session.commit()
    ghost_id, target_id = ghost.id, target.id

    preview = await preview_printer_merge(db_session, auth_user.id, ghost_id, target_id)
    assert preview["allowed"] is True
    await merge_printers(db_session, auth_user.id, ghost_id, target_id, preview["revision"])

    remaining = await _devices(db_session)
    assert [device.id for device in remaining] == [target_id]
    assert remaining[0].confirmed_at is not None


@pytest.mark.asyncio
async def test_device_report_confirms_an_observed_printer(db_session: AsyncSession, auth_user: User):
    ghost = await _ghost(db_session, auth_user)
    touch_device_last_seen(ghost)
    await db_session.commit()
    assert ghost.last_seen_at is not None and ghost.confirmed_at is not None


@pytest.mark.asyncio
async def test_tier_counts_confirmed_printers_and_ignores_dismissed(
    db_session: AsyncSession, auth_user: User
):
    ghost = await _ghost(db_session, auth_user)
    assert (await live_printer_counts(db_session))[0] == 0

    ghost.confirmed_at = func.now()
    await db_session.commit()
    assert (await live_printer_counts(db_session))[0] == 1

    ghost.dismissed_at = func.now()
    await db_session.commit()
    assert (await live_printer_counts(db_session))[0] == 0
