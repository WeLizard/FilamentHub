"""Preset endpoints."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
import json
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.core.dependencies import get_current_active_user, get_current_brand_user, get_current_active_user_optional
from app.core.utils import like_pattern
from app.core.errors import (
    ERR_EXPORT_MISSING_FIELDS,
    ERR_EXPORT_PRESET_ERROR,
    ERR_FILAMENT_NO_PRESETS,
    ERR_FILAMENT_NOT_FOUND,
    ERR_NO_PERMISSION_DELETE_PRESET,
    ERR_NO_PERMISSION_EDIT_PRESET,
    ERR_ONLY_BRAND_OFFICIAL,
    ERR_ONLY_OWN_BRAND_OFFICIAL,
    ERR_PRESET_NOT_FOUND,
    ERR_WEIGHTED_PRESET_NO_DELETE,
    ERR_WEIGHTED_PRESET_READONLY,
    raise_error,
)
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
from app.services.notification_service import notify_preset_deleted, notify_preset_updated
from app.services.preset_moderation import moderate_preset
from app.services.orcaslicer_exporter import export_preset_to_orcaslicer, generate_profile_info, preset_to_orcaslicer_json
from app.services.preset_recommender import get_recommended_preset_values
from app.services.weighted_preset_service import create_or_update_weighted_preset

router = APIRouter(prefix="/presets", tags=["presets"])


def _serialize_moderation_reason(reason: Any) -> str | None:
    if reason is None:
        return None
    if isinstance(reason, (dict, list)):
        return json.dumps(reason, ensure_ascii=False)
    return str(reason)


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
    search: str | None = Query(None, max_length=120),
    ids: str | None = Query(None, description="Comma-separated preset IDs to fetch"),
) -> PresetListResponse:
    """Получить список пресетов."""
    # Build query
    query = select(Preset).options(selectinload(Preset.printer_links).selectinload(PresetPrinter.printer))

    # Filter by explicit IDs (batch fetch, bypasses other filters)
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.where(Preset.id.in_(id_list))
            count_q = select(func.count()).select_from(Preset).where(Preset.id.in_(id_list))
            total_result = await db.execute(count_q)
            total = total_result.scalar_one()
            result = await db.execute(query.limit(len(id_list)))
            items = list(result.unique().scalars().all())
            responses = []
            for p in items:
                d = PresetResponse.model_validate(p).model_dump()
                d["printers"] = [
                    PrinterResponse.model_validate(link.printer).model_dump()
                    for link in p.printer_links
                ]
                responses.append(PresetResponse(**d))
            return PresetListResponse(items=responses, total=total, page=1, size=len(id_list))

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
    if search:
        query = query.where(Preset.name.ilike(like_pattern(search), escape="\\"))

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
    if search:
        count_query = count_query.where(Preset.name.ilike(like_pattern(search), escape="\\"))

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Pagination
    pages = (total + size - 1) // size
    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    # Execute query
    result = await db.execute(query)
    presets = result.scalars().unique().all()

    # Преобразуем пресеты в ответ с принтерами
    preset_responses = []
    for preset in presets:
        preset_dict = PresetResponse.model_validate(preset).model_dump()
        preset_dict["printers"] = [
            PrinterResponse.model_validate(link.printer).model_dump()
            for link in preset.printer_links
        ]
        preset_responses.append(PresetResponse(**preset_dict))

    return PresetListResponse(
        items=preset_responses,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{preset_id}", response_model=PresetResponse)
async def get_preset(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User | None = Depends(get_current_active_user_optional),
) -> PresetResponse:
    """Получить пресет по ID."""
    # Загружаем пресет БЕЗ printer_links (таблица может не существовать)
    result = await db.execute(
        select(Preset).where(Preset.id == preset_id)
    )
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    # Если пресет не активен и пользователь не является владельцем - не показываем
    if not preset.active:
        # Проверяем, является ли пользователь владельцем или сохраненным у него
        can_access = False
        if current_user:
            # Владелец пресета
            if preset.user_id == current_user.id:
                can_access = True
            # Или сохранен у пользователя
            else:
                from app.models.user_saved_preset import UserSavedPreset
                saved_check = await db.execute(
                    select(UserSavedPreset).where(
                        UserSavedPreset.user_id == current_user.id,
                        UserSavedPreset.preset_id == preset_id,
                    )
                )
                if saved_check.scalar_one_or_none():
                    can_access = True
        
        if not can_access:
            raise_error(404, ERR_PRESET_NOT_FOUND)

    # Если пресет не одобрен и пользователь не является владельцем - не показываем
    if preset.moderation_status != PresetModerationStatus.APPROVED and not preset.is_official:
        if current_user and preset.user_id != current_user.id:
            raise_error(404, ERR_PRESET_NOT_FOUND)

    # Преобразуем пресет в ответ (без printers, так как таблица может не существовать)
    preset_dict = PresetResponse.model_validate(preset).model_dump()
    preset_dict["printers"] = []  # Пустой массив, так как printer_links не загружаем
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
        raise_error(404, ERR_FILAMENT_NOT_FOUND)
    
    # Проверка прав на создание официального пресета
    if data.is_official:
        # Только пользователи, привязанные к бренду (или админы), могут создавать официальные пресеты
        if not current_user.brand_id and current_user.role.value != "admin":
            raise_error(403, ERR_ONLY_BRAND_OFFICIAL)
        # Проверяем, что filament принадлежит бренду пользователя (админы могут создавать для любого бренда)
        if current_user.brand_id and filament.brand_id != current_user.brand_id:
            raise_error(403, ERR_ONLY_OWN_BRAND_OFFICIAL)
    
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
    
    # Автоматическая модерация пресета (только для пользовательских пресетов)
    if not data.is_official:
        moderation_status, moderation_reason = await moderate_preset(
            preset,
            filament,
            db,
            is_official=False,
            allow_manual_review=False,
        )
        if moderation_status == PresetModerationStatus.REJECTED:
            # Не сохраняем пресет, возвращаем ошибку сразу
            raise HTTPException(
                status_code=400,
                detail=moderation_reason,  # structured {"code": "ERR_...", "params": {...}}
            )
        preset.moderation_status = moderation_status
        preset.moderation_reason = _serialize_moderation_reason(moderation_reason) if moderation_status == PresetModerationStatus.PENDING else None
    else:
        # Официальные пресеты автоматически одобряются
        preset.moderation_status = PresetModerationStatus.APPROVED
        preset.moderation_reason = None
    
    db.add(preset)
    await db.flush()  # Получаем ID пресета
    
    # Автоматически создаём запись в user_saved_presets (самосохранение)
    # Это нужно для единой логики синхронизации - все пресеты в "Профили филамента" хранят sync в user_saved_presets
    from app.models.user_saved_preset import UserSavedPreset
    saved_preset = UserSavedPreset(
        user_id=current_user.id,
        preset_id=preset.id,
        sync=True,  # По умолчанию синхронизация включена
    )
    db.add(saved_preset)
    
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
    
    # Обновляем взвешенный пресет для этого филамента (если достаточно пресетов)
    try:
        await create_or_update_weighted_preset(preset.filament_id, db, min_presets_count=4)
    except Exception as e:
        # Логируем ошибку, но не прерываем создание пресета
        logger.error(f"Failed to update weighted preset for filament {preset.filament_id}: {e}")
    
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
        raise_error(404, ERR_PRESET_NOT_FOUND)
    
    # Взвешенные пресеты нельзя редактировать (они автоматически обновляются системой)
    if preset.is_weighted:
        raise_error(403, ERR_WEIGHTED_PRESET_READONLY)

    # Проверка прав: пользователь может редактировать только свои пресеты (или админ)
    if preset.user_id != current_user.id and current_user.role.value != "admin":
        raise_error(403, ERR_NO_PERMISSION_EDIT_PRESET)

    # Обновляем только переданные поля
    update_data = data.model_dump(exclude_unset=True)
    printer_ids = update_data.pop("printer_ids", None)
    
    # Определяем filament_id: из update_data (если передан) или из preset
    # Для черновиков filament_id может быть None, и мы его обновляем через update_data
    target_filament_id = update_data.get("filament_id") or preset.filament_id
    
    # Получаем filament для автомодерации (только если есть filament_id)
    filament = None
    if target_filament_id:
        filament_result = await db.execute(select(Filament).where(Filament.id == target_filament_id))
        filament = filament_result.scalar_one_or_none()
        if not filament:
            raise_error(404, ERR_FILAMENT_NOT_FOUND)
    
    # Сохраняем старое состояние для проверки активации черновика.
    # sync больше управляется в user_saved_presets, поэтому здесь
    # учитываем только переход черновика в активный пресет.
    was_draft = not preset.active or not preset.filament_id
    
    for field, value in update_data.items():
        setattr(preset, field, value)
    
    # Логика замены меток при активации черновика:
    # если черновик стал активным и привязан к филаменту.
    if was_draft and preset.active and preset.filament_id:
        # Инициализируем orcaslicer_settings если его нет
        if preset.orcaslicer_settings is None:
            preset.orcaslicer_settings = {}
        elif not isinstance(preset.orcaslicer_settings, dict):
            preset.orcaslicer_settings = {}
        
        # Сохраняем derived-метки для предотвращения повторного создания черновиков:
        # При следующей синхронизации OrcaSlicer пришлёт тот же шаблон,
        # и мы должны распознать, что из него уже создан FH-пресет.
        old_draft_id = preset.orcaslicer_settings.get("fhub_draft_id")
        old_external_id = preset.external_id
        if old_external_id:
            preset.orcaslicer_settings["derived_from_external_id"] = old_external_id
        if old_draft_id:
            preset.orcaslicer_settings["derived_from_draft_id"] = old_draft_id

        # Убираем метку черновика, добавляем метки "нашего" пресета
        preset.orcaslicer_settings.pop("fhub_draft_id", None)
        preset.orcaslicer_settings["fhub_id"] = preset.id
        preset.orcaslicer_settings["fhub_source"] = "filamenthub"

        logger.info(
            f"Activated draft preset {preset.id}: removed fhub_draft_id={old_draft_id}, "
            f"saved derived_from_external_id={old_external_id}, derived_from_draft_id={old_draft_id}, "
            f"added fhub_id={preset.id} and fhub_source='filamenthub'"
        )
    
    # Автоматическая модерация при обновлении (только для пользовательских пресетов с filament)
    if not preset.is_official and filament:
        moderation_status, moderation_reason = await moderate_preset(
            preset,
            filament,
            db,
            is_official=preset.is_official,
            allow_manual_review=False,
        )
        # Если пресет был одобрен, а теперь отклонён - меняем статус
        if moderation_status == PresetModerationStatus.REJECTED:
            preset.moderation_status = moderation_status
            preset.moderation_reason = _serialize_moderation_reason(moderation_reason)
            preset.active = False
        # Требуется ручная проверка — переводим в pending и сохраняем причину/флаги.
        elif moderation_status == PresetModerationStatus.PENDING:
            preset.moderation_status = PresetModerationStatus.PENDING
            preset.moderation_reason = _serialize_moderation_reason(moderation_reason)
            if not preset.active:
                preset.active = True
        # Если пресет проходит проверку, а текущий статус не APPROVED
        # (например, PENDING после импорта из OrcaSlicer), переводим в APPROVED.
        elif moderation_status == PresetModerationStatus.APPROVED and preset.moderation_status != PresetModerationStatus.APPROVED:
            preset.moderation_status = moderation_status
            preset.moderation_reason = None
            # Для ранее отклонённых возвращаем активность.
            if not preset.active:
                preset.active = True
    
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
    
    # Обновляем взвешенный пресет для этого филамента (если достаточно пресетов и есть filament_id)
    if preset.filament_id:
        try:
            await create_or_update_weighted_preset(preset.filament_id, db, min_presets_count=4)
        except Exception as e:
            logger.error(f"Failed to update weighted preset for filament {preset.filament_id}: {e}")
        
        # Создаем уведомления для пользователей, у которых сохранен этот пресет
        try:
            await notify_preset_updated(
                preset_id=preset.id,
                preset_name=preset.name,
                filament_id=preset.filament_id,
                db=db,
            )
        except Exception as e:
            logger.error(f"Failed to create notifications for preset {preset.id} update: {e}")
    
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
        raise_error(404, ERR_PRESET_NOT_FOUND)
    
    # Взвешенные пресеты нельзя удалять (они автоматически управляются системой)
    if preset.is_weighted:
        raise_error(403, ERR_WEIGHTED_PRESET_NO_DELETE)

    # Проверка: пользователь может удалять только свои пресеты (или админ)
    if preset.user_id != current_user.id and current_user.role.value != "admin":
        raise_error(403, ERR_NO_PERMISSION_DELETE_PRESET)
    
    # Сохраняем данные перед удалением для уведомлений и обновления взвешенного пресета
    filament_id = preset.filament_id
    preset_name = preset.name
    preset_id_for_notification = preset.id

    await db.delete(preset)
    await db.commit()
    
    # Создаем уведомления для пользователей, у которых сохранен этот пресет
    try:
        await notify_preset_deleted(
            preset_id=preset_id_for_notification,
            preset_name=preset_name,
            filament_id=filament_id,
            db=db,
        )
    except Exception as e:
        logger.error(f"Failed to create notifications for preset {preset_id_for_notification} deletion: {e}")
    
    # Обновляем взвешенный пресет для этого филамента (если достаточно пресетов)
    try:
        await create_or_update_weighted_preset(filament_id, db, min_presets_count=4)
    except Exception as e:
        logger.error(f"Failed to update weighted preset for filament {filament_id}: {e}")


@router.post("/{preset_id}/increment-usage", response_model=PresetResponse)
async def increment_usage(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresetResponse:
    """Увеличить счётчик использования пресета."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    preset.usage_count += 1
    await db.commit()
    await db.refresh(preset)

    return PresetResponse.model_validate(preset)


@router.get("/{preset_id}/export/orcaslicer.json")
async def export_preset_json(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
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
        raise_error(404, ERR_PRESET_NOT_FOUND)
    
    if not preset.filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # EXPORT-6 fix: валидация обязательных полей перед экспортом → HTTP 422
    missing_fields = []
    if not preset.name:
        missing_fields.append("name")
    if not preset.filament.material_type:
        missing_fields.append("filament.material_type")
    if preset.extruder_temp is None:
        missing_fields.append("nozzle_temperature")
    if missing_fields:
        raise_error(422, ERR_EXPORT_MISSING_FIELDS, params={"fields": ", ".join(missing_fields)})

    # Экспортируем в JSON
    try:
        profile_dict = await preset_to_orcaslicer_json(preset, preset.filament, db)
    except Exception as e:
        logger.error(f"Error exporting preset {preset_id}: {str(e)}", exc_info=True)
        raise_error(500, ERR_EXPORT_PRESET_ERROR)
    
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
    current_user: Annotated[User, Depends(get_current_active_user)],
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
        raise_error(404, ERR_PRESET_NOT_FOUND)
    
    if not preset.filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # EXPORT-6 fix: валидация обязательных полей перед экспортом → HTTP 422
    missing_fields = []
    if not preset.name:
        missing_fields.append("name")
    if not preset.filament.material_type:
        missing_fields.append("filament.material_type")
    if missing_fields:
        raise_error(422, ERR_EXPORT_MISSING_FIELDS, params={"fields": ", ".join(missing_fields)})

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


@router.get("/recommended/{filament_id}", response_model=RecommendedPresetResponse)
async def get_recommended_preset(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecommendedPresetResponse:
    """Получить взвешенный пресет для материала (weighted average всех пресетов)."""
    try:
        recommended_values = await get_recommended_preset_values(filament_id, db)
        return RecommendedPresetResponse(
            filament_id=filament_id,
            **recommended_values
        )
    except ValueError:
        raise_error(404, ERR_FILAMENT_NO_PRESETS)
