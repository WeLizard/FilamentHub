"""Stable, tenant-owned pagination for the user's notification feed."""

from datetime import datetime, timezone

from httpx import AsyncClient

from app.models.notification import Notification, NotificationType
from app.models.user import User
from tests.conftest import accepted_legal


def _notification(user_id: int, sequence: int, *, created_at: datetime) -> Notification:
    return Notification(
        user_id=user_id,
        type=NotificationType.ADMIN_MESSAGE,
        title=f"notification-{sequence}",
        message=f"message-{sequence}",
        created_at=created_at,
        read=sequence % 2 == 0,
    )


async def test_notification_feed_is_stable_when_a_new_notification_arrives(
    auth_client: AsyncClient,
    auth_user: User,
    db_session,
) -> None:
    timestamp = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    existing = [_notification(auth_user.id, index, created_at=timestamp) for index in range(5)]
    db_session.add_all(existing)
    await db_session.commit()

    first = await auth_client.get("/api/v1/notifications/feed", params={"limit": 2})
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert [item["id"] for item in first_body["items"]] == [existing[4].id, existing[3].id]
    assert first_body["next_cursor"] == existing[3].id
    assert first_body["unread_count"] == 2

    newest = _notification(auth_user.id, 5, created_at=timestamp)
    db_session.add(newest)
    await db_session.commit()

    second = await auth_client.get(
        "/api/v1/notifications/feed",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert [item["id"] for item in second_body["items"]] == [existing[2].id, existing[1].id]
    assert not (
        {item["id"] for item in first_body["items"]} & {item["id"] for item in second_body["items"]}
    )
    assert second_body["next_cursor"] == existing[1].id

    last = await auth_client.get(
        "/api/v1/notifications/feed",
        params={"limit": 2, "cursor": second_body["next_cursor"]},
    )
    assert [item["id"] for item in last.json()["items"]] == [existing[0].id]
    assert last.json()["next_cursor"] is None


async def test_notification_feed_filter_and_detail_are_tenant_owned(
    auth_client: AsyncClient,
    auth_user: User,
    db_session,
) -> None:
    other = User(
        email="notification-owner@example.com",
        username="notification_owner",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        **accepted_legal(),
    )
    db_session.add(other)
    await db_session.flush()
    timestamp = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    unread = _notification(auth_user.id, 1, created_at=timestamp)
    read = _notification(auth_user.id, 2, created_at=timestamp)
    foreign = _notification(other.id, 3, created_at=timestamp)
    db_session.add_all([unread, read, foreign])
    await db_session.commit()

    feed = await auth_client.get(
        "/api/v1/notifications/feed",
        params={"limit": 10, "unread_only": True},
    )
    assert feed.status_code == 200, feed.text
    assert [item["id"] for item in feed.json()["items"]] == [unread.id]
    assert feed.json()["unread_count"] == 1

    owned = await auth_client.get(f"/api/v1/notifications/{read.id}")
    assert owned.status_code == 200 and owned.json()["id"] == read.id
    denied = await auth_client.get(f"/api/v1/notifications/{foreign.id}")
    assert denied.status_code == 404
    assert denied.json()["detail"]["code"] == "ERR_NOTIFICATION_NOT_FOUND"


async def test_legacy_notification_pages_remain_available(
    auth_client: AsyncClient,
    auth_user: User,
    db_session,
) -> None:
    timestamp = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    rows = [_notification(auth_user.id, index, created_at=timestamp) for index in range(3)]
    db_session.add_all(rows)
    await db_session.commit()

    response = await auth_client.get(
        "/api/v1/notifications/",
        params={"page": 2, "size": 2},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["page"], body["size"], body["pages"], body["total"]) == (2, 2, 2, 3)
    assert len(body["items"]) == 1

    assert (
        await auth_client.get("/api/v1/notifications/feed", params={"limit": 0})
    ).status_code == 422
    assert (
        await auth_client.get("/api/v1/notifications/feed", params={"limit": 101})
    ).status_code == 422
