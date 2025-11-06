"""Filament endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.filament import Filament
from app.models.user import User, UserRole
from app.schemas.filament import (
    FilamentCreate,
    FilamentListResponse,
    FilamentResponse,
    FilamentUpdate,
)

router = APIRouter(prefix="/filaments", tags=["filaments"])


@router.get("/", response_model=FilamentListResponse)
async def list_filaments(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    brand_id: int | None = Query(None),
    material_type: str | None = Query(None),
    search: str | None = Query(None, description="Поиск по названию материала"),
) -> FilamentListResponse:
    """Получить список материалов."""
    from app.models.brand import Brand
    
    # Build query
    query = select(Filament).options(selectinload(Filament.brand))
    if active_only:
        query = query.where(Filament.active == True)
    if brand_id:
        query = query.where(Filament.brand_id == brand_id)
    if material_type:
        query = query.where(Filament.material_type == material_type)
    if search:
        search_term = f"%{search.lower()}%"
        # Search in filament name AND brand name
        query = query.join(Brand).where(
            or_(
                Filament.name.ilike(search_term),
                Brand.name.ilike(search_term)
            )
        )

    # Count total
    count_query = select(func.count()).select_from(Filament)
    if active_only:
        count_query = count_query.where(Filament.active == True)
    if brand_id:
        count_query = count_query.where(Filament.brand_id == brand_id)
    if material_type:
        count_query = count_query.where(Filament.material_type == material_type)
    if search:
        search_term = f"%{search.lower()}%"
        # Search in filament name AND brand name
        count_query = count_query.join(Brand).where(
            or_(
                Filament.name.ilike(search_term),
                Brand.name.ilike(search_term)
            )
        )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(Filament.name)

    # Execute
    result = await db.execute(query)
    filaments = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 0

    # Serialize with brand_name
    filament_responses = []
    for filament in filaments:
        filament_dict = FilamentResponse.model_validate(filament).model_dump()
        filament_dict["brand_name"] = filament.brand.name if filament.brand else None
        filament_responses.append(filament_dict)

    return FilamentListResponse(
        items=filament_responses,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/material-types")
async def get_material_types(
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = Query(True),
) -> list[str]:
    """
    Получить список уникальных типов материалов.
    
    Возвращает типы из material_mappings (начальные типы из миграций) +
    типы из активных филаментов (если есть).
    """
    from app.models.material_mapping import MaterialMapping
    
    # Получаем типы из material_mappings (начальные типы, заполненные миграцией)
    mapping_query = select(MaterialMapping.material_type).distinct()
    if active_only:
        mapping_query = mapping_query.where(MaterialMapping.active == True)
    mapping_query = mapping_query.order_by(MaterialMapping.material_type)
    
    mapping_result = await db.execute(mapping_query)
    mapping_types = {row[0] for row in mapping_result.all() if row[0]}
    
    # Получаем типы из активных филаментов (если есть дополнительные)
    filament_query = select(Filament.material_type).distinct()
    if active_only:
        filament_query = filament_query.where(Filament.active == True)
    filament_query = filament_query.order_by(Filament.material_type)
    
    filament_result = await db.execute(filament_query)
    filament_types = {row[0] for row in filament_result.all() if row[0]}
    
    # Объединяем оба множества (уникальные типы)
    all_material_types = sorted(mapping_types | filament_types)
    
    return all_material_types


@router.get("/{filament_id}", response_model=FilamentResponse)
async def get_filament(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentResponse:
    """Получить материал по ID."""
    result = await db.execute(
        select(Filament).options(selectinload(Filament.brand)).where(Filament.id == filament_id)
    )
    filament = result.scalar_one_or_none()

    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")

    filament_dict = FilamentResponse.model_validate(filament).model_dump()
    filament_dict["brand_name"] = filament.brand.name if filament.brand else None
    return filament_dict


@router.get("/{filament_id}/presets")
async def get_filament_presets(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    is_official: bool | None = Query(None),
) -> dict:
    """Получить пресеты для материала."""
    from app.models.preset import Preset
    from app.schemas.preset import PresetResponse

    # Check if filament exists
    filament_result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = filament_result.scalar_one_or_none()

    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")

    # Build query - показываем только активные пресеты (все пресеты автоматически одобрены)
    from app.models.preset import PresetModerationStatus
    from app.models.preset_printer import PresetPrinter
    from app.schemas.printer import PrinterResponse
    
    query = select(Preset).options(
        selectinload(Preset.printer_links).selectinload(PresetPrinter.printer)
    ).where(
        Preset.filament_id == filament_id,
        Preset.active == True,
        Preset.moderation_status == PresetModerationStatus.APPROVED  # Все пресеты автоматически APPROVED
    )
    if is_official is not None:
        query = query.where(Preset.is_official == is_official)

    # Count total
    count_query = select(func.count()).select_from(Preset).where(
        Preset.filament_id == filament_id,
        Preset.active == True,
        Preset.moderation_status == PresetModerationStatus.APPROVED
    )
    if is_official is not None:
        count_query = count_query.where(Preset.is_official == is_official)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = (
        query.offset(offset)
        .limit(size)
        .order_by(Preset.is_official.desc(), Preset.rating.desc().nulls_last(), Preset.created_at.desc())
    )

    # Execute
    result = await db.execute(query)
    presets = result.scalars().unique().all()

    # Преобразуем пресеты в ответ с принтерами
    preset_items = []
    for preset in presets:
        try:
            preset_dict = PresetResponse.model_validate(preset).model_dump()
            preset_dict["printers"] = [
                PrinterResponse.model_validate(link.printer).model_dump()
                for link in preset.printer_links
            ]
            preset_items.append(preset_dict)
        except Exception as e:
            logger.error(f"Error serializing preset {preset.id}: {e}", exc_info=True)
            # Пропускаем проблемный пресет, но продолжаем обработку остальных
            continue

    pages = (total + size - 1) // size if total > 0 else 0

    return {
        "items": preset_items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


@router.post("/", response_model=FilamentResponse, status_code=201)
async def create_filament(
    data: FilamentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FilamentResponse:
    """Создать материал."""
    # Check if brand exists
    from app.models.brand import Brand
    from app.services.material_mapping_service import (
        get_material_preset,
        create_material_mapping,
    )
    from app.models.material_mapping import MaterialMappingPriority

    brand_result = await db.execute(select(Brand).where(Brand.id == data.brand_id))
    brand = brand_result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    # Проверка прав доступа: только админ или сотрудник бренда может создавать материалы
    if current_user.role != UserRole.ADMIN and current_user.brand_id != data.brand_id:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions. You can only create materials for your own brand."
        )

    # Create filament
    filament = Filament(**data.model_dump())
    db.add(filament)
    await db.flush()  # Получаем ID без коммита
    
    # Если бренд верифицирован - автоматически генерируем QR-код
    if brand.verified:
        from app.services.qr_service import generate_short_code
        
        # Генерируем короткий код
        short_code = generate_short_code(filament.id)
        
        # Проверяем уникальность (на случай коллизий)
        existing = await db.execute(
            select(Filament).where(Filament.qr_code == short_code)
        )
        if existing.scalar_one_or_none():
            # Если коллизия - добавляем суффикс
            short_code = f"{short_code}-{filament.id % 1000}"
        
        filament.qr_code = short_code
    
    await db.commit()
    await db.refresh(filament)

    # Автоматически создаём маппинг для нового типа материала, если его ещё нет
    material_type_upper = data.material_type.upper().strip()
    
    # Проверяем, есть ли уже маппинг для этого типа
    from app.models.material_mapping import MaterialMapping
    existing_mapping = await db.execute(
        select(MaterialMapping).where(
            MaterialMapping.material_type.ilike(material_type_upper),
            MaterialMapping.active == True,
        )
    )
    
    if not existing_mapping.scalar_one_or_none():
        # Маппинга нет - определяем базовый пресет через сервис
        base_preset = await get_material_preset(
            data.material_type,
            db,
            log_unknown=True,
        )
        
        # Создаём автоматический маппинг
        try:
            await create_material_mapping(
                material_type=data.material_type,
                orcaslicer_preset=base_preset,
                db=db,
                priority=MaterialMappingPriority.AUTOMATIC,
                brand_id=None,  # Автоматический маппинг, не от производителя
                description=f"Автоматически создан для материала '{data.material_type}' → '{base_preset}'",
            )
        except Exception as e:
            # Логируем ошибку, но не блокируем создание филамента
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to create automatic material mapping for '{data.material_type}': {e}"
            )

    return FilamentResponse.model_validate(filament)


@router.patch("/{filament_id}", response_model=FilamentResponse)
async def update_filament(
    filament_id: int,
    data: FilamentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FilamentResponse:
    """Обновить материал."""
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()

    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")
    
    # Проверка прав доступа: только админ или сотрудник бренда может редактировать материалы
    if current_user.role != UserRole.ADMIN and current_user.brand_id != filament.brand_id:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions. You can only edit materials from your own brand."
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(filament, field, value)

    await db.commit()
    await db.refresh(filament)

    return FilamentResponse.model_validate(filament)


@router.delete("/{filament_id}", status_code=204)
async def delete_filament(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Удалить материал."""
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()

    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")
    
    # Проверка прав доступа: только админ или сотрудник бренда может удалять материалы
    if current_user.role != UserRole.ADMIN and current_user.brand_id != filament.brand_id:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions. You can only delete materials from your own brand."
        )

    await db.delete(filament)
    await db.commit()


