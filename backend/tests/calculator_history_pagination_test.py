"""Stable, owner-scoped pagination for Calculator Pro history."""

import base64
import json
from datetime import datetime, timezone

from httpx import AsyncClient

from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.subscription import Subscription
from app.models.user import User
from tests.conftest import accepted_legal


def _cursor(timestamp: str, entry_id: int) -> str:
    payload = json.dumps([timestamp, entry_id], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _history(user_id: int, sequence: int, *, created_at: datetime) -> CalculatorHistoryEntry:
    return CalculatorHistoryEntry(
        user_id=user_id,
        title=f"estimate-{sequence}",
        pricing_method="combined",
        request_data={"pricing_method": "combined", "quantity": 1},
        result_data={
            "pricing_method": "combined",
            "cost_first_part": sequence,
            "cost_subsequent_parts": sequence,
            "cost_total": sequence,
            "cost_final": sequence,
            "quantity": 1,
        },
        created_at=created_at,
    )


async def _grant_calculator_access(db_session, user_id: int) -> None:
    db_session.add(
        Subscription(
            user_id=user_id,
            is_comp=True,
        )
    )
    await db_session.commit()


async def test_history_cursor_is_stable_across_equal_timestamps_and_newer_insert(
    auth_client: AsyncClient,
    auth_user: User,
    db_session,
) -> None:
    await _grant_calculator_access(db_session, auth_user.id)
    timestamp = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    existing = [_history(auth_user.id, index, created_at=timestamp) for index in range(5)]
    db_session.add_all(existing)
    await db_session.commit()

    first = await auth_client.get("/api/v1/calculator/history/feed", params={"limit": 2})
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert [item["id"] for item in first_body["items"]] == [existing[4].id, existing[3].id]
    assert all(item["source"] == "manual" for item in first_body["items"])
    assert first_body["has_more"] is True
    assert first_body["next_cursor"]

    newest = _history(auth_user.id, 5, created_at=timestamp)
    db_session.add(newest)
    await db_session.commit()

    second = await auth_client.get(
        "/api/v1/calculator/history/feed",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert [item["id"] for item in second_body["items"]] == [existing[2].id, existing[1].id]
    assert not (
        {item["id"] for item in first_body["items"]} & {item["id"] for item in second_body["items"]}
    )

    terminal = await auth_client.get(
        "/api/v1/calculator/history/feed",
        params={"limit": 2, "cursor": second_body["next_cursor"]},
    )
    assert terminal.status_code == 200, terminal.text
    assert [item["id"] for item in terminal.json()["items"]] == [existing[0].id]
    assert terminal.json()["has_more"] is False
    assert terminal.json()["next_cursor"] is None


async def test_history_cursor_remains_owner_scoped(
    auth_client: AsyncClient,
    auth_user: User,
    db_session,
) -> None:
    await _grant_calculator_access(db_session, auth_user.id)
    other = User(
        email="calculator-history-owner@example.com",
        username="calculator_history_owner",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        **accepted_legal(),
    )
    db_session.add(other)
    await db_session.flush()
    timestamp = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    owned = _history(auth_user.id, 1, created_at=timestamp)
    foreign = _history(other.id, 2, created_at=timestamp)
    db_session.add_all([owned, foreign])
    await db_session.commit()

    response = await auth_client.get("/api/v1/calculator/history/feed", params={"limit": 10})
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [owned.id]
    assert response.json()["total"] == 1

    detail = await auth_client.get(f"/api/v1/calculator/history/{foreign.id}")
    assert detail.status_code == 404
    owned_detail = await auth_client.get(f"/api/v1/calculator/history/{owned.id}")
    assert owned_detail.status_code == 200
    assert owned_detail.json()["request_data"]["pricing_method"] == "combined"


async def test_history_cursor_validation_and_legacy_pages(
    auth_client: AsyncClient,
    auth_user: User,
    db_session,
) -> None:
    await _grant_calculator_access(db_session, auth_user.id)
    timestamp = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    rows = [_history(auth_user.id, index, created_at=timestamp) for index in range(3)]
    db_session.add_all(rows)
    await db_session.commit()

    legacy = await auth_client.get(
        "/api/v1/calculator/history",
        params={"page": 2, "size": 2},
    )
    assert legacy.status_code == 200, legacy.text
    assert [item["id"] for item in legacy.json()["items"]] == [rows[0].id]
    assert legacy.json()["total"] == 3
    assert legacy.json()["next_cursor"] is None
    assert legacy.json()["has_more"] is False

    malformed = await auth_client.get(
        "/api/v1/calculator/history",
        params={"cursor": "not-an-opaque-cursor"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["detail"]["code"] == "ERR_CALCULATOR_HISTORY_CURSOR_INVALID"
    compact_malformed = await auth_client.get(
        "/api/v1/calculator/history/feed",
        params={"cursor": "not-an-opaque-cursor"},
    )
    assert compact_malformed.status_code == 422
    assert compact_malformed.json()["detail"]["code"] == "ERR_CALCULATOR_HISTORY_CURSOR_INVALID"
    for invalid_cursor in (
        _cursor("9999-12-31T23:59:59.999999-23:59", 1),
        _cursor("0001-01-01T00:00:00+23:59", 1),
        _cursor("2026-09-12T12:00:00+00:00", 2_147_483_648),
    ):
        invalid_boundary = await auth_client.get(
            "/api/v1/calculator/history",
            params={"cursor": invalid_cursor},
        )
        assert invalid_boundary.status_code == 422
        assert invalid_boundary.json()["detail"]["code"] == "ERR_CALCULATOR_HISTORY_CURSOR_INVALID"
    assert (
        await auth_client.get("/api/v1/calculator/history", params={"size": 0})
    ).status_code == 422
    assert (
        await auth_client.get("/api/v1/calculator/history", params={"size": 101})
    ).status_code == 422
    assert (
        await auth_client.get("/api/v1/calculator/history/feed", params={"limit": 0})
    ).status_code == 422
    assert (
        await auth_client.get("/api/v1/calculator/history/feed", params={"limit": 101})
    ).status_code == 422


async def test_compact_history_feed_has_a_strict_representative_page_ceiling(
    auth_client: AsyncClient,
    auth_user: User,
    db_session,
) -> None:
    await _grant_calculator_access(db_session, auth_user.id)
    timestamp = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    large_blob = "x" * 50_000
    hostile_text = '\n\r\t"\\\x01\U0001f9f5' * 300
    rows = []
    for index in range(100):
        row = _history(auth_user.id, index, created_at=timestamp)
        row.title = hostile_text[:255]
        row.request_data = {
            "pricing_method": "combined",
            "quantity": 2,
            "private_snapshot": large_blob,
        }
        row.result_data = {
            "pricing_method": "combined",
            "cost_total": 120.5,
            "cost_final": 125.25,
            "quantity": 2,
            "full_breakdown": large_blob,
        }
        row.parsed_gcode = {
            "file_name": hostile_text,
            "thumbnail_data_url": large_blob,
            "materials": [large_blob],
        }
        row.filament_snapshot = {
            "id": index + 1,
            "name": hostile_text,
            "brand_name": hostile_text,
            "material_type": "m" * 500,
            "color_name": "c" * 1000,
        }
        rows.append(row)
    db_session.add_all(rows)
    await db_session.commit()

    response = await auth_client.get("/api/v1/calculator/history/feed", params={"limit": 100})
    assert response.status_code == 200, response.text
    assert len(response.content) < 125_000
    body = response.json()
    assert len(body["items"]) == 100
    assert "request_data" not in body["items"][0]
    assert "result_data" not in body["items"][0]
    assert "parsed_gcode" not in body["items"][0]
    assert "parsed_jobs" not in body["items"][0]
    assert body["items"][0]["source"] == "gcode"
    item = body["items"][0]
    for value in (
        item["title"],
        item["gcode_file"],
        item["filament_snapshot"]["name"],
        item["filament_snapshot"]["brand_name"],
    ):
        assert hostile_text.startswith(value)
        assert "\n" in value
        assert '"' in value
        assert "\\" in value
        assert "\U0001f9f5" in value
