"""Feedback endpoints."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_active_user,
    get_current_active_user_optional,
    get_current_admin_user,
)
from app.db.session import get_db
from app.models.feedback import Feedback, FeedbackStatus, FeedbackType
from app.models.user import User, UserRole
from app.core.errors import ERR_AUTH_REQUIRED, ERR_FEEDBACK_NOT_FOUND, ERR_INVALID_FEEDBACK_TYPE, ERR_INVALID_FEEDBACK_STATUS, raise_error
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackUpdate,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    feedback_data: FeedbackCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackResponse:
    """
    Создать обратную связь.
    
    Требуется авторизация. Email не нужен, так как берется из профиля пользователя.
    """
    # Получаем текущего пользователя (для обратной связи требуется авторизация)
    current_user = await get_current_active_user_optional(request, db)
    
    if not current_user:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_AUTH_REQUIRED)
    
    # Валидация типа
    try:
        feedback_type = FeedbackType(feedback_data.type)
    except ValueError:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FEEDBACK_TYPE)
    
    feedback = Feedback(
        user_id=current_user.id,
        type=feedback_type,
        subject=feedback_data.subject,
        message=feedback_data.message,
        email=None,  # Email не нужен для авторизованных пользователей
        status=FeedbackStatus.OPEN,
        # Source context
        source=feedback_data.source,
        source_url=feedback_data.source_url,
        source_id=feedback_data.source_id,
    )
    
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    
    return FeedbackResponse.model_validate(feedback)


@router.get("/", response_model=FeedbackListResponse)
async def list_feedback(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    status_filter: FeedbackStatus | None = Query(None, alias="status", description="Фильтр по статусу"),
    type_filter: FeedbackType | None = Query(None, alias="type", description="Фильтр по типу"),
    source_filter: str | None = Query(None, alias="source", description="Фильтр по источнику (wiki_article, preset, general)"),
) -> FeedbackListResponse:
    """Получить список обратной связи (только для админов)."""
    query = select(Feedback)

    if status_filter:
        query = query.where(Feedback.status == status_filter)

    if type_filter:
        query = query.where(Feedback.type == type_filter)

    if source_filter:
        query = query.where(Feedback.source == source_filter)

    # Count total
    count_query = select(func.count()).select_from(Feedback)
    if status_filter:
        count_query = count_query.where(Feedback.status == status_filter)
    if type_filter:
        count_query = count_query.where(Feedback.type == type_filter)
    if source_filter:
        count_query = count_query.where(Feedback.source == source_filter)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Paginate
    pages = (total + size - 1) // size if total > 0 else 0
    offset = (page - 1) * size
    query = query.order_by(Feedback.created_at.desc()).offset(offset).limit(size)
    
    result = await db.execute(query)
    feedback_list = result.scalars().all()
    
    return FeedbackListResponse(
        items=[FeedbackResponse.model_validate(feedback) for feedback in feedback_list],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback(
    feedback_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackResponse:
    """Получить обратную связь по ID (только для админов)."""
    feedback = await db.get(Feedback, feedback_id)
    
    if not feedback:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)
    
    return FeedbackResponse.model_validate(feedback)


@router.patch("/{feedback_id}", response_model=FeedbackResponse)
async def update_feedback(
    feedback_id: int,
    update_data: FeedbackUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackResponse:
    """Обновить обратную связь (ответить, изменить статус) - только для админов."""
    feedback = await db.get(Feedback, feedback_id)
    
    if not feedback:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)
    
    if update_data.status:
        try:
            feedback.status = FeedbackStatus(update_data.status)
        except ValueError:
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FEEDBACK_STATUS)
    
    if update_data.admin_response is not None:
        feedback.admin_response = update_data.admin_response
        feedback.responded_by = admin.id
        feedback.admin_response_at = datetime.now(timezone.utc)
        
        # Отправляем уведомление пользователю о том, что админ ответил на его обратную связь
        if feedback.user_id:
            from app.services.notification_service import create_notification
            from app.models.notification import NotificationType
            
            await create_notification(
                user_id=feedback.user_id,
                notification_type=NotificationType.ADMIN_MESSAGE,
                title="feedback_response",
                message=update_data.admin_response,
                db=db,
                link=f"/feedback/{feedback.id}",
                extra_data={"feedback_id": feedback.id, "feedback_type": feedback.type.value},
            )
    
    await db.commit()
    await db.refresh(feedback)
    
    return FeedbackResponse.model_validate(feedback)


@router.get("/my/list", response_model=FeedbackListResponse)
async def list_my_feedback(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
) -> FeedbackListResponse:
    """Получить список своей обратной связи."""
    query = select(Feedback).where(Feedback.user_id == current_user.id)
    
    # Count total
    count_query = select(func.count()).select_from(Feedback).where(
        Feedback.user_id == current_user.id
    )
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Paginate
    pages = (total + size - 1) // size if total > 0 else 0
    offset = (page - 1) * size
    query = query.order_by(Feedback.created_at.desc()).offset(offset).limit(size)
    
    result = await db.execute(query)
    feedback_list = result.scalars().all()
    
    return FeedbackListResponse(
        items=[FeedbackResponse.model_validate(feedback) for feedback in feedback_list],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )

