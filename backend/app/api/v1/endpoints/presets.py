"""Preset endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
import json
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user, get_current_brand_user
from app.db.session import get_db
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.user import User
from app.models.filament import Filament
from app.schemas.preset import (
    PresetCreate,
    PresetListResponse,
    PresetResponse,
    PresetUpdate,
    RecommendedPresetResponse,
)
from app.schemas.printer import PrinterResponse
from app.services.orcaslicer_exporter import export_preset_to_orcaslicer, generate_profile_info, preset_to_orcaslicer_json

router = APIRouter(prefix="/presets", tags=["presets"])


@router.get("/", response_model=PresetListResponse)
async def list_presets(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    filament_id: int | None = Query(None, gt=0),
    printer_id: int | None = Query(None, gt=0, description="Фильтр по принтеру"),
    is_official: bool | None = Query(None),
    user_id: int | None = Query(None, gt=0),
) -> PresetListResponse:
    """Получить список пресетов."""
    # Build query
    query = select(Preset).options(selectinload(Preset.printer_links).selectinload(PresetPrinter.printer))
    
    if active_only:
        query = query.where(Preset.active == True)
    if filament_id:
        query = query.where(Preset.filament_id == filament_id)
    if printer_id:
        # Фильтруем пресеты, связанные с указанным принтером
        query = query.join(PresetPrinter).where(PresetPrinter.printer_id == printer_id)
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
    if printer_id:
        count_query = count_query.join(PresetPrinter).where(PresetPrinter.printer_id == printer_id)
    if is_official is not None:
        count_query = count_query.where(Preset.is_official == is_official)
    if user_id is not None:
        count_query = count_query.where(Preset.user_id == user_id)
    else:
        count_query = count_query.where(
            or_(
                Preset.moderation_status == PresetModerationStatus.APPROVED,
                Preset.is_official == True
            )
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Pagination
    pages = (total + size - 1) // size
    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    # Execute query
    result = await db.execute(query)
    presets = result.scalars().unique().all()

    return PresetListResponse(
        items=[PresetResponse.model_validate(p) for p in presets],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{preset_id}", response_model=PresetResponse)
async def get_preset(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresetResponse:
    """Получить пресет по ID."""
    result = await db.execute(
        select(Preset)
        .options(selectinload(Preset.printer_links).selectinload(PresetPrinter.printer))
        .where(Preset.id == preset_id)
    )
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    # Преобразуем пресет в ответ с принтерами
    preset_dict = PresetResponse.model_validate(preset).model_dump()
    preset_dict["printers"] = [
        PrinterResponse.model_validate(link.printer).model_dump()
        for link in preset.printer_links
    ]
    return PresetResponse(**preset_dict)


@router.post("/", response_model=PresetResponse, status_code=201)
async def create_preset(
    data: PresetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetResponse:
    """Создать новый пресет."""
    from app.models.filament import Filament
    
    # Проверка существования filament
    filament_result = await db.execute(select(Filament).where(Filament.id == data.filament_id))
    filament = filament_result.scalar_one_or_none()
    
    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")
    
    # Проверка прав на создание официального пресета
    if data.is_official:
        # Только верифицированные производители могут создавать официальные пресеты
        if current_user.role.value != "brand" and current_user.role.value != "admin":
            raise HTTPException(
                status_code=403,
                detail="Only verified brands can create official presets"
            )
        # Проверяем, что filament принадлежит бренду пользователя
        if current_user.role.value == "brand" and filament.brand_id != current_user.brand_id:
            raise HTTPException(
                status_code=403,
                detail="You can only create official presets for your brand's filaments"
            )
    
    preset = Preset(
        filament_id=data.filament_id,
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        extruder_temp=data.extruder_temp,
        bed_temp=data.bed_temp,
        print_speed=data.print_speed,
        travel_speed=data.travel_speed,
        layer_height=data.layer_height,
        first_layer_height=data.first_layer_height,
        flow_rate=data.flow_rate,
        fan_speed=data.fan_speed,
        retraction_length=data.retraction_length,
        retraction_speed=data.retraction_speed,
        is_official=data.is_official if data.is_official else False,
        orcaslicer_settings=data.orcaslicer_settings,
        active=True,
    )
    
    # Модерация: официальные пресеты автоматически одобрены
    if preset.is_official:
        preset.moderation_status = PresetModerationStatus.APPROVED
    else:
        preset.moderation_status = PresetModerationStatus.PENDING
    
    db.add(preset)
    await db.flush()  # Получаем ID пресета
    
    # Создаём связи с принтерами
    if data.printer_ids:
        for printer_id in data.printer_ids:
            # Проверяем существование принтера
            printer_result = await db.execute(select(Printer).where(Printer.id == printer_id))
            printer = printer_result.scalar_one_or_none()
            if not printer:
                continue  # Пропускаем несуществующие принтеры
            
            # Создаём связь
            preset_printer = PresetPrinter(
                preset_id=preset.id,
                printer_id=printer_id,
                is_primary=False,  # Первый принтер будет основным
            )
            db.add(preset_printer)
        
        # Первый принтер делаем основным
        if data.printer_ids:
            first_link = await db.execute(
                select(PresetPrinter)
                .where(PresetPrinter.preset_id == preset.id)
                .where(PresetPrinter.printer_id == data.printer_ids[0])
            )
            first_link_obj = first_link.scalar_one_or_none()
            if first_link_obj:
                first_link_obj.is_primary = True
    
    await db.commit()
    await db.refresh(preset, ["printer_links"])
    
    # Загружаем принтеры для ответа
    result = await db.execute(
        select(Preset)
        .options(selectinload(Preset.printer_links).selectinload(PresetPrinter.printer))
        .where(Preset.id == preset.id)
    )
    preset_with_printers = result.scalar_one()
    
    # Преобразуем пресет в ответ с принтерами
    preset_dict = PresetResponse.model_validate(preset_with_printers).model_dump()
    preset_dict["printers"] = [
        PrinterResponse.model_validate(link.printer).model_dump()
        for link in preset_with_printers.printer_links
    ]
    return PresetResponse(**preset_dict)


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

    # Проверка прав: пользователь может редактировать только свои пресеты (или админ)
    if preset.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=403,
            detail="You can only update your own presets"
        )

    # Обновляем только переданные поля
    update_data = data.model_dump(exclude_unset=True)
    printer_ids = update_data.pop("printer_ids", None)
    
    for field, value in update_data.items():
        setattr(preset, field, value)
    
    # Обновляем связи с принтерами, если указаны
    if printer_ids is not None:
        # Удаляем старые связи
        delete_result = await db.execute(
            select(PresetPrinter).where(PresetPrinter.preset_id == preset_id)
        )
        old_links = delete_result.scalars().all()
        for link in old_links:
            await db.delete(link)
        
        # Создаём новые связи
        if printer_ids:
            for i, printer_id in enumerate(printer_ids):
                # Проверяем существование принтера
                printer_result = await db.execute(select(Printer).where(Printer.id == printer_id))
                printer = printer_result.scalar_one_or_none()
                if not printer:
                    continue  # Пропускаем несуществующие принтеры
                
                # Создаём связь
                preset_printer = PresetPrinter(
                    preset_id=preset.id,
                    printer_id=printer_id,
                    is_primary=(i == 0),  # Первый принтер - основной
                )
                db.add(preset_printer)

    await db.commit()
    
    # Загружаем принтеры для ответа
    result = await db.execute(
        select(Preset)
        .options(selectinload(Preset.printer_links).selectinload(PresetPrinter.printer))
        .where(Preset.id == preset_id)
    )
    preset_with_printers = result.scalar_one()

    return PresetResponse.model_validate(preset_with_printers)


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


@router.get("/{preset_id}/export/orcaslicer.json")
async def export_preset_json(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """
    Экспортировать профиль в формате OrcaSlicer (.json).
    
    Returns:
        JSONResponse: JSON файл профиля OrcaSlicer
    """
    # Получаем preset с filament и brand
    result = await db.execute(
        select(Preset)
        .options(selectinload(Preset.filament).selectinload(Filament.brand))
        .where(Preset.id == preset_id, Preset.active == True)
    )
    preset = result.scalar_one_or_none()
    
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    if not preset.filament:
        raise HTTPException(status_code=404, detail="Filament not found")
    
    # Экспортируем в JSON
    try:
        profile_dict = await preset_to_orcaslicer_json(preset, preset.filament, db)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error exporting preset {preset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exporting preset: {str(e)}")
    
    # Возвращаем JSON файл
    # Формируем безопасное имя файла (только латиница и безопасные символы для HTTP заголовков)
    brand_name = preset.filament.brand.name if preset.filament.brand else "Generic"
    
    # Формируем читабельное имя файла (OrcaSlicer поддерживает кириллицу, пробелы и спецсимволы)
    # Убираем только недопустимые символы для файловой системы: <>:"/\|?*
    def to_safe_filename(text: str) -> str:
        """Преобразует текст в безопасное имя файла, сохраняя кириллицу и пробелы."""
        if not text:
            return ""
        # Убираем только действительно недопустимые символы для файловой системы
        safe = text.replace("<", "_").replace(">", "_").replace(":", "_")
        safe = safe.replace('"', "_").replace("/", "_").replace("\\", "_")
        safe = safe.replace("|", "_").replace("?", "_").replace("*", "_")
        # Убираем множественные подчеркивания
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe.strip(" _")  # Убираем пробелы и подчеркивания в начале/конце
    
    # Формируем имя файла: используем имя пресета (OrcaSlicer поддерживает кириллицу, пробелы, спецсимволы)
    # Примеры из OrcaSlicer: "TEST-2 ABS.json", "ABS @FilamentHub2.json", "ABS HTP.json"
    if preset.name:
        filename = to_safe_filename(preset.name) + ".json"
    else:
        # Fallback: Brand Material.json или просто Material.json
        filename_parts = []
        if brand_name:
            filename_parts.append(to_safe_filename(brand_name))
        if preset.filament.material_type:
            filename_parts.append(to_safe_filename(preset.filament.material_type))
        
        if filename_parts:
            filename = " ".join(filename_parts) + ".json"
        else:
            filename = "preset.json"
    
    # Ограничиваем длину имени файла
    if len(filename) > 200:
        # Обрезаем до 200 символов, стараясь не резать по середине слова
        filename = filename[:197].rsplit(" ", 1)[0] + ".json"
    
    # Для HTTP заголовка используем RFC 5987 формат для поддержки Unicode
    from urllib.parse import quote
    
    # ASCII версия имени для совместимости
    ascii_filename = filename.encode('ascii', 'replace').decode('ascii').replace('?', '_')
    
    # Используем оба формата: ASCII для совместимости и UTF-8 для правильного отображения
    return JSONResponse(
        content=profile_dict,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{quote(filename, safe="")}',
        }
    )


@router.get("/{preset_id}/export/orcaslicer.info")
async def export_preset_info(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """
    Экспортировать .info файл в формате INI для OrcaSlicer.
    
    Returns:
        Response: .info файл профиля OrcaSlicer (INI формат)
    """
    from fastapi.responses import PlainTextResponse
    
    # Получаем preset с filament и brand
    result = await db.execute(
        select(Preset)
        .options(selectinload(Preset.filament).selectinload(Filament.brand))
        .where(Preset.id == preset_id, Preset.active == True)
    )
    preset = result.scalar_one_or_none()
    
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    if not preset.filament:
        raise HTTPException(status_code=404, detail="Filament not found")
    
    # Генерируем .info файл (INI формат)
    info_content = generate_profile_info(preset, preset.filament)
    
    # Возвращаем .info файл
    brand_name = preset.filament.brand.name if preset.filament.brand else "Generic"
    filename = f"{brand_name}_{preset.filament.material_type}_{preset.name}.info"
    filename = filename.replace(" ", "_").replace("/", "_")
    
    return PlainTextResponse(
        content=info_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
    )
