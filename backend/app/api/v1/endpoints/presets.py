"""Preset endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_current_brand_user
from app.db.session import get_db
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.schemas.preset import (
    PresetCreate,
    PresetListResponse,
    PresetResponse,
    PresetUpdate,
    RecommendedPresetResponse,
)

router = APIRouter(prefix="/presets", tags=["presets"])


@router.get("/", response_model=PresetListResponse)
async def list_presets(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    filament_id: int | None = Query(None, gt=0),
    is_official: bool | None = Query(None),
    user_id: int | None = Query(None, gt=0),
) -> PresetListResponse:
    """Получить список пресетов."""
    # Build query
    query = select(Preset)
    if active_only:
        query = query.where(Preset.active == True)
    if filament_id:
        query = query.where(Preset.filament_id == filament_id)
    if is_official is not None:
        query = query.where(Preset.is_official == is_official)
    if user_id is not None:
        # Если указан user_id, показываем ВСЕ пресеты пользователя (включая неодобренные)
        query = query.where(Preset.user_id == user_id)
    else:
        # Показываем только одобренные пресеты (официальные автоматически одобрены)
        query = query.where(
            or_(
                Preset.moderation_status == PresetModerationStatus.APPROVED,
                Preset.is_official == True  # Официальные всегда видимы
            )
        )

    # Count total
    count_query = select(func.count()).select_from(Preset)
    if active_only:
        count_query = count_query.where(Preset.active == True)
    if filament_id:
        count_query = count_query.where(Preset.filament_id == filament_id)
    if is_official is not None:
        count_query = count_query.where(Preset.is_official == is_official)
    if user_id is not None:
        count_query = count_query.where(Preset.user_id == user_id)
    else:
        # Учитываем только одобренные
        count_query = count_query.where(
            or_(
                Preset.moderation_status == PresetModerationStatus.APPROVED,
                Preset.is_official == True
            )
        )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(
        Preset.is_official.desc(), Preset.rating.desc().nulls_last(), Preset.created_at.desc()
    )

    # Execute
    result = await db.execute(query)
    presets = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 0

    return PresetListResponse(
        items=[PresetResponse.model_validate(preset) for preset in presets],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/recommend", response_model=RecommendedPresetResponse)
async def recommend_preset(
    filament_id: int = Query(..., gt=0, description="Filament ID to get recommendations for"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> RecommendedPresetResponse:
    """
    Получить рекомендованные настройки для материала (weighted average алгоритм).
    
    Вычисляет оптимальные значения на основе всех одобренных пресетов для материала,
    используя взвешенное среднее: Σ(значение_i × вес_i) / Σ(вес_i)
    
    Вес = rating × (1 + usage_count / 100)
    """
    # Проверяем существование материала
    from app.models.filament import Filament
    
    filament_result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = filament_result.scalar_one_or_none()
    
    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")
    
    # Получаем все одобренные пресеты для материала
    query = select(Preset).where(
        Preset.filament_id == filament_id,
        Preset.active == True,
        or_(
            Preset.moderation_status == PresetModerationStatus.APPROVED,
            Preset.is_official == True
        )
    )
    result = await db.execute(query)
    presets = result.scalars().all()
    
    if not presets:
        raise HTTPException(
            status_code=404,
            detail="No approved presets found for this filament"
        )
    
    # Вычисляем веса для каждого пресета
    # Вес = rating × (1 + usage_count / 100)
    # Если rating отсутствует, используем usage_count / 10 как базовый вес
    def calculate_weight(preset: Preset) -> float:
        """Вычислить вес пресета для weighted average."""
        base_weight = preset.rating if preset.rating is not None else (preset.usage_count / 10.0)
        if base_weight <= 0:
            base_weight = 1.0  # Минимальный вес для участия в расчете
        
        # Увеличиваем вес на основе usage_count (но не слишком сильно)
        usage_factor = 1 + (preset.usage_count / 100.0)
        
        # Официальные пресеты получают дополнительный вес
        official_bonus = 1.5 if preset.is_official else 1.0
        
        return base_weight * usage_factor * official_bonus
    
    weights = [calculate_weight(p) for p in presets]
    total_weight = sum(weights)
    
    if total_weight == 0:
        raise HTTPException(
            status_code=500,
            detail="Unable to calculate recommendation (zero total weight)"
        )
    
    # Вычисляем weighted average для обязательных параметров
    extruder_temp = sum(p.extruder_temp * w for p, w in zip(presets, weights)) / total_weight
    bed_temp = sum(p.bed_temp * w for p, w in zip(presets, weights)) / total_weight
    print_speed = sum(p.print_speed * w for p, w in zip(presets, weights)) / total_weight
    
    # Вычисляем weighted average для опциональных параметров (только если есть значения)
    def weighted_avg_optional(values_and_weights: list[tuple[float, float]]) -> float | None:
        """Вычислить weighted average для опциональных параметров."""
        filtered = [(v, w) for v, w in values_and_weights if v is not None]
        if not filtered:
            return None
        values, ws = zip(*filtered)
        total_w = sum(ws)
        if total_w == 0:
            return None
        return sum(v * w for v, w in filtered) / total_w
    
    travel_speed = weighted_avg_optional([(p.travel_speed, w) if p.travel_speed is not None else (None, w) for p, w in zip(presets, weights)])
    layer_height = weighted_avg_optional([(p.layer_height, w) if p.layer_height is not None else (None, w) for p, w in zip(presets, weights)])
    first_layer_height = weighted_avg_optional([(p.first_layer_height, w) if p.first_layer_height is not None else (None, w) for p, w in zip(presets, weights)])
    flow_rate = weighted_avg_optional([(p.flow_rate, w) if p.flow_rate is not None else (None, w) for p, w in zip(presets, weights)])
    
    # fan_speed - целое число, нужно округлить
    fan_speed_values = [(p.fan_speed, w) for p, w in zip(presets, weights) if p.fan_speed is not None]
    fan_speed = None
    if fan_speed_values:
        fan_speed_avg = sum(v * w for v, w in fan_speed_values) / sum(w for _, w in fan_speed_values)
        fan_speed = round(fan_speed_avg)
    
    retraction_length = weighted_avg_optional([(p.retraction_length, w) if p.retraction_length is not None else (None, w) for p, w in zip(presets, weights)])
    retraction_speed = weighted_avg_optional([(p.retraction_speed, w) if p.retraction_speed is not None else (None, w) for p, w in zip(presets, weights)])
    
    # Вычисляем средний рейтинг
    ratings = [p.rating for p in presets if p.rating is not None]
    avg_rating = sum(ratings) / len(ratings) if ratings else None
    
    return RecommendedPresetResponse(
        filament_id=filament_id,
        extruder_temp=round(extruder_temp, 1),
        bed_temp=round(bed_temp, 1),
        print_speed=round(print_speed, 1),
        travel_speed=round(travel_speed, 1) if travel_speed is not None else None,
        layer_height=round(layer_height, 3) if layer_height is not None else None,
        first_layer_height=round(first_layer_height, 3) if first_layer_height is not None else None,
        flow_rate=round(flow_rate, 1) if flow_rate is not None else None,
        fan_speed=fan_speed,
        retraction_length=round(retraction_length, 2) if retraction_length is not None else None,
        retraction_speed=round(retraction_speed, 1) if retraction_speed is not None else None,
        presets_count=len(presets),
        avg_rating=round(avg_rating, 2) if avg_rating else None,
    )


@router.get("/{preset_id}", response_model=PresetResponse)
async def get_preset(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresetResponse:
    """Получить пресет по ID."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    return PresetResponse.model_validate(preset)


@router.post("/", response_model=PresetResponse, status_code=201)
async def create_preset(
    data: PresetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetResponse:
    """Создать пресет."""
    # Check if filament exists
    from app.models.filament import Filament

    filament_result = await db.execute(select(Filament).where(Filament.id == data.filament_id))
    filament = filament_result.scalar_one_or_none()

    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")

    # Create preset
    preset_data = data.model_dump(exclude={"user_id"})  # Игнорируем user_id из запроса
    preset_data["user_id"] = current_user.id  # Используем текущего пользователя
    
    # Проверка: только верифицированные производители могут создавать официальные пресеты
    if preset_data.get("is_official", False):
        # TODO: Добавить проверку verified бренда через filament.brand_id
        if current_user.role.value != "brand":
            raise HTTPException(
                status_code=403,
                detail="Only verified manufacturers can create official presets"
            )
        preset_data["moderation_status"] = PresetModerationStatus.APPROVED
    else:
        # Для MVP модерация отключена - все пресеты сразу одобрены
        preset_data["moderation_status"] = PresetModerationStatus.APPROVED
    
    preset = Preset(**preset_data)
    db.add(preset)
    await db.commit()
    await db.refresh(preset)

    return PresetResponse.model_validate(preset)


@router.patch("/{preset_id}", response_model=PresetResponse)
async def update_preset(
    preset_id: int,
    data: PresetUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetResponse:
    """Обновить пресет."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    # Проверка: пользователь может редактировать только свои пресеты (или админ)
    if preset.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=403,
            detail="You can only edit your own presets"
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(preset, field, value)

    await db.commit()
    await db.refresh(preset)

    return PresetResponse.model_validate(preset)


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Удалить пресет."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    # Проверка: пользователь может удалять только свои пресеты (или админ)
    if preset.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own presets"
        )

    await db.delete(preset)
    await db.commit()


@router.post("/{preset_id}/increment-usage", response_model=PresetResponse)
async def increment_usage(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresetResponse:
    """Увеличить счётчик использования пресета."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    preset.usage_count += 1
    await db.commit()
    await db.refresh(preset)

    return PresetResponse.model_validate(preset)



    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    # Проверка: пользователь может удалять только свои пресеты (или админ)
    if preset.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own presets"
        )

    await db.delete(preset)
    await db.commit()


@router.post("/{preset_id}/increment-usage", response_model=PresetResponse)
async def increment_usage(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresetResponse:
    """Увеличить счётчик использования пресета."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    preset.usage_count += 1
    await db.commit()
    await db.refresh(preset)

    return PresetResponse.model_validate(preset)

