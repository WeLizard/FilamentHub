from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.notification import DeletedPresetDecisionItem, Notification, NotificationType
from app.models.preset import Preset
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.orca_sync import DeletedPresetAction, DeletedPresetsRequest


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


def _item(
    notification_id: int,
    preset_id: int,
    *,
    created: bool = False,
    saved: bool = False,
    reported_at: datetime | None = None,
):
    return DeletedPresetDecisionItem(
        notification_id=notification_id,
        preset_id=preset_id,
        preset_name=f"Preset {preset_id}",
        bundle_preset_name=None,
        is_created=created,
        is_saved=saved,
        **({"reported_at": reported_at} if reported_at is not None else {}),
    )


def test_action_ids_are_bounded_and_normalized():
    assert DeletedPresetAction(action="skip", preset_ids=[3, 3, 4]).preset_ids == [3, 4]
    with pytest.raises(ValidationError):
        DeletedPresetAction(action="skip", preset_ids=list(range(501)))
    for invalid_id in (0, -1, 2_147_483_648):
        with pytest.raises(ValidationError):
            DeletedPresetAction(action="skip", preset_ids=[invalid_id])
        with pytest.raises(ValidationError):
            DeletedPresetsRequest(
                deleted_presets=[{"preset_id": invalid_id, "preset_name": "Invalid"}]
            )
    request = DeletedPresetsRequest(
        deleted_presets=[
            {"preset_id": 9, "preset_name": "Old snapshot"},
            {"preset_id": 9, "preset_name": "Latest snapshot"},
        ]
    )
    assert [(item.preset_id, item.preset_name) for item in request.deleted_presets] == [
        (9, "Latest snapshot")
    ]


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


def test_migration_backfill_gives_legacy_items_a_full_new_grace_period():
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "deleted_preset_decision_queue.py"
    ).read_text(encoding="utf-8")
    assert "n.read IS FALSE" not in migration
    assert "CURRENT_TIMESTAMP" in migration
    assert "n.created_at" not in migration
    assert "<= 2147483647" in migration
    assert "ON CONFLICT (notification_id, preset_id) DO NOTHING" in migration
    assert "jsonb_array_elements(" in migration
    assert "jsonb_typeof(" in migration
    assert "ELSE '[]'::jsonb" in migration
    assert "json_array_elements(" not in migration
    assert "json_typeof(" not in migration
    assert "coalesce(n.extra_data, '{}'::jsonb)" in migration
    assert "THEN false" in migration
    assert "THEN NULL" in migration


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


@pytest.mark.asyncio
async def test_repeat_report_preserves_first_reported_at_and_fresh_append_gets_new_time(
    auth_client, auth_user, db_session
):
    def payload(ids):
        return {"deleted_presets": [
            {"preset_id": preset_id, "preset_name": f"Preset {preset_id}"}
            for preset_id in ids
        ]}
    response = await auth_client.post("/api/v1/orcaslicer/deleted-presets", json=payload([31]))
    notification_id = response.json()["notification_id"]
    row = await db_session.scalar(select(DeletedPresetDecisionItem))
    original = datetime.now(timezone.utc) - timedelta(days=8)
    row.reported_at = original
    await db_session.commit()

    await auth_client.post("/api/v1/orcaslicer/deleted-presets", json=payload([31, 32]))
    rows = list((await db_session.scalars(
        select(DeletedPresetDecisionItem)
        .where(DeletedPresetDecisionItem.notification_id == notification_id)
        .order_by(DeletedPresetDecisionItem.preset_id)
    )).all())
    assert rows[0].reported_at == original
    assert rows[1].reported_at.replace(tzinfo=timezone.utc) > original


@pytest.mark.asyncio
async def test_generic_notification_mutations_protect_pending_decisions(
    auth_client, auth_user, db_session
):
    pending = await _notification(db_session, auth_user.id)
    db_session.add(_item(pending.id, 41))
    ordinary = Notification(
        user_id=auth_user.id,
        type=NotificationType.ADMIN_MESSAGE,
        title="ordinary",
        message="ordinary",
        read=False,
    )
    db_session.add(ordinary)
    await db_session.commit()
    await db_session.refresh(ordinary)

    mark_one = await auth_client.patch(f"/api/v1/notifications/{pending.id}/read")
    assert mark_one.status_code == 409
    assert mark_one.json()["detail"]["code"] == "ERR_NOTIFICATION_HAS_PENDING_DECISIONS"
    delete_one = await auth_client.delete(f"/api/v1/notifications/{pending.id}")
    assert delete_one.status_code == 409

    mark_all = await auth_client.post("/api/v1/notifications/mark-all-read")
    assert mark_all.json() == {"marked_count": 1, "skipped_pending_count": 1}
    await db_session.refresh(pending)
    await db_session.refresh(ordinary)
    assert pending.read is False
    assert ordinary.read is True

    delete_all = await auth_client.delete("/api/v1/notifications/all")
    assert delete_all.json()["skipped_pending_count"] == 1
    assert await db_session.get(Notification, pending.id) is not None
    assert await db_session.get(Notification, ordinary.id) is None


@pytest.mark.asyncio
async def test_auto_process_resolves_only_items_older_than_seven_days(
    auth_client, auth_user, db_session
):
    notification = await _notification(db_session, auth_user.id)
    db_session.add_all([
        _item(
            notification.id,
            51,
            saved=True,
            reported_at=datetime.now(timezone.utc) - timedelta(days=8),
        ),
        _item(notification.id, 52, saved=True, reported_at=datetime.now(timezone.utc)),
    ])
    await db_session.commit()

    response = await auth_client.post("/api/v1/orcaslicer/deleted-presets/auto-process")
    assert response.status_code == 200
    assert response.json()["notifications_processed"] == 1
    rows = list((await db_session.scalars(
        select(DeletedPresetDecisionItem)
        .where(DeletedPresetDecisionItem.notification_id == notification.id)
        .order_by(DeletedPresetDecisionItem.preset_id)
    )).all())
    assert rows[0].resolved_at is not None
    assert rows[1].resolved_at is None
    await db_session.refresh(notification)
    assert notification.read is False
    assert notification.extra_data["remaining_count"] == 1


@pytest.mark.asyncio
async def test_direct_always_restore_and_always_delete_rules(
    auth_client, auth_user, db_session
):
    saved = Preset(name="Saved preset", extruder_temp=210, bed_temp=60)
    db_session.add(saved)
    await db_session.flush()
    db_session.add(UserSavedPreset(user_id=auth_user.id, preset_id=saved.id))
    auth_user.deleted_preset_rule = "always_restore"
    await db_session.commit()

    payload = {"deleted_presets": [{"preset_id": saved.id, "preset_name": saved.name}]}
    restored = await auth_client.post("/api/v1/orcaslicer/deleted-presets", json=payload)
    assert restored.status_code == 200
    assert restored.json()["rule"] == "always_restore"
    assert await db_session.scalar(select(UserSavedPreset.id)) is not None

    auth_user.deleted_preset_rule = "always_delete"
    await db_session.commit()
    deleted = await auth_client.post("/api/v1/orcaslicer/deleted-presets", json=payload)
    assert deleted.status_code == 200
    assert deleted.json()["rule"] == "always_delete"
    assert await db_session.scalar(select(UserSavedPreset.id)) is None
    assert await db_session.scalar(select(Notification.id)) is None


def test_decision_rows_use_database_cascade():
    foreign_key = next(iter(DeletedPresetDecisionItem.__table__.c.notification_id.foreign_keys))
    assert foreign_key.ondelete == "CASCADE"
