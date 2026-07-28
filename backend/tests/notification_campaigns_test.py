"""Regression tests for previewed and auditable in-app notification campaigns."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.notification_campaign import (
    NotificationCampaign,
    NotificationCampaignRecipient,
)
from app.models.user import User


async def _user(
    db: AsyncSession,
    *,
    suffix: str,
    active: bool = True,
) -> User:
    user = User(
        email=f"campaign-{suffix}@example.com",
        username=f"campaign_{suffix}",
        full_name=f"Campaign {suffix}",
        password_hash="$2b$12$test",
        active=active,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_campaign_uses_exact_snapshot_and_confirmation_is_idempotent(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    first = await _user(db_session, suffix="first")
    second = await _user(db_session, suffix="second")
    inactive = await _user(db_session, suffix="inactive", active=False)
    await db_session.commit()

    search_response = await admin_client.get(
        "/api/v1/admin/users",
        params={"search": "campaign_first", "active_only": True},
    )
    assert search_response.status_code == 200
    assert [user["id"] for user in search_response.json()["items"]] == [first.id]

    preview_response = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/preview",
        json={
            "audience": "selected",
            "user_ids": [first.id, second.id, inactive.id, 999_999],
            "title": "Scheduled maintenance",
            "message": "The platform will be read-only for ten minutes.",
            "link": "/profile",
        },
    )

    assert preview_response.status_code == 201
    preview = preview_response.json()
    assert preview["recipient_count"] == 2
    assert preview["excluded_user_ids"] == [inactive.id, 999_999]
    assert [recipient["id"] for recipient in preview["recipient_sample"]] == [
        first.id,
        second.id,
    ]
    assert await db_session.scalar(select(func.count(Notification.id))) == 0
    assert (
        await db_session.scalar(select(func.count(NotificationCampaignRecipient.id)))
        == 2
    )

    # The active flag changes after preview, but confirmation must deliver the
    # immutable recipient snapshot rather than re-querying the audience.
    second.active = False
    await db_session.commit()

    confirm_response = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/confirm",
        json={"confirmation_token": preview["confirmation_token"]},
    )
    replay_response = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/confirm",
        json={"confirmation_token": preview["confirmation_token"]},
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["replayed"] is False
    assert confirm_response.json()["recipient_count"] == 2
    assert replay_response.status_code == 200
    assert replay_response.json()["replayed"] is True
    notifications = list(
        (
            await db_session.scalars(
                select(Notification).order_by(Notification.user_id)
            )
        ).all()
    )
    assert [notification.user_id for notification in notifications] == [
        first.id,
        second.id,
    ]
    assert all(
        notification.extra_data == {"campaign_id": preview["campaign_id"]}
        for notification in notifications
    )

    history_response = await admin_client.get(
        "/api/v1/admin/communications/broadcasts"
    )
    assert history_response.status_code == 200
    assert history_response.json()["items"][0]["status"] == "sent"
    assert history_response.json()["items"][0]["recipient_count"] == 2


@pytest.mark.asyncio
async def test_campaign_cancel_expiry_and_legacy_routes_are_enforced(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    recipient = await _user(db_session, suffix="guarded")
    await db_session.commit()

    cancelled_preview_response = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/preview",
        json={
            "audience": "selected",
            "user_ids": [recipient.id],
            "title": "Cancelled campaign",
            "message": "This must not be delivered.",
        },
    )
    assert cancelled_preview_response.status_code == 201
    cancelled_preview = cancelled_preview_response.json()

    cancel_response = await admin_client.delete(
        f"/api/v1/admin/communications/broadcasts/{cancelled_preview['campaign_id']}"
    )
    assert cancel_response.status_code == 200
    cancelled_confirm = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/confirm",
        json={"confirmation_token": cancelled_preview["confirmation_token"]},
    )
    assert cancelled_confirm.status_code == 409
    assert (
        cancelled_confirm.json()["detail"]["code"]
        == "ERR_NOTIFICATION_CAMPAIGN_STATE_INVALID"
    )

    expired_preview_response = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/preview",
        json={
            "audience": "selected",
            "user_ids": [recipient.id],
            "title": "Expired campaign",
            "message": "This must expire before delivery.",
        },
    )
    assert expired_preview_response.status_code == 201
    expired_preview = expired_preview_response.json()
    expired_campaign = await db_session.scalar(
        select(NotificationCampaign).where(
            NotificationCampaign.public_id == expired_preview["campaign_id"]
        )
    )
    assert expired_campaign is not None
    expired_campaign.confirmation_expires_at = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    await db_session.commit()

    expired_confirm = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/confirm",
        json={"confirmation_token": expired_preview["confirmation_token"]},
    )
    assert expired_confirm.status_code == 409
    assert (
        expired_confirm.json()["detail"]["code"]
        == "ERR_NOTIFICATION_CAMPAIGN_EXPIRED"
    )

    invalid_token = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/confirm",
        json={"confirmation_token": expired_preview["confirmation_token"] + "x"},
    )
    assert invalid_token.status_code == 409
    assert (
        invalid_token.json()["detail"]["code"]
        == "ERR_NOTIFICATION_CAMPAIGN_CONFIRMATION_INVALID"
    )

    legacy_broadcast = await admin_client.post("/api/v1/admin/notifications/broadcast")
    legacy_selected = await admin_client.post("/api/v1/admin/notifications/send")
    assert legacy_broadcast.status_code == 409
    assert legacy_selected.status_code == 409
    assert (
        legacy_broadcast.json()["detail"]["code"]
        == "ERR_NOTIFICATION_PREVIEW_REQUIRED"
    )
    assert await db_session.scalar(select(func.count(Notification.id))) == 0

    history_response = await admin_client.get(
        "/api/v1/admin/communications/broadcasts"
    )
    statuses = {
        item["campaign_id"]: item["status"]
        for item in history_response.json()["items"]
    }
    assert statuses[cancelled_preview["campaign_id"]] == "cancelled"
    assert statuses[expired_preview["campaign_id"]] == "expired"


@pytest.mark.asyncio
async def test_campaign_rejects_a_modified_recipient_snapshot(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    original = await _user(db_session, suffix="snapshot-original")
    replacement = await _user(db_session, suffix="snapshot-replacement")
    await db_session.commit()
    preview_response = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/preview",
        json={
            "audience": "selected",
            "user_ids": [original.id],
            "title": "Snapshot integrity",
            "message": "Recipient rows must match the signed digest.",
        },
    )
    assert preview_response.status_code == 201
    preview = preview_response.json()
    campaign = await db_session.scalar(
        select(NotificationCampaign).where(
            NotificationCampaign.public_id == preview["campaign_id"]
        )
    )
    assert campaign is not None
    recipient = await db_session.scalar(
        select(NotificationCampaignRecipient).where(
            NotificationCampaignRecipient.campaign_id == campaign.id
        )
    )
    assert recipient is not None
    recipient.user_id = replacement.id
    await db_session.commit()

    confirm_response = await admin_client.post(
        "/api/v1/admin/communications/broadcasts/confirm",
        json={"confirmation_token": preview["confirmation_token"]},
    )

    assert confirm_response.status_code == 409
    assert (
        confirm_response.json()["detail"]["code"]
        == "ERR_NOTIFICATION_CAMPAIGN_CONFIRMATION_INVALID"
    )
    assert await db_session.scalar(select(func.count(Notification.id))) == 0
