from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.notification import DeletedPresetDecisionItem, Notification, NotificationType
from app.schemas.orca_sync import DeletedPresetAction


async def _notification(db_session, user_id: int, *, legacy: list[dict] | None = None) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=NotificationType.PRESET_LOCALLY_DELETED,
        title="deleted_presets_detected",
        message="deleted_presets_detected_message",
        extra_data={"deleted_presets": legacy or []},
        read=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


def _item(notification_id: int, preset_id: int, *, created: bool = False, saved: bool = False):
    return DeletedPresetDecisionItem(
        notification_id=notification_id,
        preset_id=preset_id,
        preset_name=f"Preset {preset_id}",
        bundle_preset_name=None,
        is_created=created,
        is_saved=saved,
    )


def test_action_ids_are_bounded_and_normalized():
    assert DeletedPresetAction(action="skip", preset_ids=[3, 3, 4]).preset_ids == [3, 4]
    with pytest.raises(ValidationError):
        DeletedPresetAction(action="skip", preset_ids=list(range(501)))


@pytest.mark.asyncio
async def test_deleted_preset_feed_is_owned_bounded_and_stable_across_insert(
    auth_client, auth_user, db_session
):
    notification = await _notification(db_session, auth_user.id)
    db_session.add_all([_item(notification.id, 1), _item(notification.id, 2), _item(notification.id, 3)])
    await db_session.commit()

    first = await auth_client.get(
        f"/api/v1/notifications/{notification.id}/deleted-presets", params={"limit": 2}
    )
    assert first.status_code == 200
    assert [item["preset_id"] for item in first.json()["items"]] == [1, 2]
    cursor = first.json()["next_cursor"]

    db_session.add(_item(notification.id, 4))
    await db_session.commit()
    second = await auth_client.get(
        f"/api/v1/notifications/{notification.id}/deleted-presets",
        params={"limit": 2, "cursor": cursor},
    )
    assert [item["preset_id"] for item in second.json()["items"]] == [3, 4]
    assert second.json()["remaining_count"] == 4
    assert (await auth_client.get(
        f"/api/v1/notifications/{notification.id}/deleted-presets", params={"limit": 0}
    )).status_code == 422
    assert (await auth_client.get(
        f"/api/v1/notifications/{notification.id}/deleted-presets", params={"limit": 101}
    )).status_code == 422
    assert (await auth_client.get(
        f"/api/v1/notifications/{notification.id}/deleted-presets",
        params={"cursor": 2_147_483_648},
    )).status_code == 422


@pytest.mark.asyncio
async def test_deleted_preset_feed_rejects_another_users_notification(
    auth_client, db_session
):
    from app.models.user import User

    other = User(email="queue-other@example.com", username="queue-other", password_hash="x", active=True)
    db_session.add(other)
    await db_session.commit()
    notification = await _notification(db_session, other.id)
    response = await auth_client.get(f"/api/v1/notifications/{notification.id}/deleted-presets")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_json_queue_remains_readable_before_backfill(
    auth_client, auth_user, db_session
):
    notification = await _notification(
        db_session,
        auth_user.id,
        legacy=[
            {"preset_id": 8, "preset_name": "Legacy A", "is_created": True, "is_saved": False},
            {"preset_id": 9, "preset_name": "Legacy B", "is_created": False, "is_saved": True},
        ],
    )
    response = await auth_client.get(
        f"/api/v1/notifications/{notification.id}/deleted-presets", params={"limit": 1}
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["preset_id"] == 8
    assert response.json()["next_cursor"] == 1
    assert response.json()["created_count"] == 1
    assert response.json()["saved_count"] == 1

    action = await auth_client.post(
        f"/api/v1/orcaslicer/deleted-presets/{notification.id}/action",
        json={"action": "skip", "preset_ids": [8], "apply_to_all": False},
    )
    assert action.status_code == 200
    await db_session.refresh(notification)
    assert [value["preset_id"] for value in notification.extra_data["deleted_presets"]] == [9]
    assert notification.read is False


@pytest.mark.asyncio
async def test_reports_append_without_duplicates_or_lost_entries(
    auth_client, auth_user, db_session
):
    def payload(ids):
        return {"deleted_presets": [
            {"preset_id": preset_id, "preset_name": f"Preset {preset_id}"} for preset_id in ids
        ]}
    assert (await auth_client.post("/api/v1/orcaslicer/deleted-presets", json=payload([11, 12]))).status_code == 200
    assert (await auth_client.post("/api/v1/orcaslicer/deleted-presets", json=payload([12, 13]))).status_code == 200

    notification = await db_session.scalar(
        select(Notification).where(
            Notification.user_id == auth_user.id,
            Notification.type == NotificationType.PRESET_LOCALLY_DELETED,
        )
    )
    rows = list((await db_session.scalars(
        select(DeletedPresetDecisionItem)
        .where(DeletedPresetDecisionItem.notification_id == notification.id)
        .order_by(DeletedPresetDecisionItem.preset_id)
    )).all())
    assert [row.preset_id for row in rows] == [11, 12, 13]


@pytest.mark.asyncio
async def test_explicit_action_is_scoped_and_apply_all_includes_unloaded_pages(
    auth_client, auth_user, db_session
):
    notification = await _notification(db_session, auth_user.id)
    db_session.add_all([_item(notification.id, preset_id) for preset_id in range(1, 106)])
    await db_session.commit()

    explicit = await auth_client.post(
        f"/api/v1/orcaslicer/deleted-presets/{notification.id}/action",
        json={"action": "skip", "preset_ids": [1], "apply_to_all": False},
    )
    assert explicit.status_code == 200
    assert explicit.json()["total_count"] == 1
    assert await db_session.scalar(
        select(func.count()).select_from(DeletedPresetDecisionItem).where(
            DeletedPresetDecisionItem.notification_id == notification.id,
            DeletedPresetDecisionItem.resolved_at.is_(None),
        )
    ) == 104

    all_response = await auth_client.post(
        f"/api/v1/orcaslicer/deleted-presets/{notification.id}/action",
        json={"action": "skip", "apply_to_all": True},
    )
    assert all_response.status_code == 200
    assert all_response.json()["total_count"] == 104
    await db_session.refresh(notification)
    assert notification.read is True


@pytest.mark.asyncio
async def test_report_retry_cannot_resurrect_a_resolved_item_in_open_queue(
    auth_client, auth_user, db_session
):
    def payload(ids):
        return {"deleted_presets": [
            {"preset_id": preset_id, "preset_name": f"Preset {preset_id}"} for preset_id in ids
        ]}
    report = await auth_client.post("/api/v1/orcaslicer/deleted-presets", json=payload([21, 22]))
    notification_id = report.json()["notification_id"]
    await auth_client.post(
        f"/api/v1/orcaslicer/deleted-presets/{notification_id}/action",
        json={"action": "skip", "preset_ids": [21], "apply_to_all": False},
    )

    # A delayed/retried report can refresh snapshots but cannot reopen a decision
    # already resolved while this notification remains active.
    await auth_client.post("/api/v1/orcaslicer/deleted-presets", json=payload([21, 23]))
    pending = list((await db_session.scalars(
        select(DeletedPresetDecisionItem.preset_id).where(
            DeletedPresetDecisionItem.notification_id == notification_id,
            DeletedPresetDecisionItem.resolved_at.is_(None),
        ).order_by(DeletedPresetDecisionItem.preset_id)
    )).all())
    assert pending == [22, 23]


def test_decision_rows_use_database_cascade():
    foreign_key = next(iter(DeletedPresetDecisionItem.__table__.c.notification_id.foreign_keys))
    assert foreign_key.ondelete == "CASCADE"
