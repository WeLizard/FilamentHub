"""Notification endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_NOTIFICATION_HAS_PENDING_DECISIONS,
    ERR_NOTIFICATION_NOT_FOUND,
    raise_error,
)
from app.db.session import get_db
from app.models.notification import DeletedPresetDecisionItem, Notification, NotificationType
from app.models.user import User
from app.schemas.notification import (
    DeletedPresetDecisionFeedResponse,
    DeletedPresetDecisionItemResponse,
    NotificationFeedResponse,
    NotificationListResponse,
    NotificationResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


async def _has_pending_deleted_preset_decisions(
    db: AsyncSession, notification: Notification
) -> bool:
    if notification.type != NotificationType.PRESET_LOCALLY_DELETED:
        return False
    return bool(
        await db.scalar(
            select(DeletedPresetDecisionItem.id)
            .where(
                DeletedPresetDecisionItem.notification_id == notification.id,
                DeletedPresetDecisionItem.resolved_at.is_(None),
            )
            .limit(1)
        )
    )


async def _pending_decision_notification_ids(
    db: AsyncSession, notification_ids: list[int]
) -> set[int]:
    if not notification_ids:
        return set()
    return set(
        (
            await db.scalars(
                select(DeletedPresetDecisionItem.notification_id)
                .where(
                    DeletedPresetDecisionItem.notification_id.in_(notification_ids),
                    DeletedPresetDecisionItem.resolved_at.is_(None),
                )
                .distinct()
            )
        ).all()
    )


async def _lock_notification_owner(db: AsyncSession, user_id: int) -> None:
    await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _notification_feed_item(notification: Notification) -> NotificationResponse:
    """Keep feed rows compact while detail endpoints retain compatibility payloads."""
    response = NotificationResponse.model_validate(notification)
    if notification.type != NotificationType.PRESET_LOCALLY_DELETED:
        return response

    extra_data = dict(response.extra_data or {})
    extra_data.pop("deleted_presets", None)
    return response.model_copy(update={"extra_data": extra_data})


@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False, description="Показать только непрочитанные"),
) -> NotificationListResponse:
    """Получить список уведомлений пользователя."""
    # Build query
    query = select(Notification).where(Notification.user_id == current_user.id)

    if unread_only:
        query = query.where(Notification.read == False)

    # Count total
    count_query = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == current_user.id)
    )
    if unread_only:
        count_query = count_query.where(Notification.read == False)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Count unread
    unread_count_query = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read == False,
        )
    )
    unread_count_result = await db.execute(unread_count_query)
    unread_count = unread_count_result.scalar() or 0

    # Paginate
    pages = (total + size - 1) // size if total > 0 else 0
    offset = (page - 1) * size
    query = query.order_by(Notification.created_at.desc()).offset(offset).limit(size)

    # Execute
    result = await db.execute(query)
    notifications = result.scalars().all()

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        size=size,
        pages=pages,
        unread_count=unread_count,
    )


@router.get("/feed", response_model=NotificationFeedResponse)
async def list_notification_feed(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=100),
    cursor: int | None = Query(None, ge=1),
    unread_only: bool = Query(False, description="Показать только непрочитанные"),
) -> NotificationFeedResponse:
    """Return a bounded, stable page of the current user's notifications."""
    query = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        query = query.where(Notification.read == False)
    if cursor is not None:
        query = query.where(Notification.id < cursor)

    result = await db.execute(query.order_by(Notification.id.desc()).limit(limit + 1))
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    notifications = rows[:limit]

    unread_count = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read == False,
        )
    )

    return NotificationFeedResponse(
        items=[_notification_feed_item(notification) for notification in notifications],
        next_cursor=notifications[-1].id if has_more and notifications else None,
        unread_count=unread_count or 0,
    )


@router.get("/unread-count")
async def get_unread_count(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Получить количество непрочитанных уведомлений."""
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read == False,
        )
    )
    count = result.scalar() or 0

    return {"unread_count": count}


@router.get(
    "/{notification_id}/deleted-presets",
    response_model=DeletedPresetDecisionFeedResponse,
)
async def list_deleted_preset_decisions(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=100),
    cursor: int | None = Query(None, ge=1, le=2_147_483_647),
) -> DeletedPresetDecisionFeedResponse:
    """Return one stable page of pending Orca-local deletion decisions."""
    notification = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
            Notification.type == NotificationType.PRESET_LOCALLY_DELETED,
        )
    )
    if notification is None:
        raise_error(404, ERR_NOTIFICATION_NOT_FOUND)

    base = (
        DeletedPresetDecisionItem.notification_id == notification_id,
        DeletedPresetDecisionItem.resolved_at.is_(None),
    )
    row_count = await db.scalar(
        select(func.count()).select_from(DeletedPresetDecisionItem).where(*base)
    )
    page_query = select(DeletedPresetDecisionItem).where(*base)
    if cursor is not None:
        page_query = page_query.where(DeletedPresetDecisionItem.id > cursor)
    rows = list(
        (await db.scalars(page_query.order_by(DeletedPresetDecisionItem.id).limit(limit + 1))).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    created_count, saved_count = (
        await db.execute(
            select(
                func.count().filter(DeletedPresetDecisionItem.is_created.is_(True)),
                func.count().filter(DeletedPresetDecisionItem.is_saved.is_(True)),
            ).where(*base)
        )
    ).one()
    return DeletedPresetDecisionFeedResponse(
        items=[DeletedPresetDecisionItemResponse.model_validate(row) for row in page],
        next_cursor=page[-1].id if has_more and page else None,
        remaining_count=int(row_count or 0),
        created_count=int(created_count or 0),
        saved_count=int(saved_count or 0),
    )


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationResponse:
    """Return one notification owned by the current user."""
    notification = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    if notification is None:
        raise_error(404, ERR_NOTIFICATION_NOT_FOUND)
    return NotificationResponse.model_validate(notification)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationResponse:
    """Отметить уведомление как прочитанное."""
    await _lock_notification_owner(db, current_user.id)
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise_error(404, ERR_NOTIFICATION_NOT_FOUND)
    if await _has_pending_deleted_preset_decisions(db, notification):
        raise_error(409, ERR_NOTIFICATION_HAS_PENDING_DECISIONS)

    if not notification.read:
        from datetime import datetime, timezone

        notification.read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notification)

    return NotificationResponse.model_validate(notification)


@router.post("/mark-all-read")
async def mark_all_as_read(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Отметить все уведомления пользователя как прочитанные."""
    from datetime import datetime, timezone

    await _lock_notification_owner(db, current_user.id)
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.read == False,
        )
    )
    notifications = result.scalars().all()
    pending_ids = await _pending_decision_notification_ids(
        db, [notification.id for notification in notifications]
    )

    count = 0
    for notification in notifications:
        if notification.id in pending_ids:
            continue
        notification.read = True
        notification.read_at = datetime.now(timezone.utc)
        count += 1

    await db.commit()

    return {"marked_count": count, "skipped_pending_count": len(pending_ids)}


@router.delete("/all")
async def delete_all_notifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    read_only: bool = Query(False, description="Удалить только прочитанные уведомления"),
) -> dict[str, int | str]:
    """Удалить все уведомления пользователя (или только прочитанные)."""
    await _lock_notification_owner(db, current_user.id)
    query = select(Notification).where(Notification.user_id == current_user.id)

    if read_only:
        query = query.where(Notification.read == True)

    result = await db.execute(query)
    notifications = result.scalars().all()
    pending_ids = await _pending_decision_notification_ids(
        db, [notification.id for notification in notifications]
    )

    count = 0
    for notification in notifications:
        if notification.id in pending_ids:
            continue
        await db.delete(notification)
        count += 1

    await db.commit()

    return {
        "deleted_count": count,
        "skipped_pending_count": len(pending_ids),
        "message": "notifications_deleted" if count > 0 else "no_notifications_to_delete",
    }


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Удалить уведомление."""
    await _lock_notification_owner(db, current_user.id)
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise_error(404, ERR_NOTIFICATION_NOT_FOUND)
    if await _has_pending_deleted_preset_decisions(db, notification):
        raise_error(409, ERR_NOTIFICATION_HAS_PENDING_DECISIONS)

    await db.delete(notification)
    await db.commit()

    return {"message": "notification_deleted"}
