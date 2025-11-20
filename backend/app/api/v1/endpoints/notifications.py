"""Notification endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationListResponse, NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


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
    count_query = select(func.count()).select_from(Notification).where(
        Notification.user_id == current_user.id
    )
    if unread_only:
        count_query = count_query.where(Notification.read == False)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Count unread
    unread_count_query = select(func.count()).select_from(Notification).where(
        Notification.user_id == current_user.id,
        Notification.read == False,
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


@router.get("/unread-count")
async def get_unread_count(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Получить количество непрочитанных уведомлений."""
    result = await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == current_user.id,
            Notification.read == False,
        )
    )
    count = result.scalar() or 0
    
    return {"unread_count": count}


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationResponse:
    """Отметить уведомление как прочитанное."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
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
    
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.read == False,
        )
    )
    notifications = result.scalars().all()
    
    count = 0
    for notification in notifications:
        notification.read = True
        notification.read_at = datetime.now(timezone.utc)
        count += 1
    
    await db.commit()
    
    return {"marked_count": count}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Удалить уведомление."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    await db.delete(notification)
    await db.commit()
    
    return {"message": "Notification deleted successfully"}


@router.delete("/all")
async def delete_all_notifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    read_only: bool = Query(False, description="Удалить только прочитанные уведомления"),
) -> dict[str, int]:
    """Удалить все уведомления пользователя (или только прочитанные)."""
    query = select(Notification).where(Notification.user_id == current_user.id)
    
    if read_only:
        query = query.where(Notification.read == True)
    
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    count = 0
    for notification in notifications:
        await db.delete(notification)
        count += 1
    
    await db.commit()
    
    return {
        "deleted_count": count,
        "message": f"Удалено {count} уведомлений" if count > 0 else "Нет уведомлений для удаления",
    }
