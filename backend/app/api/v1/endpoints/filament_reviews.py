"""FilamentReview endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user
from app.core.errors import (
    ERR_ADD_PRESET_FIRST,
    ERR_FILAMENT_NOT_FOUND,
    ERR_NO_PERMISSION_DELETE_REVIEW,
    ERR_NO_PERMISSION_EDIT_REVIEW,
    ERR_PRESET_NOT_MATCH,
    ERR_REVIEW_ALREADY_EXISTS,
    ERR_REVIEW_NOT_FOUND,
    ERR_REVIEW_SAVED_ONLY,
    raise_error,
)
from app.db.session import get_db
from app.models.filament_review import FilamentReview
from app.models.preset import Preset
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.filament_review import (
    FilamentRatingStats,
    FilamentReviewCreate,
    FilamentReviewListResponse,
    FilamentReviewResponse,
    FilamentReviewUpdate,
)
from app.services.preset_ratings import update_preset_ratings

router = APIRouter(prefix="/filament-reviews", tags=["filament-reviews"])


@router.get("/available-presets/{filament_id}")
async def get_available_presets_for_review(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    Получить список пресетов, на которые можно оставить отзыв для указанного филамента.
    
    Возвращает:
    - Официальный пресет (если есть)
    - Сохраненные пользователем пресеты этого филамента
    """
    from app.models.filament import Filament
    from app.schemas.preset import PresetResponse

    # Проверяем существование материала
    filament_result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = filament_result.scalar_one_or_none()
    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    available_presets = []

    # 1. Официальный пресет
    official_preset_result = await db.execute(
        select(Preset).where(
            Preset.filament_id == filament_id,
            Preset.is_official == True,
            Preset.active == True,
        ).order_by(Preset.created_at.desc()).limit(1)
    )
    official_preset = official_preset_result.scalar_one_or_none()
    if official_preset:
        preset_dict = PresetResponse.model_validate(official_preset).model_dump()
        preset_dict["is_official"] = True
        preset_dict["is_saved"] = False  # Проверим ниже
        available_presets.append(preset_dict)

    # 2. Сохраненные пользователем пресеты этого филамента
    saved_presets_result = await db.execute(
        select(UserSavedPreset, Preset)
        .join(Preset, UserSavedPreset.preset_id == Preset.id)
        .where(
            UserSavedPreset.user_id == current_user.id,
            Preset.filament_id == filament_id,
            Preset.active == True,
        )
    )
    saved_presets_data = saved_presets_result.all()
    
    saved_preset_ids = set()
    for saved_preset_row, preset in saved_presets_data:
        # Пропускаем официальный пресет, если он уже добавлен
        if preset.is_official and official_preset and preset.id == official_preset.id:
            # Обновляем is_saved для официального пресета
            for p in available_presets:
                if p["id"] == preset.id:
                    p["is_saved"] = True
            continue
        
        preset_dict = PresetResponse.model_validate(preset).model_dump()
        preset_dict["is_official"] = preset.is_official
        preset_dict["is_saved"] = True
        available_presets.append(preset_dict)
        saved_preset_ids.add(preset.id)

    # Если есть официальный пресет и он сохранен, обновляем is_saved
    if official_preset and official_preset.id in saved_preset_ids:
        for p in available_presets:
            if p["id"] == official_preset.id:
                p["is_saved"] = True

    return {
        "items": available_presets,
        "total": len(available_presets),
    }


@router.get("/my", response_model=FilamentReviewListResponse)
async def get_my_reviews(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(True),
) -> FilamentReviewListResponse:
    """Получить список отзывов текущего пользователя."""
    # Строим запрос
    query = (
        select(FilamentReview)
        .options(selectinload(FilamentReview.user), selectinload(FilamentReview.filament))
        .where(FilamentReview.user_id == current_user.id)
    )

    if active_only:
        query = query.where(FilamentReview.active == True)

    # Сортировка по дате создания (новые сначала)
    query = query.order_by(FilamentReview.created_at.desc())

    # Пагинация
    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one() or 0

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    # Выполняем запрос
    result = await db.execute(query)
    reviews = result.scalars().all()

    # Преобразуем в ответы
    items = []
    for review in reviews:
        # Загружаем пресет если есть
        preset_name = None
        if review.preset_id:
            preset_result = await db.execute(select(Preset).where(Preset.id == review.preset_id))
            preset = preset_result.scalar_one_or_none()
            preset_name = preset.name if preset else None
        
        items.append(
            FilamentReviewResponse(
                id=review.id,
                filament_id=review.filament_id,
                user_id=review.user_id,
                preset_id=review.preset_id,
                preset_name=preset_name,
                username=review.user.username if review.user else None,
                user_badges=review.user.badges if review.user else None,
                success=review.success,
                rating=review.rating,
                comment=review.comment,
                printer_model=review.printer_model,
                active=review.active,
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
        )

    pages = (total + size - 1) // size if total > 0 else 0

    return FilamentReviewListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/filament/{filament_id}", response_model=FilamentReviewListResponse)
async def list_filament_reviews(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(True),
    order_by: str = Query("created_at", regex="^(created_at|rating|updated_at)$"),
    order_desc: bool = Query(True),
) -> FilamentReviewListResponse:
    """Получить список отзывов для материала."""
    from app.models.filament import Filament

    # Проверяем существование материала
    filament_result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = filament_result.scalar_one_or_none()
    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Строим запрос
    query = (
        select(FilamentReview)
        .options(selectinload(FilamentReview.user))
        .where(FilamentReview.filament_id == filament_id)
    )

    if active_only:
        query = query.where(FilamentReview.active == True)

    # Сортировка
    order_column = getattr(FilamentReview, order_by)
    if order_desc:
        query = query.order_by(order_column.desc())
    else:
        query = query.order_by(order_column.asc())

    # Пагинация
    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one() or 0

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    # Выполняем запрос
    result = await db.execute(query)
    reviews = result.scalars().all()

    # Преобразуем в ответы
    items = []
    for review in reviews:
        # Загружаем пресет если есть
        preset_name = None
        if review.preset_id:
            preset_result = await db.execute(select(Preset).where(Preset.id == review.preset_id))
            preset = preset_result.scalar_one_or_none()
            preset_name = preset.name if preset else None
        
        items.append(
            FilamentReviewResponse(
                id=review.id,
                filament_id=review.filament_id,
                user_id=review.user_id,
                preset_id=review.preset_id,
                preset_name=preset_name,
                username=review.user.username if review.user else None,
                user_badges=review.user.badges if review.user else None,
                success=review.success,
                rating=review.rating,
                comment=review.comment,
                printer_model=review.printer_model,
                active=review.active,
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
        )

    pages = (total + size - 1) // size if total > 0 else 0

    return FilamentReviewListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/filament/{filament_id}/stats", response_model=FilamentRatingStats)
async def get_filament_rating_stats(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = Query(True),
) -> FilamentRatingStats:
    """Получить статистику рейтингов для материала."""
    from app.models.filament import Filament
    from app.services.preset_ratings import calculate_filament_weighted_rating

    # Проверяем существование материала
    filament_result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = filament_result.scalar_one_or_none()
    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Строим запрос для активных отзывов
    query = select(FilamentReview).where(FilamentReview.filament_id == filament_id)
    if active_only:
        query = query.where(FilamentReview.active == True)

    # Получаем все отзывы для расчёта статистики
    result = await db.execute(query)
    reviews = result.scalars().all()

    if not reviews:
        return FilamentRatingStats(
            avg_rating=None,
            total_reviews=0,
            success_rate=None,
            rating_distribution={},
        )

    # Вычисляем взвешенный рейтинг филамента на основе пресетов
    weighted_rating, weighted_success_rate = await calculate_filament_weighted_rating(filament_id, db)
    
    # Если есть взвешенный рейтинг, используем его, иначе простое среднее всех отзывов
    if weighted_rating is not None:
        avg_rating = weighted_rating
        success_rate = weighted_success_rate
    else:
        # Fallback: простое среднее всех отзывов
        total_reviews_count = len(reviews)
        avg_rating = sum(r.rating for r in reviews) / total_reviews_count
        success_count = sum(1 for r in reviews if r.success)
        success_rate = (success_count / total_reviews_count) * 100.0

    # Распределение рейтингов
    rating_distribution: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for review in reviews:
        rating_int = int(review.rating)
        rating_distribution[rating_int] = rating_distribution.get(rating_int, 0) + 1

    return FilamentRatingStats(
        avg_rating=round(avg_rating, 2) if avg_rating is not None else None,
        total_reviews=len(reviews),
        success_rate=round(success_rate, 1) if success_rate is not None else None,
        rating_distribution=rating_distribution,
    )


@router.get("/{review_id}", response_model=FilamentReviewResponse)
async def get_review(
    review_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentReviewResponse:
    """Получить отзыв по ID."""
    result = await db.execute(
        select(FilamentReview)
        .options(selectinload(FilamentReview.user))
        .where(FilamentReview.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise_error(404, ERR_REVIEW_NOT_FOUND)

    # Загружаем пресет если есть
    preset_name = None
    if review.preset_id:
        preset_result = await db.execute(select(Preset).where(Preset.id == review.preset_id))
        preset = preset_result.scalar_one_or_none()
        preset_name = preset.name if preset else None
    
    return FilamentReviewResponse(
        id=review.id,
        filament_id=review.filament_id,
        user_id=review.user_id,
        preset_id=review.preset_id,
        preset_name=preset_name,
        username=review.user.username if review.user else None,
        user_badges=review.user.badges if review.user else None,
        success=review.success,
        rating=review.rating,
        comment=review.comment,
        printer_model=review.printer_model,
        active=review.active,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


@router.post("/", response_model=FilamentReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    review_data: FilamentReviewCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FilamentReviewResponse:
    """Создать отзыв о материале."""
    from app.models.filament import Filament

    # Проверяем существование материала
    filament_result = await db.execute(select(Filament).where(Filament.id == review_data.filament_id))
    filament = filament_result.scalar_one_or_none()
    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Определяем пресет для отзыва
    preset_id = review_data.preset_id
    
    if preset_id is None:
        # Если пресет не указан, пытаемся найти официальный пресет
        official_preset_result = await db.execute(
            select(Preset).where(
                Preset.filament_id == review_data.filament_id,
                Preset.is_official == True,
                Preset.active == True,
            ).order_by(Preset.created_at.desc()).limit(1)
        )
        official_preset = official_preset_result.scalar_one_or_none()
        
        if official_preset:
            preset_id = official_preset.id
        else:
            # Если нет официального, ищем сохраненные пресеты пользователя
            saved_presets_result = await db.execute(
                select(UserSavedPreset).join(Preset).where(
                    UserSavedPreset.user_id == current_user.id,
                    Preset.filament_id == review_data.filament_id,
                    Preset.active == True,
                ).limit(1)
            )
            saved_preset = saved_presets_result.scalar_one_or_none()
            
            if saved_preset:
                preset_id = saved_preset.preset_id
            else:
                raise_error(400, ERR_ADD_PRESET_FIRST)
    
    # Проверяем существование пресета и соответствие филаменту
    preset_result = await db.execute(
        select(Preset).where(
            Preset.id == preset_id,
            Preset.filament_id == review_data.filament_id,
            Preset.active == True,
        )
    )
    preset = preset_result.scalar_one_or_none()
    if not preset:
        raise_error(404, ERR_PRESET_NOT_MATCH)
    
    # Проверяем доступность пресета для пользователя
    # Пресет должен быть либо официальным, либо сохраненным пользователем
    if not preset.is_official:
        saved_preset_check = await db.execute(
            select(UserSavedPreset).where(
                UserSavedPreset.user_id == current_user.id,
                UserSavedPreset.preset_id == preset_id,
            )
        )
        if not saved_preset_check.scalar_one_or_none():
            raise_error(403, ERR_REVIEW_SAVED_ONLY)
    
    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    if review_data.comment:
        is_valid, error_msg = await validate_text_field(review_data.comment, db, "review_comment")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if review_data.printer_model:
        is_valid, error_msg = await validate_text_field(review_data.printer_model, db, "printer_model")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    # Проверяем, не оставил ли пользователь уже отзыв для этого пресета
    existing_review_result = await db.execute(
        select(FilamentReview).where(
            FilamentReview.filament_id == review_data.filament_id,
            FilamentReview.preset_id == preset_id,
            FilamentReview.user_id == current_user.id,
            FilamentReview.active == True,
        )
    )
    existing_review = existing_review_result.scalar_one_or_none()
    if existing_review:
        raise_error(400, ERR_REVIEW_ALREADY_EXISTS)

    # Создаём отзыв
    review = FilamentReview(
        filament_id=review_data.filament_id,
        preset_id=preset_id,
        user_id=current_user.id,
        success=review_data.success,
        rating=review_data.rating,
        comment=review_data.comment,
        printer_model=review_data.printer_model,
        active=True,
    )

    db.add(review)
    await db.commit()
    await db.refresh(review)

    # Обновляем рейтинги пресета
    await update_preset_ratings(preset_id, db)

    # Загружаем пользователя и пресет для ответа
    await db.refresh(review, ["user"])
    preset_name = preset.name if preset else None
    
    return FilamentReviewResponse(
        id=review.id,
        filament_id=review.filament_id,
        user_id=review.user_id,
        preset_id=review.preset_id,
        preset_name=preset_name,
        username=review.user.username if review.user else None,
        user_badges=review.user.badges if review.user else None,
        success=review.success,
        rating=review.rating,
        comment=review.comment,
        printer_model=review.printer_model,
        active=review.active,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


@router.patch("/{review_id}", response_model=FilamentReviewResponse)
async def update_review(
    review_id: int,
    review_data: FilamentReviewUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FilamentReviewResponse:
    """Обновить отзыв."""
    result = await db.execute(
        select(FilamentReview)
        .options(selectinload(FilamentReview.user))
        .where(FilamentReview.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise_error(404, ERR_REVIEW_NOT_FOUND)

    # Проверяем права: только автор или админ
    if review.user_id != current_user.id and current_user.role.value != "admin":
        raise_error(403, ERR_NO_PERMISSION_EDIT_REVIEW)
    
    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    update_data = review_data.model_dump(exclude_unset=True)
    
    if "comment" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["comment"], db, "review_comment")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if "printer_model" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["printer_model"], db, "printer_model")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    # Сохраняем старый preset_id для обновления рейтингов
    old_preset_id = review.preset_id
    
    # Обновляем поля
    for key, value in update_data.items():
        setattr(review, key, value)

    await db.commit()
    await db.refresh(review)
    
    # Обновляем рейтинги пресета (старого и нового, если изменился)
    if old_preset_id:
        await update_preset_ratings(old_preset_id, db)
    if review.preset_id and review.preset_id != old_preset_id:
        await update_preset_ratings(review.preset_id, db)

    # Загружаем пресет если есть
    preset_name = None
    if review.preset_id:
        preset_result = await db.execute(select(Preset).where(Preset.id == review.preset_id))
        preset = preset_result.scalar_one_or_none()
        preset_name = preset.name if preset else None
    
    return FilamentReviewResponse(
        id=review.id,
        filament_id=review.filament_id,
        user_id=review.user_id,
        preset_id=review.preset_id,
        preset_name=preset_name,
        username=review.user.username if review.user else None,
        user_badges=review.user.badges if review.user else None,
        success=review.success,
        rating=review.rating,
        comment=review.comment,
        printer_model=review.printer_model,
        active=review.active,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Удалить отзыв (деактивация)."""
    result = await db.execute(
        select(FilamentReview).where(FilamentReview.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise_error(404, ERR_REVIEW_NOT_FOUND)

    # Проверяем права: только автор или админ
    if review.user_id != current_user.id and current_user.role.value != "admin":
        raise_error(403, ERR_NO_PERMISSION_DELETE_REVIEW)

    # Сохраняем preset_id перед деактивацией
    preset_id = review.preset_id
    
    # Деактивируем отзыв вместо физического удаления
    review.active = False
    await db.commit()
    
    # Обновляем рейтинги пресета после деактивации отзыва
    if preset_id:
        await update_preset_ratings(preset_id, db)

