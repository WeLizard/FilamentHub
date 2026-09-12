"""Stable bounded pages for the primary physical-printer card list."""

import base64
import json
from datetime import datetime, timezone

import pytest

from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from tests.conftest import accepted_legal


async def _printer(db_session, user_id: int, name: str, created_at: datetime):
    printer = UserPrinterDevice(user_id=user_id, name=name, created_at=created_at)
    db_session.add(printer)
    await db_session.flush()
    return printer


@pytest.mark.asyncio
async def test_physical_printer_feed_is_stable_owned_and_keeps_nested_shape(
    auth_client, auth_user, db_session
):
    timestamp = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    first = await _printer(db_session, auth_user.id, "First", timestamp)
    second = await _printer(db_session, auth_user.id, "Second", timestamp)
    third = await _printer(db_session, auth_user.id, "Third", timestamp)
    system = MaterialSystem(
        user_id=auth_user.id,
        physical_printer_id=first.id,
        name="Direct feed",
        kind="direct_feed",
        provider="manual",
    )
    stranger = User(
        email="printer-feed-stranger@example.com",
        username="printer_feed_stranger",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        **accepted_legal(),
    )
    db_session.add_all([system, stranger])
    await db_session.flush()
    slot = MaterialSlot(
        user_id=auth_user.id,
        material_system_id=system.id,
        provider_index=0,
        label="Direct",
    )
    connector = PhysicalPrinterConnector(
        user_id=auth_user.id,
        physical_printer_id=first.id,
        material_system_id=system.id,
        provider="manual",
        transport="local",
    )
    profile = PrinterProfile(
        owner_user_id=auth_user.id,
        name="First configuration",
        slug=f"printer-feed-{auth_user.id}",
        is_official=False,
        active=True,
        source="user",
        orcaslicer_settings={},
    )
    db_session.add_all([slot, connector, profile])
    await db_session.flush()
    db_session.add(
        UserPrinterProfileLink(
            user_id=auth_user.id,
            physical_printer_id=first.id,
            printer_profile_id=profile.id,
        )
    )
    foreign = await _printer(db_session, stranger.id, "Foreign", timestamp)
    await db_session.commit()

    page_one = await auth_client.get("/api/v1/physical-printers/feed", params={"size": 2})
    assert page_one.status_code == 200, page_one.text
    body_one = page_one.json()
    assert [item["id"] for item in body_one["items"]] == [first.id, second.id]
    assert body_one["items"][0]["material_systems"][0]["name"] == "Direct feed"
    assert body_one["items"][0]["material_systems"][0]["slots"][0]["provider_index"] == 0
    assert body_one["items"][0]["connectors"][0]["provider"] == "manual"
    assert body_one["items"][0]["printer_profile_ids"] == [profile.id]
    assert body_one["total"] == 3
    assert body_one["has_more"] is True
    assert body_one["next_cursor"]
    assert foreign.id not in [item["id"] for item in body_one["items"]]

    inserted = await _printer(db_session, auth_user.id, "Inserted", timestamp)
    await db_session.commit()
    page_two = await auth_client.get(
        "/api/v1/physical-printers/feed",
        params={"size": 2, "cursor": body_one["next_cursor"]},
    )
    assert page_two.status_code == 200, page_two.text
    body_two = page_two.json()
    assert [item["id"] for item in body_two["items"]] == [third.id, inserted.id]
    assert body_two["total"] == 4
    assert body_two["has_more"] is False
    assert body_two["next_cursor"] is None

    legacy = await auth_client.get("/api/v1/physical-printers")
    assert legacy.status_code == 200
    assert [item["id"] for item in legacy.json()] == [
        first.id,
        second.id,
        third.id,
        inserted.id,
    ]


@pytest.mark.asyncio
async def test_physical_printer_feed_rejects_cursor_and_size_bounds(auth_client):
    timestamp = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    overflow_cursor = (
        base64.urlsafe_b64encode(json.dumps([timestamp.isoformat(), 2_147_483_648]).encode())
        .decode()
        .rstrip("=")
    )
    malformed = await auth_client.get("/api/v1/physical-printers/feed", params={"cursor": "broken"})
    assert malformed.status_code == 422
    assert malformed.json()["detail"]["code"] == "ERR_PHYSICAL_PRINTER_CURSOR_INVALID"
    for params in (
        {"size": 0},
        {"size": 51},
        {"cursor": "x" * 513},
        {"cursor": overflow_cursor},
    ):
        response = await auth_client.get("/api/v1/physical-printers/feed", params=params)
        assert response.status_code == 422
