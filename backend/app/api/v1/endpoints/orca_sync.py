"""Endpoints for OrcaSlicer synchronisation (printer & print profiles)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.notification import Notification, NotificationType
from app.models.preset import Preset, PresetModerationStatus
from app.models.print_profile import PrintProfile
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User, UserRole
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.orca_sync import (
    DeletedPresetAction,
    DeletedPresetActionResponse,
    DeletedPresetsRequest,
    DeletedPresetsResponse,
    FilamentPresetSyncRequest,
    FilamentPresetSyncResponse,
    OrcaSyncResult,
    PrintProfileSyncRequest,
    PrintProfileSyncResponse,
    PrinterProfileSyncRequest,
    PrinterProfileSyncResponse,
)
from app.schemas.print_profile import PrintProfileListResponse, PrintProfileResponse
from app.schemas.printer_profile import PrinterProfileListResponse, PrinterProfileResponse
from app.services.notification_service import create_notification
from app.services.orcaslicer_service import (
    get_user_deleted_preset_rule,
    is_preset_created_by_user,
    is_preset_saved_by_user,
    remove_saved_preset,
    save_user_deleted_preset_rule,
)
from app.services.preset_moderation import validate_text_field
from app.services.slug_service import generate_unique_slug

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orcaslicer", tags=["orcaslicer"])


def _normalize_for_match(value: str | None) -> str:
    """Нормализовать строку для сопоставления (lowercase, убрать лишние пробелы)."""
    if not value:
        return ""
    return " ".join(str(value).lower().strip().split())


async def _ensure_printer_id(
    *,
    db: AsyncSession,
    printer_id: int | None,
    printer_slug: str | None,
    profile_name: str | None = None,
    profile_metadata: dict[str, Any] | None = None,
    profile_settings: dict[str, Any] | None = None,
    profile_vendor: str | None = None,
) -> int | None:
    """
    Автоматическое сопоставление принтера с существующим в базе.
    
    Алгоритм поиска (в порядке приоритета):
    1. По printer_id (если указан явно)
    2. По printer_slug (если указан)
    3. По model_id из metadata/settings (самый надежный способ)
    4. По manufacturer + model (нормализованные)
    5. По vendor + name (нормализованные)
    6. По vendor + model из metadata (нормализованные)
    
    Если принтер не найден, создается новый на основе данных профиля.
    """
    # Объединяем все источники metadata
    combined_metadata = {}
    if profile_metadata:
        combined_metadata.update(profile_metadata)
    if profile_settings:
        combined_metadata.update(profile_settings)
    
    # 1. Поиск по явному printer_id
    if printer_id:
        printer = await db.get(Printer, printer_id)
        if printer:
            return printer.id
    
    # 2. Поиск по printer_slug
    if printer_slug:
        result = await db.execute(select(Printer).where(Printer.slug == printer_slug))
        printer = result.scalar_one_or_none()
        if printer:
            return printer.id
    
    # 3. Поиск по model_id (самый надежный способ сопоставления)
    model_id = combined_metadata.get("model_id") or combined_metadata.get("printer_model_id")
    if model_id:
        result = await db.execute(select(Printer).where(Printer.model_id == str(model_id)))
        printer = result.scalar_one_or_none()
        if printer:
            return printer.id
    
    # 4. Извлекаем данные для сопоставления
    vendor_name = (
        profile_vendor
        or combined_metadata.get("printer_vendor")
        or combined_metadata.get("vendor")
        or ""
    )
    printer_model = combined_metadata.get("printer_model") or ""
    
    # Пытаемся определить manufacturer и model из имени профиля
    name_parts = (profile_name or "").split()
    manufacturer_from_name = name_parts[0] if name_parts else ""
    model_from_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else (profile_name or "")
    
    # Используем данные из metadata, если есть, иначе из имени
    manufacturer = vendor_name or manufacturer_from_name or "Custom"
    model = printer_model or model_from_name or profile_name or "Unknown"
    
    # Нормализуем для сопоставления
    manufacturer_normalized = _normalize_for_match(manufacturer)
    model_normalized = _normalize_for_match(model)
    vendor_normalized = _normalize_for_match(vendor_name)
    name_normalized = _normalize_for_match(profile_name)
    
    # 5. Поиск по manufacturer + model (case-insensitive через SQL LIKE)
    if manufacturer_normalized and model_normalized:
        # Точное совпадение (case-insensitive)
        result = await db.execute(
            select(Printer).where(
                or_(
                    # Точное совпадение manufacturer + model (через ILIKE для PostgreSQL)
                    or_(
                        Printer.manufacturer.ilike(f"%{manufacturer}%"),
                        Printer.manufacturer.ilike(f"%{vendor_name}%"),
                    ),
                    Printer.model.ilike(f"%{model}%"),
                )
            )
        )
        printers = result.scalars().all()
        
        # Фильтруем в памяти для точного сопоставления (SQL не может нормализовать так же точно)
        for printer in printers:
            printer_manufacturer = _normalize_for_match(printer.manufacturer)
            printer_model_norm = _normalize_for_match(printer.model)
            
            # Точное совпадение manufacturer и model
            if (
                (printer_manufacturer == manufacturer_normalized or printer_manufacturer == vendor_normalized)
                and printer_model_norm == model_normalized
            ):
                return printer.id
            
            # Частичное совпадение (если manufacturer совпадает, а model содержит искомую модель)
            if (
                (printer_manufacturer == manufacturer_normalized or printer_manufacturer == vendor_normalized)
                and model_normalized in printer_model_norm
            ):
                return printer.id
    
    # 6. Поиск по vendor + name (нормализованные)
    if vendor_normalized and name_normalized:
        result = await db.execute(
            select(Printer).where(
                Printer.vendor.ilike(f"%{vendor_name}%"),
                Printer.name.ilike(f"%{profile_name}%"),
            )
        )
        printers = result.scalars().all()
        
        for printer in printers:
            printer_vendor = _normalize_for_match(printer.vendor)
            printer_name = _normalize_for_match(printer.name)
            
            if printer_vendor == vendor_normalized and printer_name == name_normalized:
                return printer.id
    
    # 7. Поиск по vendor + model из metadata
    if vendor_normalized and model_normalized:
        result = await db.execute(
            select(Printer).where(
                Printer.vendor.ilike(f"%{vendor_name}%"),
                Printer.model.ilike(f"%{model}%"),
            )
        )
        printers = result.scalars().all()
        
        for printer in printers:
            printer_vendor = _normalize_for_match(printer.vendor)
            printer_model_norm = _normalize_for_match(printer.model)
            
            if printer_vendor == vendor_normalized and printer_model_norm == model_normalized:
                return printer.id
    
    # Принтер не найден - создаем новый
    if profile_name:
        from app.services.slug_service import generate_unique_slug
        
        # Используем printer_slug если есть, иначе генерируем
        final_slug = printer_slug
        if not final_slug:
            slug_source = f"{manufacturer} {model}".strip()
            final_slug = await generate_unique_slug(
                db=db,
                model=Printer,
                source=slug_source,
                fallback="printer",
            )
        
        printer = Printer(
            name=profile_name,
            manufacturer=manufacturer,
            model=model,
            slug=final_slug,
            source="user",
            vendor=vendor_name or None,
            model_id=model_id or None,
            extra_metadata=combined_metadata if combined_metadata else None,
            active=True,
        )
        db.add(printer)
        await db.flush()
        return printer.id
    
    return None


def _merge_extra_metadata(
    metadata: dict[str, Any] | None,
    condition: str | None,
) -> dict[str, Any] | None:
    """Merge metadata dict with compatibility condition, returning None if empty."""
    merged: dict[str, Any] = dict(metadata or {})
    if condition:
        merged["compatible_printers_condition"] = condition
    return merged or None


async def _upsert_printer_profile(
    *,
    payload,
    current_user: User,
    db: AsyncSession,
) -> OrcaSyncResult:
    from app.schemas.orca_sync import OrcaPrinterProfilePayload

    if not isinstance(payload, OrcaPrinterProfilePayload):
        raise ValueError("Invalid payload type for printer profile import")

    is_valid, error_msg = await validate_text_field(payload.name, db, "Название профиля принтера")
    if not is_valid:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=payload.fhub_id,
            status="error",
            message=error_msg,
        )

    for field_value, label in [
        (payload.description, "Описание профиля принтера"),
        (payload.notes, "Заметки к профилю принтера"),
    ]:
        if field_value:
            is_valid, error_msg = await validate_text_field(field_value, db, label)
            if not is_valid:
                return OrcaSyncResult(
                    external_id=payload.external_id,
                    fhub_id=payload.fhub_id,
                    status="error",
                    message=error_msg,
                )

    profile: PrinterProfile | None = None
    if payload.fhub_id:
        profile = await db.get(PrinterProfile, payload.fhub_id)
        if profile is None:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=payload.fhub_id,
                status="error",
                message="Printer profile not found in FilamentHub",
            )
    elif payload.slug:
        result = await db.execute(
            select(PrinterProfile).where(
                PrinterProfile.slug == payload.slug,
                PrinterProfile.owner_user_id == current_user.id,
            )
        )
        profile = result.scalar_one_or_none()

    printer_id = await _ensure_printer_id(
        db=db,
        printer_id=payload.printer_id,
        printer_slug=payload.printer_slug,
        profile_name=payload.name,
        profile_metadata=payload.extra_metadata,
        profile_settings=payload.orcaslicer_settings,
        profile_vendor=payload.vendor,
    )

    if profile:
        if profile.owner_user_id not in (None, current_user.id) and current_user.role != UserRole.ADMIN:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=profile.id,
                status="skipped",
                message="Недостаточно прав для обновления профиля",
            )

        if payload.slug and payload.slug != profile.slug:
            profile.slug = await generate_unique_slug(
                db=db,
                model=PrinterProfile,
                source=payload.slug,
                fallback=f"printer-profile-{current_user.id}",
                exclude_id=profile.id,
            )

        profile.name = payload.name
        profile.description = payload.description
        profile.printer_id = printer_id
        profile.owner_user_id = profile.owner_user_id or current_user.id
        profile.active = payload.active if payload.active is not None else profile.active
        profile.source = payload.source or profile.source
        profile.vendor = payload.vendor or profile.vendor
        profile.setting_id = payload.setting_id or profile.setting_id
        profile.external_id = payload.external_id or profile.external_id
        profile.default_print_profile_slug = (
            payload.default_print_profile_slug or profile.default_print_profile_slug
        )
        if payload.nozzle_diameters is not None:
            profile.nozzle_diameters = payload.nozzle_diameters
        if payload.printable_area is not None:
            profile.printable_area = payload.printable_area
        if payload.printable_height_mm is not None:
            profile.printable_height_mm = payload.printable_height_mm
        if payload.extra_metadata:
            profile.extra_metadata = payload.extra_metadata
        profile.orcaslicer_settings = payload.orcaslicer_settings or {}
        profile.start_gcode = payload.start_gcode
        profile.end_gcode = payload.end_gcode
        profile.notes = payload.notes
        profile.is_official = profile.is_official if current_user.role != UserRole.ADMIN else profile.is_official

        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=profile.id,
            status="updated",
            message="Profile updated",
        )

    slug_source = payload.slug or payload.name
    slug = await generate_unique_slug(
        db=db,
        model=PrinterProfile,
        source=slug_source,
        fallback=f"printer-profile-{current_user.id}",
    )

    profile = PrinterProfile(
        name=payload.name,
        slug=slug,
        description=payload.description,
        printer_id=printer_id,
        owner_user_id=current_user.id,
        is_official=False,
        active=payload.active if payload.active is not None else False,
        source=payload.source or "system",
        vendor=payload.vendor,
        setting_id=payload.setting_id,
        external_id=payload.external_id,
        default_print_profile_slug=payload.default_print_profile_slug,
        nozzle_diameters=payload.nozzle_diameters,
        printable_area=payload.printable_area,
        printable_height_mm=payload.printable_height_mm,
        extra_metadata=payload.extra_metadata,
        orcaslicer_settings=payload.orcaslicer_settings or {},
        start_gcode=payload.start_gcode,
        end_gcode=payload.end_gcode,
        notes=payload.notes,
    )
    db.add(profile)
    await db.flush()

    return OrcaSyncResult(
        external_id=payload.external_id,
        fhub_id=profile.id,
        status="created",
        message="Profile created",
    )


async def _upsert_print_profile(
    *,
    payload,
    current_user: User,
    db: AsyncSession,
) -> OrcaSyncResult:
    from app.schemas.orca_sync import OrcaPrintProfilePayload

    if not isinstance(payload, OrcaPrintProfilePayload):
        raise ValueError("Invalid payload type for print profile import")

    is_valid, error_msg = await validate_text_field(payload.name, db, "Название профиля печати")
    if not is_valid:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=payload.fhub_id,
            status="error",
            message=error_msg,
        )

    for field_value, label in [
        (payload.description, "Описание профиля печати"),
        (payload.notes, "Заметки к профилю печати"),
    ]:
        if field_value:
            is_valid, error_msg = await validate_text_field(field_value, db, label)
            if not is_valid:
                return OrcaSyncResult(
                    external_id=payload.external_id,
                    fhub_id=payload.fhub_id,
                    status="error",
                    message=error_msg,
                )

    profile: PrintProfile | None = None
    if payload.fhub_id:
        profile = await db.get(PrintProfile, payload.fhub_id)
        if profile is None:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=payload.fhub_id,
                status="error",
                message="Print profile not found in FilamentHub",
            )
    elif payload.slug:
        result = await db.execute(
            select(PrintProfile).where(
                PrintProfile.slug == payload.slug,
                PrintProfile.owner_user_id == current_user.id,
            )
        )
        profile = result.scalar_one_or_none()

    compatible_printers = (
        [str(item) for item in payload.compatible_printers] if payload.compatible_printers else None
    )
    compatible_filaments = (
        [str(item) for item in payload.compatible_filaments] if payload.compatible_filaments else None
    )

    if profile:
        if profile.owner_user_id not in (None, current_user.id) and current_user.role != UserRole.ADMIN:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=profile.id,
                status="skipped",
                message="Недостаточно прав для обновления профиля",
            )

        if payload.slug and payload.slug != profile.slug:
            profile.slug = await generate_unique_slug(
                db=db,
                model=PrintProfile,
                source=payload.slug,
                fallback=f"print-profile-{current_user.id}",
                exclude_id=profile.id,
            )

        profile.name = payload.name
        profile.description = payload.description
        profile.category = payload.category
        profile.owner_user_id = profile.owner_user_id or current_user.id
        profile.active = payload.active if payload.active is not None else profile.active
        profile.source = payload.source or profile.source
        profile.vendor = payload.vendor or profile.vendor
        profile.setting_id = payload.setting_id or profile.setting_id
        profile.external_id = payload.external_id or profile.external_id
        profile.quality_tier = payload.quality_tier or profile.quality_tier
        profile.default_nozzle = payload.default_nozzle or profile.default_nozzle
        if payload.layer_height_mm is not None:
            profile.layer_height_mm = payload.layer_height_mm
        profile.compatible_printers = compatible_printers
        profile.compatible_filaments = compatible_filaments
        profile.orcaslicer_settings = payload.orcaslicer_settings or {}
        if payload.extra_metadata:
            profile.extra_metadata = payload.extra_metadata
        if payload.compatible_printers_condition:
            extra = dict(profile.extra_metadata or {})
            extra["compatible_printers_condition"] = payload.compatible_printers_condition
            profile.extra_metadata = extra
        profile.notes = payload.notes
        profile.is_official = profile.is_official if current_user.role != UserRole.ADMIN else profile.is_official

        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=profile.id,
            status="updated",
            message="Profile updated",
        )

    slug_source = payload.slug or payload.name
    slug = await generate_unique_slug(
        db=db,
        model=PrintProfile,
        source=slug_source,
        fallback=f"print-profile-{current_user.id}",
    )

    profile = PrintProfile(
        name=payload.name,
        slug=slug,
        description=payload.description,
        category=payload.category,
        owner_user_id=current_user.id,
        is_official=False,
        active=payload.active if payload.active is not None else False,
        source=payload.source or "system",
        vendor=payload.vendor,
        external_id=payload.external_id,
        setting_id=payload.setting_id,
        quality_tier=payload.quality_tier,
        default_nozzle=payload.default_nozzle,
        layer_height_mm=payload.layer_height_mm,
        compatible_printers=compatible_printers,
        compatible_filaments=compatible_filaments,
        orcaslicer_settings=payload.orcaslicer_settings or {},
        extra_metadata=_merge_extra_metadata(payload.extra_metadata, payload.compatible_printers_condition),
        notes=payload.notes,
    )
    db.add(profile)
    await db.flush()

    return OrcaSyncResult(
        external_id=payload.external_id,
        fhub_id=profile.id,
        status="created",
        message="Profile created",
    )


@router.get("/printer-profiles", response_model=PrinterProfileListResponse)
async def list_printer_profiles_for_sync(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    updated_since: datetime | None = Query(
        default=None,
        description="Возвращать только профили, обновленные после указанной даты (ISO 8601).",
    ),
    include_official: bool = Query(
        default=True,
        description="Включить официальные профили FilamentHub в выдачу.",
    ),
) -> PrinterProfileListResponse:
    """Return printer profiles for OrcaSlicer synchronisation."""
    # Проверяем разрешение на экспорт профилей принтера
    if not current_user.allow_printer_profiles_export:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Экспорт профилей принтера отключен в настройках пользователя",
        )
    
    query = select(PrinterProfile)
    if include_official:
        query = query.where(
            or_(
                PrinterProfile.owner_user_id == current_user.id,
                PrinterProfile.is_official.is_(True),
            )
        )
    else:
        query = query.where(PrinterProfile.owner_user_id == current_user.id)

    if updated_since:
        query = query.where(PrinterProfile.updated_at >= updated_since)

    query = query.order_by(PrinterProfile.updated_at.desc())
    result = await db.execute(query)
    profiles = result.scalars().all()

    items = [PrinterProfileResponse.model_validate(profile) for profile in profiles]
    total = len(items)

    return PrinterProfileListResponse(
        items=items,
        total=total,
        page=1,
        size=total,
        pages=1,
    )


@router.get("/print-profiles", response_model=PrintProfileListResponse)
async def list_print_profiles_for_sync(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    updated_since: datetime | None = Query(
        default=None,
        description="Возвращать только профили, обновленные после указанной даты (ISO 8601).",
    ),
    include_official: bool = Query(
        default=True,
        description="Включить официальные профили FilamentHub в выдачу.",
    ),
) -> PrintProfileListResponse:
    """Return print profiles for OrcaSlicer synchronisation."""
    # Проверяем разрешение на экспорт профилей печати
    if not current_user.allow_print_profiles_export:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Экспорт профилей печати отключен в настройках пользователя",
        )
    
    query = select(PrintProfile)
    if include_official:
        query = query.where(
            or_(
                PrintProfile.owner_user_id == current_user.id,
                PrintProfile.is_official.is_(True),
            )
        )
    else:
        query = query.where(PrintProfile.owner_user_id == current_user.id)

    if updated_since:
        query = query.where(PrintProfile.updated_at >= updated_since)

    query = query.order_by(PrintProfile.updated_at.desc())
    result = await db.execute(query)
    profiles = result.scalars().all()

    items = [PrintProfileResponse.model_validate(profile) for profile in profiles]
    total = len(items)

    return PrintProfileListResponse(
        items=items,
        total=total,
        page=1,
        size=total,
        pages=1,
    )


@router.post(
    "/printer-profiles/import",
    response_model=PrinterProfileSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def import_printer_profiles(
    payload: PrinterProfileSyncRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterProfileSyncResponse:
    """Import or update printer profiles submitted by OrcaSlicer."""
    # Проверяем разрешение на импорт профилей принтера
    if not current_user.allow_printer_profiles_import:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Импорт профилей принтера отключен в настройках пользователя",
        )
    
    results: list[OrcaSyncResult] = []

    for item in payload.profiles:
        try:
            result = await _upsert_printer_profile(
                payload=item,
                current_user=current_user,
                db=db,
            )
        except HTTPException as exc:
            logger.warning("Failed to sync printer profile: %s", exc.detail)
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=exc.detail,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while syncing printer profile")
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=f"Unexpected error: {exc}",
            )
        results.append(result)

    await db.commit()
    return PrinterProfileSyncResponse(results=results)


@router.post(
    "/print-profiles/import",
    response_model=PrintProfileSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def import_print_profiles(
    payload: PrintProfileSyncRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintProfileSyncResponse:
    """Import or update print profiles submitted by OrcaSlicer."""
    # Проверяем разрешение на импорт профилей печати
    if not current_user.allow_print_profiles_import:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Импорт профилей печати отключен в настройках пользователя",
        )
    
    results: list[OrcaSyncResult] = []

    for item in payload.profiles:
        try:
            result = await _upsert_print_profile(
                payload=item,
                current_user=current_user,
                db=db,
            )
        except HTTPException as exc:
            logger.warning("Failed to sync print profile: %s", exc.detail)
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=exc.detail,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while syncing print profile")
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=f"Unexpected error: {exc}",
            )
        results.append(result)

    await db.commit()
    return PrintProfileSyncResponse(results=results)


async def _upsert_filament_preset(
    *,
    payload,
    current_user: User,
    db: AsyncSession,
) -> OrcaSyncResult:
    """Создать или обновить Filament Preset из OrcaSlicer."""
    from app.schemas.orca_sync import OrcaFilamentPresetPayload

    if not isinstance(payload, OrcaFilamentPresetPayload):
        raise ValueError("Invalid payload type for filament preset import")

    # Валидация текстовых полей
    is_valid, error_msg = await validate_text_field(payload.name, db, "Название пресета")
    if not is_valid:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=payload.fhub_id,
            status="error",
            message=error_msg,
        )

    for field_value, label in [
        (payload.description, "Описание пресета"),
        (payload.notes, "Заметки к пресету"),
        (payload.filament_name, "Название материала"),
    ]:
        if field_value:
            is_valid, error_msg = await validate_text_field(field_value, db, label)
            if not is_valid:
                return OrcaSyncResult(
                    external_id=payload.external_id,
                    fhub_id=payload.fhub_id,
                    status="error",
                    message=error_msg,
                )

    # Служебный бренд "User Materials" (id=1) для черновиков
    USER_MATERIALS_BRAND_ID = 1

    # 1. Найти или создать Filament (черновик)
    filament: Filament | None = None
    if payload.filament_id:
        filament = await db.get(Filament, payload.filament_id)
        if filament is None:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=payload.fhub_id,
                status="error",
                message="Filament not found in FilamentHub",
            )
        # Проверяем права доступа
        if (
            filament.brand_id != USER_MATERIALS_BRAND_ID
            and current_user.brand_id != filament.brand_id
            and current_user.role != UserRole.ADMIN
        ):
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=payload.fhub_id,
                status="error",
                message="Недостаточно прав для доступа к этому материалу",
            )
    elif payload.filament_name:
        # Ищем по имени в служебном бренде (несколько пользователей могут иметь Filament с одинаковым именем)
        result = await db.execute(
            select(Filament).where(
                Filament.name == payload.filament_name,
                Filament.brand_id == USER_MATERIALS_BRAND_ID,
            )
        )
        filament = result.scalar_one_or_none()

    if not filament:
        # Создаем новый Filament (черновик) в служебном бренде
        # Проверяем, что служебный бренд существует
        brand = await db.get(Brand, USER_MATERIALS_BRAND_ID)
        if brand is None:
            logger.error("User Materials brand (id=1) not found in database")
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=payload.fhub_id,
                status="error",
                message="User Materials brand not found. Please run database migrations.",
            )

        filament_name = payload.filament_name or f"Imported from OrcaSlicer"
        material_type = payload.material_type or "PLA"

        # Генерируем уникальный slug для Filament
        filament_slug_source = filament_name
        filament_slug = await generate_unique_slug(
            db=db,
            model=Filament,
            source=filament_slug_source,
            fallback=f"filament-{current_user.id}-{int(datetime.now(timezone.utc).timestamp())}",
        )

        filament = Filament(
            name=filament_name,
            slug=filament_slug,
            material_type=material_type,
            brand_id=USER_MATERIALS_BRAND_ID,  # Служебный бренд "User Materials" (id=1)
            diameter=1.75,  # По умолчанию
            active=False,  # Черновик - пользователь может активировать и привязать к своему бренду через UI
        )
        db.add(filament)
        await db.flush()  # Получаем ID филамента

        logger.info(
            f"Created draft Filament (id={filament.id}, name='{filament_name}') "
            f"for user {current_user.id}. User can activate and assign to their brand via UI."
        )

    # 2. Найти или создать Preset
    preset: Preset | None = None
    if payload.fhub_id:
        preset = await db.get(Preset, payload.fhub_id)
        if preset is None:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=payload.fhub_id,
                status="error",
                message="Preset not found in FilamentHub",
            )
        # Проверяем права доступа
        if (
            preset.user_id != current_user.id
            and current_user.role != UserRole.ADMIN
        ):
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=payload.fhub_id,
                status="error",
                message="Недостаточно прав для обновления этого пресета",
            )
    elif payload.external_id:
        # Ищем по external_id
        result = await db.execute(
            select(Preset).where(
                Preset.external_id == payload.external_id,
                Preset.user_id == current_user.id,
            )
        )
        preset = result.scalar_one_or_none()

    if preset:
        # Обновляем существующий пресет
        # Проверяем конфликты (timestamp-based resolution)
        # Если payload.updated_at не передан, обновляем всегда (для обратной совместимости)
        # Если передан, обновляем только если версия из OrcaSlicer новее
        should_update = True
        if payload.orcaslicer_settings and preset.orcaslicer_settings:
            # Если есть updated_at в orcaslicer_settings, проверяем его
            payload_updated_at = payload.orcaslicer_settings.get("updated_at")
            preset_updated_at = preset.orcaslicer_settings.get("updated_at")
            if payload_updated_at and preset_updated_at:
                # Сравниваем timestamps
                try:
                    from datetime import datetime as dt
                    payload_dt = dt.fromisoformat(payload_updated_at.replace("Z", "+00:00"))
                    preset_dt = dt.fromisoformat(preset_updated_at.replace("Z", "+00:00"))
                    if preset_dt > payload_dt:
                        # FilamentHub версия новее - не обновляем
                        should_update = False
                        logger.info(
                            f"Preset {preset.id} not updated: FilamentHub version is newer "
                            f"(FilamentHub: {preset_dt}, OrcaSlicer: {payload_dt})"
                        )
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Failed to parse updated_at timestamps: {e}")
                    # Если не удалось распарсить, обновляем (для безопасности)

        if should_update:
            preset.name = payload.name
            if payload.description is not None:
                preset.description = payload.description
            if payload.extruder_temp is not None:
                preset.extruder_temp = payload.extruder_temp
            if payload.bed_temp is not None:
                preset.bed_temp = payload.bed_temp
            if payload.print_speed is not None:
                preset.print_speed = payload.print_speed
            if payload.travel_speed is not None:
                preset.travel_speed = payload.travel_speed
            if payload.layer_height is not None:
                preset.layer_height = payload.layer_height
            if payload.first_layer_height is not None:
                preset.first_layer_height = payload.first_layer_height
            if payload.flow_rate is not None:
                preset.flow_rate = payload.flow_rate
            if payload.fan_speed is not None:
                preset.fan_speed = payload.fan_speed
            if payload.retraction_length is not None:
                preset.retraction_length = payload.retraction_length
            if payload.retraction_speed is not None:
                preset.retraction_speed = payload.retraction_speed
            if payload.orcaslicer_settings:
                preset.orcaslicer_settings = payload.orcaslicer_settings
            if payload.notes is not None:
                preset.notes = payload.notes
            if payload.source:
                preset.source = payload.source
            if payload.external_id:
                preset.external_id = payload.external_id
            # Обновляем updated_at вручную, чтобы отметить, что пресет был изменен
            preset.updated_at = datetime.now(timezone.utc)

            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=preset.id,
                status="updated",
                message="Preset updated",
            )
        else:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=preset.id,
                status="skipped",
                message="Preset not updated: FilamentHub version is newer",
            )
    else:
        # Создаем новый пресет (черновик)
        # Примечание: Preset не имеет поля slug (только Filament имеет slug)

        # Значения по умолчанию
        extruder_temp = payload.extruder_temp or 210.0
        bed_temp = payload.bed_temp or 60.0
        print_speed = payload.print_speed or 80.0
        travel_speed = payload.travel_speed or 150.0

        preset = Preset(
            name=payload.name,
            description=payload.description,
            filament_id=filament.id,
            user_id=current_user.id,
            extruder_temp=extruder_temp,
            bed_temp=bed_temp,
            print_speed=print_speed,
            travel_speed=travel_speed,
            layer_height=payload.layer_height,
            first_layer_height=payload.first_layer_height,
            flow_rate=payload.flow_rate,
            fan_speed=payload.fan_speed,
            retraction_length=payload.retraction_length,
            retraction_speed=payload.retraction_speed,
            orcaslicer_settings=payload.orcaslicer_settings or {},
            is_official=False,
            active=payload.active if payload.active is not None else False,  # Черновик
            moderation_status=PresetModerationStatus.PENDING,
            source=payload.source or "orcaslicer",
            external_id=payload.external_id,
            sync_enabled=True,  # По умолчанию синхронизация включена для новых пресетов
            # Примечание: Preset не имеет поля notes
        )
        db.add(preset)
        await db.flush()  # Получаем ID пресета

        logger.info(
            f"Created draft Preset (id={preset.id}, name='{payload.name}') "
            f"for user {current_user.id}. Filament: {filament.name} (id={filament.id})"
        )

        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=preset.id,
            status="created",
            message="Preset created as draft",
        )


@router.post(
    "/filaments/import",
    response_model=FilamentPresetSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def import_filament_presets(
    payload: FilamentPresetSyncRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentPresetSyncResponse:
    """Import or update filament presets submitted by OrcaSlicer."""
    # Проверяем разрешение на импорт filament presets
    if not current_user.allow_filament_presets_import:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Импорт пресетов филаментов отключен в настройках пользователя",
        )

    # Лимит на количество профилей (50 для MVP)
    MAX_PROFILES_PER_REQUEST = 50
    if len(payload.profiles) > MAX_PROFILES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many profiles: {len(payload.profiles)} (max {MAX_PROFILES_PER_REQUEST})",
        )

    results: list[OrcaSyncResult] = []

    for item in payload.profiles:
        try:
            result = await _upsert_filament_preset(
                payload=item,
                current_user=current_user,
                db=db,
            )
        except HTTPException as exc:
            logger.warning("Failed to sync filament preset: %s", exc.detail)
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=exc.detail,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while syncing filament preset")
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=f"Unexpected error: {exc}",
            )
        results.append(result)

    await db.commit()
    return FilamentPresetSyncResponse(results=results)


@router.post("/deleted-presets", response_model=DeletedPresetsResponse, status_code=status.HTTP_200_OK)
async def report_deleted_presets(
    request: DeletedPresetsRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeletedPresetsResponse:
    """Сообщить бэкенду об удалённых пресетах в OrcaSlicer."""
    if not request.deleted_presets:
        return DeletedPresetsResponse(message="No deleted presets to report")

    # Разделяем пресеты на созданные и сохранённые
    created_preset_ids = []
    saved_preset_ids = []

    for preset_data in request.deleted_presets:
        preset_id = preset_data.preset_id

        # Проверяем, создан ли пресет пользователем
        if await is_preset_created_by_user(current_user.id, preset_id, db):
            created_preset_ids.append(preset_id)
        elif await is_preset_saved_by_user(current_user.id, preset_id, db):
            # Пресет сохранён пользователем (из каталога)
            saved_preset_ids.append(preset_id)

    # Создаём уведомление
    preset_count = len(request.deleted_presets)
    title = f"Обнаружено {preset_count} удалённых пресетов"
    message = (
        f"В OrcaSlicer обнаружено {preset_count} пресетов, которые были удалены локально, "
        "но остаются в FilamentHub."
    )

    # Сохраняем список пресетов в extra_data с указанием типа
    extra_data = {
        "deleted_presets": [
            {
                "preset_id": preset.preset_id,
                "preset_name": preset.preset_name,
                "bundle_preset_name": preset.bundle_preset_name,
                "is_created": preset.preset_id in created_preset_ids,  # Создан пользователем
                "is_saved": preset.preset_id in saved_preset_ids,  # Сохранён пользователем
            }
            for preset in request.deleted_presets
        ],
        "created_count": len(created_preset_ids),
        "saved_count": len(saved_preset_ids),
    }

    # Проверяем правила пользователя
    user_rule = await get_user_deleted_preset_rule(current_user.id, db)

    # Если правило "always_restore" или "always_delete", применяем автоматически
    if user_rule == "always_restore":
        # Восстанавливаем все пресеты (удаляем маппинг, OrcaSlicer переимпортирует)
        # Уведомление не создаём, просто удаляем маппинг
        return DeletedPresetsResponse(
            message="All presets will be restored automatically",
            rule=user_rule,
            preset_count=preset_count,
            created_count=len(created_preset_ids),
            saved_count=len(saved_preset_ids),
        )

    elif user_rule == "always_delete":
        # Удаляем сохранённые пресеты из "Профили филамента"
        # Созданные пресеты не трогаем
        for preset_id in saved_preset_ids:
            await remove_saved_preset(current_user.id, preset_id, db)

        await db.commit()

        # Уведомление не создаём
        return DeletedPresetsResponse(
            message="Saved presets removed automatically",
            rule=user_rule,
            preset_count=preset_count,
            created_count=len(created_preset_ids),
            saved_count=len(saved_preset_ids),
        )

    # Если правило "always_ask" или другое, проверяем, есть ли уже необработанное уведомление
    # Если есть - обновляем его, если нет - создаём новое
    existing_notification_result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.type == NotificationType.PRESET_LOCALLY_DELETED,
            Notification.read.is_(False),
        ).order_by(Notification.created_at.desc())
    )
    existing_notification = existing_notification_result.scalar_one_or_none()

    if existing_notification:
        # Обновляем существующее уведомление
        # Объединяем списки пресетов, избегая дубликатов
        existing_preset_ids = {p["preset_id"] for p in existing_notification.extra_data.get("deleted_presets", [])}
        
        # Добавляем только новые пресеты (которых еще нет в существующем уведомлении)
        new_presets = [
            {
                "preset_id": preset.preset_id,
                "preset_name": preset.preset_name,
                "bundle_preset_name": preset.bundle_preset_name,
                "is_created": preset.preset_id in created_preset_ids,
                "is_saved": preset.preset_id in saved_preset_ids,
            }
            for preset in request.deleted_presets
            if preset.preset_id not in existing_preset_ids
        ]
        
        if new_presets:
            # Обновляем extra_data, добавляя новые пресеты
            all_presets = existing_notification.extra_data.get("deleted_presets", []) + new_presets
            existing_notification.extra_data = {
                "deleted_presets": all_presets,
                "created_count": sum(1 for p in all_presets if p.get("is_created", False)),
                "saved_count": sum(1 for p in all_presets if p.get("is_saved", False)),
            }
            existing_notification.title = f"Обнаружено {len(all_presets)} удалённых пресетов"
            existing_notification.message = (
                f"В OrcaSlicer обнаружено {len(all_presets)} пресетов, которые были удалены локально, "
                "но остаются в FilamentHub."
            )
            await db.commit()
            await db.refresh(existing_notification)
            notification = existing_notification
        else:
            # Все пресеты уже есть в уведомлении - ничего не делаем
            notification = existing_notification
    else:
        # Создаём новое уведомление
        notification = await create_notification(
            user_id=current_user.id,
            notification_type=NotificationType.PRESET_LOCALLY_DELETED,
            title=title,
            message=message,
            db=db,
            link=None,  # Не переходим по ссылке, открываем модалку
            extra_data=extra_data,
        )

    return DeletedPresetsResponse(
        message="Notification created",
        notification_id=notification.id,
        preset_count=preset_count,
        created_count=len(created_preset_ids),
        saved_count=len(saved_preset_ids),
    )


@router.post(
    "/deleted-presets/{notification_id}/action",
    response_model=DeletedPresetActionResponse,
    status_code=status.HTTP_200_OK,
)
async def handle_deleted_preset_action(
    notification_id: int,
    action: DeletedPresetAction,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeletedPresetActionResponse:
    """Обработать действие пользователя для удалённого пресета."""
    # Получаем уведомление
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
            Notification.type == NotificationType.PRESET_LOCALLY_DELETED,
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    # Получаем список удалённых пресетов из extra_data
    if not notification.extra_data:
        raise HTTPException(status_code=400, detail="Notification has no extra_data")
    deleted_presets = notification.extra_data.get("deleted_presets", [])

    # Фильтруем пресеты по выбранным preset_ids (если apply_to_all=False)
    if action.preset_ids:
        deleted_presets = [p for p in deleted_presets if p["preset_id"] in action.preset_ids]
    elif not action.apply_to_all:
        # Если не указаны preset_ids и не apply_to_all, возвращаем ошибку
        raise HTTPException(status_code=400, detail="preset_ids or apply_to_all required")

    processed_count = 0

    if action.action == "restore":
        # Восстанавливаем пресеты (удаляем маппинг, OrcaSlicer переимпортирует при следующей синхронизации)
        # Маппинг удаляется на стороне OrcaSlicer (C++), бэкенд просто подтверждает действие
        processed_count = len(deleted_presets)

    elif action.action == "delete":
        # Удаляем пресеты из "Профили филамента"
        for preset_data in deleted_presets:
            preset_id = preset_data["preset_id"]
            is_created = preset_data.get("is_created", False)
            is_saved = preset_data.get("is_saved", False)

            if is_created:
                # Пресет создан пользователем - НЕ удаляем из FilamentHub
                # Просто пропускаем
                continue
            elif is_saved:
                # Пресет сохранён пользователем - удаляем из "Профили филамента" (убираем из избранного)
                await remove_saved_preset(current_user.id, preset_id, db)
                processed_count += 1

    elif action.action == "skip":
        # Пропускаем (отключаем синхронизацию, но НЕ удаляем маппинг)
        # Устанавливаем sync_enabled=False в user_saved_presets для пресетов пользователя
        from app.models.user_saved_preset import UserSavedPreset
        for preset_data in deleted_presets:
            preset_id = preset_data["preset_id"]
            # Находим запись в user_saved_presets для этого пользователя и пресета
            result = await db.execute(
                select(UserSavedPreset).where(
                    UserSavedPreset.user_id == current_user.id,
                    UserSavedPreset.preset_id == preset_id,
                )
            )
            saved_preset = result.scalar_one_or_none()
            if saved_preset:
                saved_preset.sync_enabled = False
                processed_count += 1
        
        await db.commit()

    # Сохраняем правило пользователя, если задано
    if action.save_rule:
        rule_mapping = {
            "restore": "always_restore",
            "delete": "always_delete",
            "skip": "always_ask",  # Для skip используем always_ask
        }
        rule = rule_mapping.get(action.action, "always_ask")
        await save_user_deleted_preset_rule(current_user.id, rule, db)

    # Удаляем обработанные пресеты из extra_data
    if notification.extra_data:
        processed_preset_ids = {p["preset_id"] for p in deleted_presets}
        remaining_presets = [
            p for p in notification.extra_data.get("deleted_presets", [])
            if p["preset_id"] not in processed_preset_ids
        ]
        notification.extra_data["deleted_presets"] = remaining_presets
        
        # Обновляем счетчики
        notification.extra_data["created_count"] = sum(1 for p in remaining_presets if p.get("is_created", False))
        notification.extra_data["saved_count"] = sum(1 for p in remaining_presets if p.get("is_saved", False))
        
        # Если все пресеты обработаны, отмечаем уведомление как прочитанное
        if len(remaining_presets) == 0:
            from datetime import datetime, timezone
            notification.read = True
            notification.read_at = datetime.now(timezone.utc)

    await db.commit()

    return DeletedPresetActionResponse(
        message="Action processed",
        action=action.action,
        processed_count=processed_count,
        total_count=len(deleted_presets),
    )


@router.post("/deleted-presets/auto-process", status_code=status.HTTP_200_OK)
async def auto_process_deleted_presets(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Автоматически обработать удалённые уведомления (вызывается при синхронизации).
    
    Для сохранённых пресетов: удалить из "Профили филамента" через 7 дней или при следующей синхронизации.
    Для созданных пресетов: ничего не делать.
    """
    from datetime import datetime, timedelta, timezone

    # Находим все необработанные уведомления о удалённых пресетах старше 7 дней
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.type == NotificationType.PRESET_LOCALLY_DELETED,
            Notification.read.is_(False),
            Notification.created_at < seven_days_ago,
        )
    )
    old_notifications = result.scalars().all()

    processed_count = 0

    for notification in old_notifications:
        if not notification.extra_data:
            continue

        deleted_presets = notification.extra_data.get("deleted_presets", [])

        for preset_data in deleted_presets:
            preset_id = preset_data["preset_id"]
            is_created = preset_data.get("is_created", False)
            is_saved = preset_data.get("is_saved", False)

            if is_created:
                # Пресет создан пользователем - НЕ удаляем из FilamentHub
                continue
            elif is_saved:
                # Пресет сохранён пользователем - удаляем из "Профили филамента"
                await remove_saved_preset(current_user.id, preset_id, db)
                processed_count += 1

        # Отмечаем уведомление как прочитанное
        notification.read = True
        notification.read_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "message": "Auto-processed deleted presets",
        "processed_count": processed_count,
        "notifications_processed": len(old_notifications),
    }


