"""Filament endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.filament import Filament
from app.models.printer import Printer
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
        # Search in filament name AND brand name (LEFT JOIN чтобы не потерять филаменты без бренда)
        query = query.outerjoin(Brand).where(
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
        # Search in filament name AND brand name (LEFT JOIN чтобы не потерять филаменты без бренда)
        count_query = count_query.outerjoin(Brand).where(
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
    filament_ids = [filament.id for filament in filaments]

    pages = (total + size - 1) // size if total > 0 else 0

    preset_stats: dict[int, dict[str, int]] = {}
    preset_summary_map: dict[int, dict[str, object]] = {}

    if filament_ids:
        from app.models.preset import Preset, PresetModerationStatus

        stats_query = (
            select(
                Preset.filament_id,
                func.count().label("total"),
                func.sum(case((Preset.is_official.is_(True), 1), else_=0)).label("official_count"),
                func.sum(case((Preset.is_official.is_(False), 1), else_=0)).label("community_count"),
            )
            .where(
                Preset.filament_id.in_(filament_ids),
                Preset.active.is_(True),
                Preset.moderation_status == PresetModerationStatus.APPROVED,
            )
            .group_by(Preset.filament_id)
        )
        stats_rows = await db.execute(stats_query)
        for row in stats_rows:
            preset_stats[row.filament_id] = {
                "total": int(row.total or 0),
                "official": int(row.official_count or 0),
                "community": int(row.community_count or 0),
            }

        preset_query = (
            select(Preset)
            .where(
                Preset.filament_id.in_(filament_ids),
                Preset.active.is_(True),
                Preset.moderation_status == PresetModerationStatus.APPROVED,
            )
            .order_by(
                Preset.filament_id,
                desc(Preset.is_weighted),
                desc(Preset.rating),
                desc(Preset.updated_at),
            )
        )
        presets = await db.execute(preset_query)
        for preset in presets.scalars():
            bucket = preset_summary_map.setdefault(preset.filament_id, {})
            if preset.is_official and "official" not in bucket:
                bucket["official"] = preset
            if preset.is_weighted and "weighted" not in bucket:
                bucket["weighted"] = preset
            if not preset.is_official and not preset.is_weighted and "community" not in bucket:
                bucket["community"] = preset

    # Serialize with brand_name and preset summary
    filament_responses = []
    for filament in filaments:
        filament_dict = FilamentResponse.model_validate(filament).model_dump()
        filament_dict["brand_name"] = filament.brand.name if filament.brand else None

        stats = preset_stats.get(filament.id)
        if stats:
            filament_dict["presets_count"] = stats["total"]
            filament_dict["official_presets_count"] = stats["official"]
            filament_dict["community_presets_count"] = stats["community"]
        else:
            filament_dict["presets_count"] = 0
            filament_dict["official_presets_count"] = 0
            filament_dict["community_presets_count"] = 0

        summaries: list[dict] = []
        summary_bucket = preset_summary_map.get(filament.id, {})

        def serialize_preset(preset_obj, preset_type: str) -> dict:
            return {
                "id": preset_obj.id,
                "name": preset_obj.name,
                "is_official": preset_obj.is_official,
                "is_weighted": preset_obj.is_weighted,
                "extruder_temp": preset_obj.extruder_temp,
                "bed_temp": preset_obj.bed_temp,
                "fan_speed": preset_obj.fan_speed,
                "flow_rate": preset_obj.flow_rate,
                "print_speed": preset_obj.print_speed,
                "layer_height": preset_obj.layer_height,
                "rating": preset_obj.rating,
                "success_rate": preset_obj.success_rate,
                "updated_at": preset_obj.updated_at,
                "preset_type": preset_type,
            }

        if "official" in summary_bucket:
            official_preset = summary_bucket["official"]
            filament_dict["official_preset"] = serialize_preset(official_preset, "official")
            summaries.append(filament_dict["official_preset"])
        else:
            filament_dict["official_preset"] = None

        if "weighted" in summary_bucket:
            weighted_preset = summary_bucket["weighted"]
            # Avoid duplicating if weighted preset already marked as official
            if filament_dict["official_preset"] is None or weighted_preset.id != filament_dict["official_preset"]["id"]:
                summaries.append(serialize_preset(weighted_preset, "weighted"))

        if "community" in summary_bucket:
            community_preset = summary_bucket["community"]
            summaries.append(serialize_preset(community_preset, "community"))

        filament_dict["preset_summaries"] = summaries

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
    
    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    is_valid, error_msg = await validate_text_field(data.name, db, "Название материала")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    if data.description:
        is_valid, error_msg = await validate_text_field(data.description, db, "Описание материала")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if data.color_name:
        is_valid, error_msg = await validate_text_field(data.color_name, db, "Название цвета")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

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
    
    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    update_data = data.model_dump(exclude_unset=True)
    
    if "name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["name"], db, "Название материала")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if "description" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["description"], db, "Описание материала")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if "color_name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["color_name"], db, "Название цвета")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    # Update fields
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


@router.get("/{filament_id}/compatible-printers", response_model=list[dict])
async def get_compatible_printers(
    filament_id: int,
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> list[dict]:
    """
    Получить список принтеров, совместимых с филаментом.
    
    Использует VIEW filament_printer_compatibility_view для вывода совместимости
    на основе существующих связей через Preset и PrintProfile.
    """
    from sqlalchemy import text
    
    # Проверяем существование филамента
    filament = await db.get(Filament, filament_id)
    if not filament:
        raise HTTPException(status_code=404, detail="Филамент не найден")
    
    # Используем VIEW для получения совместимых принтеров
    query = text("""
        SELECT DISTINCT
            printer_id,
            printer_slug,
            printer_name,
            relation_source,
            MAX(confidence_score) as confidence_score
        FROM filament_printer_compatibility_view
        WHERE filament_id = :filament_id
          AND confidence_score >= :min_confidence
        GROUP BY printer_id, printer_slug, printer_name, relation_source
        ORDER BY confidence_score DESC, printer_name
    """)
    
    result = await db.execute(query, {"filament_id": filament_id, "min_confidence": min_confidence})
    rows = result.fetchall()
    
    # Получаем дополнительную информацию о принтерах
    printer_ids = [row[0] for row in rows]
    if not printer_ids:
        return []
    
    printers_query = select(Printer).where(Printer.id.in_(printer_ids))
    printers_result = await db.execute(printers_query)
    printers = {p.id: p for p in printers_result.scalars().all()}
    
    # Формируем ответ
    compatible_printers = []
    for row in rows:
        printer_id, printer_slug, printer_name, relation_source, confidence_score = row
        printer = printers.get(printer_id)
        if printer:
            compatible_printers.append({
                "id": printer.id,
                "slug": printer.slug,
                "name": printer.name,
                "manufacturer": printer.manufacturer,
                "relation_source": relation_source,
                "confidence_score": float(confidence_score),
            })
    
    return compatible_printers


