"""Endpoints for OrcaSlicer synchronisation (printer & print profiles)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_EXPORT_PRINT_DISABLED,
    ERR_EXPORT_PRINTER_DISABLED,
    ERR_IMPORT_FILAMENT_DISABLED,
    ERR_IMPORT_PRINT_DISABLED,
    ERR_IMPORT_PRINTER_DISABLED,
    ERR_INTERNAL_ERROR,
    ERR_NO_PERMISSION,
    ERR_NO_NOTIFICATION_DATA,
    ERR_NOTIFICATION_NOT_FOUND,
    ERR_PRESET_IDS_REQUIRED,
    ERR_PRESET_NOT_FOUND,
    ERR_TOO_MANY_PROFILES,
    raise_error,
)
from app.core.utils import like_pattern
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.notification import Notification, NotificationType
from app.models.preset import Preset, PresetModerationStatus
from app.models.print_profile import PrintProfile
from app.models.print_profile_filament import PrintProfileFilament
from app.models.print_profile_printer import PrintProfilePrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User, UserRole
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool
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
from app.services.preset_moderation import moderate_preset, validate_text_field
from app.services.slug_service import generate_unique_slug

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orcaslicer", tags=["orcaslicer"])


def _serialize_moderation_reason(reason: Any) -> str | None:
    if reason is None:
        return None
    if isinstance(reason, (dict, list)):
        return json.dumps(reason, ensure_ascii=False)
    return str(reason)


async def _resolve_preset_filament(
    preset: Preset,
    filament_hint: Filament | None,
    db: AsyncSession,
) -> Filament | None:
    if preset.filament_id is None:
        return None
    if filament_hint is not None and filament_hint.id == preset.filament_id:
        return filament_hint
    return await db.get(Filament, preset.filament_id)


async def _apply_orca_import_moderation(
    preset: Preset,
    filament_hint: Filament | None,
    db: AsyncSession,
) -> None:
    """Применить модерацию к пресету при импорте из Orca.

    Для импорта мы не блокируем сохранение: всё, что не APPROVED, переводим в PENDING
    с сохранением причины в moderation_reason.
    """
    if preset.is_official:
        preset.moderation_status = PresetModerationStatus.APPROVED
        preset.moderation_reason = None
        return

    filament = await _resolve_preset_filament(preset, filament_hint, db)
    if filament is None:
        preset.moderation_status = PresetModerationStatus.PENDING
        preset.moderation_reason = None
        return

    moderation_status, moderation_reason = await moderate_preset(
        preset,
        filament,
        db,
        is_official=False,
    )

    if moderation_status == PresetModerationStatus.APPROVED:
        preset.moderation_status = PresetModerationStatus.APPROVED
        preset.moderation_reason = None
        return

    preset.moderation_status = PresetModerationStatus.PENDING
    preset.moderation_reason = _serialize_moderation_reason(moderation_reason)


def _normalize_for_match(value: str | None) -> str:
    """Нормализовать строку для сопоставления (lowercase, убрать лишние пробелы)."""
    if not value:
        return ""
    return " ".join(str(value).lower().strip().split())


_PLACEHOLDER_IDENTITIES = {
    "printer",
    "принтер",
    "unknown",
    "default",
    "generic",
    "custom",
    "none",
    "null",
    "n/a",
    "na",
    "-",
}
_PLACEHOLDER_PRINTER_RE = re.compile(r"^(printer|принтер)\s*[-_#:]?\s*\d+$", re.IGNORECASE)
_VENDOR_ALIASES = {
    "bambu": "Bambu Lab",
    "bambulab": "Bambu Lab",
    "creality3d": "Creality",
    "prusa3d": "Prusa",
    "prusaresearch": "Prusa",
    "qiditech": "QIDI",
}


def _is_placeholder_identity(value: str | None) -> bool:
    normalized = _normalize_for_match(value)
    if not normalized:
        return True
    if normalized in _PLACEHOLDER_IDENTITIES:
        return True
    if _PLACEHOLDER_PRINTER_RE.fullmatch(normalized):
        return True
    return False


def _clean_identity_value(value: Any | None) -> str:
    if value is None:
        return ""
    cleaned = str(value).strip()
    if not cleaned:
        return ""
    if _is_placeholder_identity(cleaned):
        return ""
    return cleaned


def _normalize_vendor_name(value: Any | None) -> str:
    cleaned = _clean_identity_value(value)
    if not cleaned:
        return ""
    normalized = _normalize_for_match(cleaned).replace("-", " ").replace("_", " ")
    normalized = " ".join(normalized.split())
    alias_key = normalized.replace(" ", "")
    return _VENDOR_ALIASES.get(alias_key, cleaned)


def _vendor_search_terms(value: Any | None) -> list[str]:
    cleaned = _clean_identity_value(value)
    if not cleaned:
        return []
    canonical = _normalize_vendor_name(cleaned)
    terms = {cleaned, canonical}
    for candidate in (cleaned, canonical):
        compact = candidate.replace(" ", "")
        if compact:
            terms.add(compact)
    return [term for term in terms if term]


def _normalize_vendor_key(value: str | None) -> str:
    normalized = _normalize_for_match(value)
    if not normalized:
        return ""
    return normalized.replace(" ", "").replace("-", "").replace("_", "")


def _extract_base_printer_name(name: str) -> str:
    """Remove common Orca nozzle suffix from printer profile names."""
    match = re.match(r"^(.*?)\s+\d+(?:\.\d+)?\s*nozzle$", name.strip(), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return name.strip()


def _slugify_string(value: str, fallback: str = "item") -> str:
    """Generate a stable slug-like value for compatibility links."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


async def _resolve_print_profile_printer_link(
    *,
    db: AsyncSession,
    owner_user_id: int | None,
    identifier: str,
) -> tuple[int | None, str]:
    """Resolve imported compatible printer entry to a FilamentHub printer link."""
    name = (identifier or "").strip()
    if not name:
        return None, ""

    printer: Printer | None = None

    if name.isdigit():
        printer = await db.get(Printer, int(name))

    if printer is None:
        result = await db.execute(
            select(Printer).where(
                or_(
                    Printer.slug == name,
                    Printer.name == name,
                    Printer.model == name,
                )
            )
        )
        printer = result.scalars().first()

    if printer is not None:
        return printer.id, printer.slug

    printer_profile: PrinterProfile | None = None
    if owner_user_id is not None:
        result = await db.execute(
            select(PrinterProfile).where(
                PrinterProfile.owner_user_id == owner_user_id,
                or_(
                    PrinterProfile.name == name,
                    PrinterProfile.slug == name,
                ),
            )
        )
        printer_profile = result.scalars().first()

    if printer_profile is None:
        result = await db.execute(
            select(PrinterProfile).where(
                or_(
                    PrinterProfile.name == name,
                    PrinterProfile.slug == name,
                )
            )
        )
        printer_profile = result.scalars().first()

    if printer_profile is not None:
        if printer_profile.printer_id:
            printer = await db.get(Printer, printer_profile.printer_id)
            if printer is not None:
                return printer.id, printer.slug

    base_name = _extract_base_printer_name(name)
    if base_name and base_name != name:
        result = await db.execute(
            select(Printer).where(
                or_(
                    Printer.name == base_name,
                    Printer.model == base_name,
                    Printer.slug == _slugify_string(base_name),
                )
            )
        )
        printer = result.scalars().first()
        if printer is not None:
            return printer.id, printer.slug

    return None, _slugify_string(name)[:200]


async def _resolve_print_profile_filament_link(
    *,
    db: AsyncSession,
    identifier: str,
) -> tuple[int | None, str]:
    """Resolve imported compatible filament entry to a FilamentHub filament link."""
    name = (identifier or "").strip()
    if not name:
        return None, ""

    filament: Filament | None = None
    if name.isdigit():
        filament = await db.get(Filament, int(name))

    if filament is None:
        result = await db.execute(
            select(Filament).where(
                or_(
                    Filament.slug == name,
                    Filament.name == name,
                )
            )
        )
        filament = result.scalars().first()

    if filament is None and "@" in name:
        short_name = name.split("@", 1)[0].strip()
        if short_name:
            result = await db.execute(select(Filament).where(Filament.name == short_name))
            filament = result.scalars().first()

    if filament is not None:
        return filament.id, filament.slug

    return None, _slugify_string(name)[:200]


async def _sync_imported_print_profile_links(
    *,
    db: AsyncSession,
    profile: PrintProfile,
) -> None:
    """Synchronise junction links for print profile import from OrcaSlicer."""
    await profile.awaitable_attrs.printer_links
    await profile.awaitable_attrs.filament_links
    profile.printer_links.clear()
    profile.filament_links.clear()

    printer_slugs: set[str] = set()
    for entry in profile.compatible_printers or []:
        printer_id, printer_slug = await _resolve_print_profile_printer_link(
            db=db,
            owner_user_id=profile.owner_user_id,
            identifier=entry,
        )
        if not printer_slug or printer_slug in printer_slugs:
            continue
        printer_slugs.add(printer_slug)
        profile.printer_links.append(
            PrintProfilePrinter(
                printer_id=printer_id,
                printer_slug=printer_slug,
                relation_type="explicit",
            )
        )

    condition = ""
    if isinstance(profile.extra_metadata, dict):
        condition = str(profile.extra_metadata.get("compatible_printers_condition") or "").strip()
    if condition:
        condition_slug = _slugify_string(condition, fallback="condition")[:200]
        if condition_slug in printer_slugs:
            condition_slug = f"{condition_slug}-{len(printer_slugs) + 1}"[:200]
        profile.printer_links.append(
            PrintProfilePrinter(
                printer_id=None,
                printer_slug=condition_slug,
                relation_type="condition",
                condition=condition,
            )
        )

    filament_slugs: set[str] = set()
    for entry in profile.compatible_filaments or []:
        filament_id, filament_slug = await _resolve_print_profile_filament_link(
            db=db,
            identifier=entry,
        )
        if not filament_slug or filament_slug in filament_slugs:
            continue
        filament_slugs.add(filament_slug)
        profile.filament_links.append(
            PrintProfileFilament(
                filament_id=filament_id,
                filament_slug=filament_slug,
                relation_type="explicit",
            )
        )

    await db.flush()


def _extract_material_type_from_inherits(inherits: str | None) -> str:
    """
    Извлечь тип материала из inherits (родительский пресет OrcaSlicer).
    
    Примеры:
    - "Generic PLA @System" -> "PLA"
    - "Generic PETG @System" -> "PETG"
    - "Generic ABS @System" -> "ABS"
    """
    if not inherits:
        return "PLA"  # По умолчанию
    
    inherits_upper = inherits.upper()
    
    # Порядок важен - проверяем более специфичные сначала
    if "PETG" in inherits_upper or "PET" in inherits_upper:
        return "PETG"
    if "ABS" in inherits_upper:
        return "ABS"
    if "ASA" in inherits_upper:
        return "ASA"
    if "TPU" in inherits_upper:
        return "TPU"
    if "PC" in inherits_upper:
        return "PC"
    if "PA" in inherits_upper or "NYLON" in inherits_upper:
        return "PA"
    if "PVA" in inherits_upper:
        return "PVA"
    if "PLA" in inherits_upper:
        return "PLA"
    
    # По умолчанию PLA
    return "PLA"


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
    """Сопоставление принтера из OrcaSlicer с существующим в базе."""
    import logging
    logger = logging.getLogger(__name__)

    # Логируем входные данные для отладки
    logger.info(f"🔍 _ensure_printer_id: name='{profile_name}', vendor='{profile_vendor}'")
    if profile_settings:
        printer_model = profile_settings.get('printer_model')
        inherits = profile_settings.get('inherits')
        logger.info(f"  📋 printer_model='{printer_model}', inherits='{inherits}'")
        logger.info(f"  📋 all keys: {list(profile_settings.keys())}")
    if profile_metadata:
        logger.info(f"  📋 metadata keys: {list(profile_metadata.keys())}")
    """
    Автоматическое сопоставление принтера с существующим в базе.

    Алгоритм поиска (в порядке приоритета):
    1. По printer_id (если указан явно)
    2. По printer_slug (если указан)
    3. По model_id из metadata/settings (самый надежный способ)
    4. По vendor + model (для принтеров из базы OrcaSlicer) - ПРИОРИТЕТНЫЙ
    5. По manufacturer + model (нормализованные)
    6. По vendor + name (нормализованные)
    7. По имени принтера (fallback для пользовательских принтеров)
    8. По vendor + model из metadata (расширенный поиск)

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
    
    # 4. Извлекаем данные для сопоставления из OrcaSlicer metadata
    vendor_name = ""
    for vendor_candidate in (
        profile_vendor,
        combined_metadata.get("printer_vendor"),
        combined_metadata.get("vendor"),
        combined_metadata.get("from"),  # OrcaSlicer может указывать vendor в поле "from"
    ):
        normalized_vendor = _normalize_vendor_name(vendor_candidate)
        if normalized_vendor:
            vendor_name = normalized_vendor
            break

    # Для printer_model пробуем разные поля из OrcaSlicer и отбрасываем placeholder значения
    printer_model = ""
    for model_candidate in (
        combined_metadata.get("printer_model"),  # Основное поле для ссылки на базовую модель
        combined_metadata.get("model"),
        combined_metadata.get("name"),  # Иногда model хранится в name
    ):
        cleaned_model = _clean_identity_value(model_candidate)
        if cleaned_model:
            printer_model = cleaned_model
            break

    # Если model пустой, попробуем извлечь из inherits (ссылка на базовый принтер)
    if not printer_model and combined_metadata.get("inherits"):
        inherits = combined_metadata.get("inherits")
        if isinstance(inherits, str):
            # Формат: "vendor/model" или просто "model" или путь к файлу
            parts = inherits.split("/")
            if len(parts) >= 2:
                # Если есть vendor/model в inherits
                vendor_name = vendor_name or _normalize_vendor_name(parts[-2])  # Предпоследняя часть
                printer_model = printer_model or _clean_identity_value(parts[-1])  # Последняя часть
            elif len(parts) == 1:
                # Просто имя модели в inherits
                printer_model = printer_model or _clean_identity_value(inherits)
    
    # Пытаемся определить manufacturer и model из имени профиля
    # Сначала пробуем извлечь чистое название принтера (без диаметра сопла)
    clean_printer_name = _extract_printer_name_from_profile_name(profile_name)

    # Для OrcaSlicer принтеров имя часто имеет формат: "Vendor Model nozzle"
    # Пример: "Creality Ender 3 0.4 nozzle" -> vendor="Creality", model="Ender 3"
    name_parts = (clean_printer_name or profile_name or "").split()
    manufacturer_from_name = _clean_identity_value(name_parts[0] if name_parts else "")
    model_from_name = _clean_identity_value(
        " ".join(name_parts[1:]) if len(name_parts) > 1 else (clean_printer_name or profile_name or "")
    )

    # Если vendor не указан в metadata, попробуем извлечь его из имени профиля
    # Для OrcaSlicer формат обычно: "Vendor Model nozzle" или просто "Vendor Model"
    if not vendor_name and clean_printer_name:
        # Ищем в нашей базе принтеров с похожим manufacturer
        # Это позволит автоматически определять vendor для новых принтеров
        potential_manufacturers = set()

        # Соберем все уникальные manufacturer'ы из базы для быстрого поиска
        manufacturer_query = select(Printer.manufacturer).distinct()
        manufacturer_result = await db.execute(manufacturer_query)
        all_manufacturers = [row[0] for row in manufacturer_result.fetchall()]

        # Проверим, начинается ли имя принтера с какого-то известного manufacturer'а
        for manufacturer in all_manufacturers:
            if manufacturer and clean_printer_name.upper().startswith(manufacturer.upper()):
                normalized_manufacturer = _normalize_vendor_name(manufacturer)
                if normalized_manufacturer:
                    potential_manufacturers.add(normalized_manufacturer)

        # Если нашли потенциальных manufacturer'ов, выберем самого длинного (точнее)
        if potential_manufacturers:
            vendor_name = max(potential_manufacturers, key=len)
            # Уберем vendor из начала имени для получения model
            if clean_printer_name.upper().startswith(vendor_name.upper()):
                remaining_part = clean_printer_name[len(vendor_name):].strip()
                if remaining_part:
                    model_from_name = _clean_identity_value(remaining_part)

    # Извлекаем manufacturer и model из combined_metadata (если OrcaSlicer передал их отдельно)
    manufacturer_from_metadata = _clean_identity_value(combined_metadata.get("manufacturer"))
    model_from_metadata = _clean_identity_value(combined_metadata.get("model"))
    
    # Используем данные из metadata, если есть, иначе из имени
    vendor_name = _normalize_vendor_name(vendor_name)
    manufacturer = manufacturer_from_metadata or vendor_name or manufacturer_from_name or "Custom"
    model = (
        model_from_metadata
        or _clean_identity_value(printer_model)
        or model_from_name
        or _clean_identity_value(profile_name)
        or "Unknown"
    )
    
    # Нормализуем для сопоставления
    manufacturer_normalized = _normalize_for_match(_clean_identity_value(manufacturer))
    model_normalized = _normalize_for_match(_clean_identity_value(model))
    vendor_normalized = _normalize_for_match(vendor_name)
    vendor_key = _normalize_vendor_key(vendor_name)
    name_normalized = _normalize_for_match(_clean_identity_value(profile_name))
    
    # 5. Поиск по printer_model из OrcaSlicer (ссылка на базовую модель) - САМЫЙ ПРИОРИТЕТНЫЙ
    if printer_model:
        logger.info(f"  🔍 Шаг 5: Ищем по printer_model='{printer_model}'")
        # Ищем принтер по точному совпадению name или model_id
        result = await db.execute(
            select(Printer).where(
                or_(
                    Printer.name.ilike(like_pattern(printer_model)),
                    Printer.model_id.ilike(like_pattern(printer_model)),
                )
            )
        )
        printers = result.scalars().all()
        logger.info(f"  📊 Найдено {len(printers)} кандидатов по printer_model")
        for printer in printers:
            # Точное совпадение имени модели
            if _normalize_for_match(printer.name) == _normalize_for_match(printer_model):
                logger.info(f"  ✅ Найден по точному совпадению имени: {printer.name} (id={printer.id})")
                return printer.id
            # Или совпадение по model_id (если printer_model содержит model_id)
            if printer.model_id and _normalize_for_match(printer.model_id) in _normalize_for_match(printer_model):
                logger.info(f"  ✅ Найден по model_id: {printer.model_id} (id={printer.id})")
                return printer.id

    # 6. Поиск по vendor + model (для принтеров из базы OrcaSlicer) - ПРИОРИТЕТНЫЙ
    search_model = _normalize_for_match(
        _clean_identity_value(printer_model) or _clean_identity_value(model)
    )
    if vendor_normalized and search_model:
        vendor_terms = _vendor_search_terms(vendor_name)
        vendor_conditions = [Printer.vendor.ilike(like_pattern(term)) for term in vendor_terms] or [
            Printer.vendor.ilike(like_pattern(vendor_name))
        ]

        # Точное совпадение vendor + model
        result = await db.execute(
            select(Printer).where(
                or_(*vendor_conditions),
                Printer.model.ilike(like_pattern(search_model))
            )
        )
        printer = result.scalar_one_or_none()
        if printer:
            return printer.id

        # Если точное не найдено, попробуем умное сопоставление моделей
        logger.info(f"  🔍 Шаг 6: Умное сопоставление для vendor='{vendor_name}', model='{search_model}'")
        result = await db.execute(
            select(Printer).where(or_(*vendor_conditions))
        )
        vendor_printers = result.scalars().all()
        logger.info(f"  📊 Найдено {len(vendor_printers)} принтеров vendor'а {vendor_name}")

        for printer in vendor_printers:
            printer_model_norm = _normalize_for_match(printer.model)

            # Проверяем различные варианты совпадения:
            # 1. Модель из OrcaSlicer содержится в нашей модели
            if search_model in printer_model_norm:
                logger.info(f"  ✅ Найден (модель содержится): '{search_model}' в '{printer_model_norm}' (id={printer.id})")
                return printer.id

            # 2. Наша модель содержится в модели из OrcaSlicer
            if printer_model_norm in search_model:
                logger.info(f"  ✅ Найден (содержит модель): '{printer_model_norm}' в '{search_model}' (id={printer.id})")
                return printer.id

            # 3. Совпадение по ключевым словам (например "Ender 3" и "Ender 3 Pro")
            search_words = set(search_model.split())
            printer_words = set(printer_model_norm.split())
            common_words = search_words & printer_words

            # Если больше половины слов совпадают, считаем что это тот же принтер
            if len(common_words) > 0 and len(common_words) >= len(search_words) * 0.5:
                logger.info(f"  ✅ Найден по ключевым словам: {common_words} из {search_words} (id={printer.id})")
                return printer.id

    # 7. Поиск по manufacturer + model (case-insensitive через SQL LIKE)
    if manufacturer_normalized and model_normalized:
        # Строим условия поиска
        manufacturer_conditions = [Printer.manufacturer.ilike(like_pattern(manufacturer))]
        if vendor_name:  # Добавляем только если vendor_name не пустой
            vendor_terms = _vendor_search_terms(vendor_name)
            manufacturer_conditions.extend(
                Printer.manufacturer.ilike(like_pattern(term)) for term in vendor_terms
            )

        # Точное совпадение (case-insensitive)
        result = await db.execute(
            select(Printer).where(
                or_(
                    or_(*manufacturer_conditions),  # manufacturer содержит искомое
                    Printer.model.ilike(like_pattern(model)),  # ИЛИ model содержит искомое
                )
            )
        )
        printers = result.scalars().all()
        
        # Фильтруем в памяти для точного сопоставления (SQL не может нормализовать так же точно)
        for printer in printers:
            printer_manufacturer = _normalize_for_match(printer.manufacturer)
            printer_manufacturer_key = _normalize_vendor_key(printer.manufacturer)
            printer_model_norm = _normalize_for_match(printer.model)

            # Точное совпадение manufacturer и model
            if (
                (printer_manufacturer == manufacturer_normalized or printer_manufacturer_key == vendor_key)
                and printer_model_norm == model_normalized
            ):
                return printer.id

            # Частичное совпадение (если manufacturer совпадает, а model содержит искомую модель)
            if (
                (printer_manufacturer == manufacturer_normalized or printer_manufacturer_key == vendor_key)
                and model_normalized in printer_model_norm
            ):
                return printer.id
    
    # 8. Поиск по vendor + name (нормализованные)
    if vendor_normalized and name_normalized:
        vendor_terms = _vendor_search_terms(vendor_name)
        vendor_conditions = [Printer.vendor.ilike(like_pattern(term)) for term in vendor_terms] or [
            Printer.vendor.ilike(like_pattern(vendor_name))
        ]
        result = await db.execute(
            select(Printer).where(
                or_(*vendor_conditions),
                Printer.name.ilike(like_pattern(profile_name)),
            )
        )
        printers = result.scalars().all()
        
        for printer in printers:
            printer_vendor_key = _normalize_vendor_key(printer.vendor)
            printer_name = _normalize_for_match(printer.name)
            
            if printer_vendor_key == vendor_key and printer_name == name_normalized:
                return printer.id

    # 7. Fallback: поиск по имени принтера (для случаев когда OrcaSlicer не передает ID)
    if profile_name:
        clean_printer_name = _extract_printer_name_from_profile_name(profile_name)
        clean_printer_name = _clean_identity_value(clean_printer_name)
        if clean_printer_name:
            result = await db.execute(
                select(Printer).where(Printer.name.ilike(like_pattern(clean_printer_name)))
            )
            printers = result.scalars().all()

            for printer in printers:
                # Точное совпадение имени (без учета регистра и лишних пробелов)
                if _normalize_for_match(printer.name) == _normalize_for_match(clean_printer_name):
                    return printer.id

    # 8. Поиск по vendor + model из metadata
    if vendor_normalized and model_normalized:
        vendor_terms = _vendor_search_terms(vendor_name)
        vendor_conditions = [Printer.vendor.ilike(like_pattern(term)) for term in vendor_terms] or [
            Printer.vendor.ilike(like_pattern(vendor_name))
        ]
        result = await db.execute(
            select(Printer).where(
                or_(*vendor_conditions),
                Printer.model.ilike(like_pattern(model)),
            )
        )
        printers = result.scalars().all()

        for printer in printers:
            printer_vendor_key = _normalize_vendor_key(printer.vendor)
            printer_model_norm = _normalize_for_match(printer.model)

            if printer_vendor_key == vendor_key and printer_model_norm == model_normalized:
                return printer.id

    # Принтер не найден - создаем новый
    logger.info(f"  ❌ Принтер не найден, создаем новый: manufacturer='{manufacturer}', model='{model}'")
    if profile_name:
        from app.services.slug_service import generate_unique_slug

        # Формируем правильное имя принтера из manufacturer и model
        # Используем очищенное имя профиля (без диаметра сопла) если оно лучше
        clean_profile_name = _clean_identity_value(clean_printer_name) or _clean_identity_value(profile_name)
        printer_display_name = clean_profile_name if clean_profile_name and clean_profile_name != profile_name else None
        
        # Если manufacturer и model определены правильно, используем их для имени
        if manufacturer_normalized and model_normalized:
            # Формируем имя: "Manufacturer Model" или просто "Model" если manufacturer пустой
            if manufacturer and manufacturer.lower() != "custom":
                printer_display_name = f"{manufacturer} {model}".strip()
            else:
                printer_display_name = model.strip()
        elif clean_profile_name:
            # Используем очищенное имя профиля (без диаметра сопла)
            printer_display_name = clean_profile_name
        else:
            # Жесткий fallback, когда входные данные полностью placeholder
            printer_display_name = "Custom printer"

        # Используем printer_slug если есть, иначе генерируем из правильного имени
        final_slug = printer_slug
        if not final_slug:
            slug_source = f"{manufacturer} {model}".strip() if manufacturer_normalized and model_normalized else printer_display_name
            final_slug = await generate_unique_slug(
                db=db,
                model=Printer,
                source=slug_source,
                fallback="printer",
            )

        logger.info(f"  🆕 Создание нового принтера: '{printer_display_name}' (manufacturer='{manufacturer}', model='{model}', slug: {final_slug})")
        printer = Printer(
            name=printer_display_name,  # Используем правильное имя, а не профиль с диаметром сопла
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
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            # Race condition: другой запрос создал принтер параллельно — ищем заново
            result = await db.execute(
                select(Printer).where(Printer.slug == final_slug)
            )
            existing = result.scalar_one_or_none()
            if existing:
                logger.info(f"  ♻️ Race condition resolved: found printer {existing.id} by slug")
                return existing.id
            logger.warning("IntegrityError при создании принтера, но повторный поиск не дал результата")
            return None
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


def _extract_printer_name_from_profile_name(profile_name: str | None) -> str | None:
    """
    Извлечь название принтера из имени профиля, убрав диаметр сопла.

    Формат OrcaSlicer: "{Manufacturer} {Model} {nozzle} nozzle"
    Пример: "Voron 2.4 350 0.4 nozzle" -> "Voron 2.4 350"
    """
    if not profile_name:
        return None

    # Регулярное выражение для поиска паттерна "{что-то} {число} nozzle"
    import re
    pattern = r"^(.*)\s+\d+\.?\d*\s+nozzle$"
    match = re.search(pattern, profile_name.strip(), re.IGNORECASE)

    if match:
        return match.group(1).strip()

    # Если паттерн не найден, возвращаем имя как есть
    return profile_name.strip()


def _convert_printable_area_from_orca(printable_area: Any) -> dict[str, float] | None:
    """
    Преобразовать printable_area из формата OrcaSlicer в наш формат.
    
    OrcaSlicer формат: ["0x0", "220x0", "220x220", "0x220"] (массив строк с координатами углов)
    Наш формат: {"x": 220, "y": 220} (ширина и глубина)
    
    Возвращает dict с ключами "x" и "y" или None, если не удалось преобразовать.
    """
    if not printable_area:
        return None
    
    try:
        # Если это уже наш формат (dict с x и y)
        if isinstance(printable_area, dict):
            if "x" in printable_area and "y" in printable_area:
                return {"x": float(printable_area["x"]), "y": float(printable_area["y"])}
            # Если это старый формат с x_min, y_min, x_max, y_max
            if "x_min" in printable_area and "y_min" in printable_area and "x_max" in printable_area and "y_max" in printable_area:
                x = float(printable_area["x_max"]) - float(printable_area["x_min"])
                y = float(printable_area["y_max"]) - float(printable_area["y_min"])
                return {"x": x, "y": y}
        
        # Если это массив строк (формат OrcaSlicer)
        if isinstance(printable_area, list) and len(printable_area) >= 2:
            # Парсим первую и третью координаты для определения размеров
            # ["0x0", "220x0", "220x220", "0x220"]
            # Извлекаем максимальные координаты
            max_x = 0
            max_y = 0
            
            for coord_str in printable_area:
                if isinstance(coord_str, str) and "x" in coord_str:
                    parts = coord_str.split("x")
                    if len(parts) == 2:
                        try:
                            x_val = float(parts[0])
                            y_val = float(parts[1])
                            max_x = max(max_x, x_val)
                            max_y = max(max_y, y_val)
                        except (ValueError, TypeError):
                            continue
            
            if max_x > 0 and max_y > 0:
                return {"x": max_x, "y": max_y}
    except (ValueError, TypeError, AttributeError):
        pass
    
    return None


def _extract_nozzle_diameters_from_settings(settings: dict[str, Any] | None) -> list[float] | None:
    """
    Извлечь диаметры сопла из orcaslicer_settings профиля.
    
    В OrcaSlicer поле nozzle_diameter может быть:
    - Массивом строк: ["0.4"] или ["0.4", "0.6"]
    - Строкой: "0.4"
    - Числом: 0.4
    
    Возвращает список float значений или None, если не найдено.
    """
    if not settings:
        return None
    
    nozzle_diameter = settings.get("nozzle_diameter")
    if nozzle_diameter is None:
        return None
    
    diameters: list[float] = []
    
    try:
        # Массив строк или чисел
        if isinstance(nozzle_diameter, list):
            for item in nozzle_diameter:
                try:
                    if isinstance(item, (int, float)):
                        diameters.append(float(item))
                    elif isinstance(item, str):
                        diameters.append(float(item))
                except (ValueError, TypeError):
                    continue
        # Строка
        elif isinstance(nozzle_diameter, str):
            diameters.append(float(nozzle_diameter))
        # Число
        elif isinstance(nozzle_diameter, (int, float)):
            diameters.append(float(nozzle_diameter))
    except (ValueError, TypeError):
        return None
    
    # Фильтруем разумные значения (0.15-1.5 мм)
    valid_diameters = [d for d in diameters if 0.15 <= d <= 1.5]
    return valid_diameters if valid_diameters else None


async def _upsert_printer_profile(
    *,
    payload,
    current_user: User,
    db: AsyncSession,
) -> OrcaSyncResult:
    from app.schemas.orca_sync import OrcaPrinterProfilePayload

    if not isinstance(payload, OrcaPrinterProfilePayload):
        raise ValueError("Invalid payload type for printer profile import")

    is_valid, error_msg = await validate_text_field(payload.name, db, "printer_profile_name")
    if not is_valid:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=payload.fhub_id,
            status="error",
            message=error_msg,
        )

    for field_value, label in [
        (payload.description, "printer_profile_description"),
        (payload.notes, "printer_profile_notes"),
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
    
    # Проверяем метки из orcaslicer_settings (приоритетный способ идентификации)
    orcaslicer_settings = payload.orcaslicer_settings or {}
    fhub_id_from_metadata = orcaslicer_settings.get("fhub_id")
    fhub_source = orcaslicer_settings.get("fhub_source")
    
    # Приоритет 1: Ищем по fhub_id из payload (явное указание)
    if payload.fhub_id:
        profile = await db.get(PrinterProfile, payload.fhub_id)
        if profile:
            # Проверяем права доступа
            if profile.owner_user_id not in (None, current_user.id) and current_user.role != UserRole.ADMIN:
                return OrcaSyncResult(
                    external_id=payload.external_id,
                    fhub_id=payload.fhub_id,
                    status="error",
                    message=ERR_NO_PERMISSION,
                )
            logger.info(f"Found printer profile by fhub_id from payload: {payload.fhub_id}")
    
    # Приоритет 2: Ищем по меткам из orcaslicer_settings
    if profile is None:
        if fhub_id_from_metadata and fhub_source == "filamenthub":
            try:
                fhub_id_int = int(fhub_id_from_metadata)
                profile = await db.get(PrinterProfile, fhub_id_int)
                if profile:
                    # Проверяем права доступа
                    if profile.owner_user_id not in (None, current_user.id) and current_user.role != UserRole.ADMIN:
                        return OrcaSyncResult(
                            external_id=payload.external_id,
                            fhub_id=fhub_id_int,
                            status="error",
                            message=ERR_NO_PERMISSION,
                        )
                    logger.info(f"Found printer profile by fhub_id from metadata: {fhub_id_int}")
            except (ValueError, TypeError):
                logger.warning(f"Invalid fhub_id in metadata: {fhub_id_from_metadata}")
    
    # Приоритет 3: Ищем по external_id (fallback)
    if profile is None and payload.external_id:
        result = await db.execute(
            select(PrinterProfile).where(
                PrinterProfile.external_id == payload.external_id,
                PrinterProfile.owner_user_id == current_user.id,
            )
        )
        profile = result.scalars().first()
        if profile:
            logger.info(
                f"Found printer profile by external_id {payload.external_id} instead of fhub_id {payload.fhub_id}"
            )

    # Приоритет 4: Ищем по slug (fallback)
    if profile is None and payload.slug:
        result = await db.execute(
            select(PrinterProfile).where(
                PrinterProfile.slug == payload.slug,
                PrinterProfile.owner_user_id == current_user.id,
            )
        )
        profile = result.scalars().first()

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
                message=ERR_NO_PERMISSION,
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
        # Обновляем nozzle_diameters: сначала из payload, потом из orcaslicer_settings
        if payload.nozzle_diameters is not None and payload.nozzle_diameters != [0.0]:
            profile.nozzle_diameters = payload.nozzle_diameters
        elif not profile.nozzle_diameters or profile.nozzle_diameters == [0.0]:
            # Если диаметры не указаны, извлекаем из orcaslicer_settings
            extracted_diameters = _extract_nozzle_diameters_from_settings(payload.orcaslicer_settings)
            if extracted_diameters:
                profile.nozzle_diameters = extracted_diameters
        
        # Обновляем printable_area: сначала из payload, потом из orcaslicer_settings
        if payload.printable_area is not None:
            profile.printable_area = payload.printable_area
        elif payload.orcaslicer_settings and "printable_area" in payload.orcaslicer_settings:
            # Преобразуем из формата OrcaSlicer в наш формат
            converted_area = _convert_printable_area_from_orca(payload.orcaslicer_settings.get("printable_area"))
            if converted_area:
                profile.printable_area = converted_area
        
        # Обновляем printable_height_mm: сначала из payload, потом из orcaslicer_settings
        if payload.printable_height_mm is not None:
            profile.printable_height_mm = payload.printable_height_mm
        elif payload.orcaslicer_settings and "printable_height" in payload.orcaslicer_settings:
            printable_height_raw = payload.orcaslicer_settings.get("printable_height")
            if printable_height_raw:
                try:
                    if isinstance(printable_height_raw, str):
                        profile.printable_height_mm = float(printable_height_raw)
                    elif isinstance(printable_height_raw, (int, float)):
                        profile.printable_height_mm = float(printable_height_raw)
                except (ValueError, TypeError):
                    pass  # Оставляем старое значение
        if payload.extra_metadata:
            profile.extra_metadata = payload.extra_metadata
        if payload.orcaslicer_settings:
            # Сохраняем метки FilamentHub при обновлении
            updated_settings = dict(payload.orcaslicer_settings)
            
            # Приоритет: метки из payload.orcaslicer_settings (если есть), иначе существующие метки
            if "fhub_id" in updated_settings and "fhub_source" in updated_settings:
                # Метки пришли из OrcaSlicer - используем их
                logger.info(f"Using fhub_id and fhub_source from payload.orcaslicer_settings for printer profile {profile.id}")
            elif profile.orcaslicer_settings:
                # Если метки не пришли, но были раньше - сохраняем существующие
                existing_fhub_id = profile.orcaslicer_settings.get("fhub_id")
                existing_fhub_source = profile.orcaslicer_settings.get("fhub_source")
                
                if existing_fhub_id and existing_fhub_source == "filamenthub":
                    updated_settings["fhub_id"] = existing_fhub_id
                    updated_settings["fhub_source"] = existing_fhub_source
                    logger.info(f"Preserving existing fhub_id and fhub_source for printer profile {profile.id}")
            
            profile.orcaslicer_settings = updated_settings
        else:
            profile.orcaslicer_settings = profile.orcaslicer_settings or {}
        # Обновляем отдельные колонки из payload или orcaslicer_settings
        if payload.start_gcode:
            profile.start_gcode = payload.start_gcode
        elif payload.orcaslicer_settings and "machine_start_gcode" in payload.orcaslicer_settings:
            profile.start_gcode = payload.orcaslicer_settings.get("machine_start_gcode")

        if payload.end_gcode:
            profile.end_gcode = payload.end_gcode
        elif payload.orcaslicer_settings and "machine_end_gcode" in payload.orcaslicer_settings:
            profile.end_gcode = payload.orcaslicer_settings.get("machine_end_gcode")

        if payload.notes:
            profile.notes = payload.notes
        elif payload.orcaslicer_settings and "printer_notes" in payload.orcaslicer_settings:
            profile.notes = payload.orcaslicer_settings.get("printer_notes")
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

    # Извлекаем диаметр сопла: сначала из payload, потом из orcaslicer_settings
    nozzle_diameters = payload.nozzle_diameters
    if not nozzle_diameters or nozzle_diameters == [0.0]:
        # Извлекаем из orcaslicer_settings профиля
        extracted_diameters = _extract_nozzle_diameters_from_settings(payload.orcaslicer_settings)
        if extracted_diameters:
            nozzle_diameters = extracted_diameters

    # Извлекаем дополнительные поля из orcaslicer_settings, если payload их не передал
    printable_area = payload.printable_area
    if not printable_area:
        printable_area_raw = payload.orcaslicer_settings.get("printable_area") if payload.orcaslicer_settings else None
        if printable_area_raw:
            # Преобразуем из формата OrcaSlicer в наш формат
            printable_area = _convert_printable_area_from_orca(printable_area_raw)

    printable_height_mm = payload.printable_height_mm
    if not printable_height_mm:
        printable_height_raw = payload.orcaslicer_settings.get("printable_height") if payload.orcaslicer_settings else None
        if printable_height_raw:
            try:
                if isinstance(printable_height_raw, str):
                    printable_height_mm = float(printable_height_raw)
                elif isinstance(printable_height_raw, (int, float)):
                    printable_height_mm = float(printable_height_raw)
            except (ValueError, TypeError):
                printable_height_mm = None

    start_gcode = payload.start_gcode
    if not start_gcode:
        start_gcode = payload.orcaslicer_settings.get("machine_start_gcode") if payload.orcaslicer_settings else None

    end_gcode = payload.end_gcode
    if not end_gcode:
        end_gcode = payload.orcaslicer_settings.get("machine_end_gcode") if payload.orcaslicer_settings else None

    notes = payload.notes
    if not notes:
        notes = payload.orcaslicer_settings.get("printer_notes") if payload.orcaslicer_settings else None
    
    # Подготавливаем orcaslicer_settings с метками
    profile_orcaslicer_settings = dict(payload.orcaslicer_settings or {})
    
    # Добавляем метки FilamentHub для синхронизации
    profile_orcaslicer_settings["fhub_id"] = None  # Будет установлен после flush
    profile_orcaslicer_settings["fhub_source"] = "filamenthub"
    
    profile = PrinterProfile(
        name=payload.name,
        slug=slug,
        description=payload.description,
        printer_id=printer_id,
        owner_user_id=current_user.id,
        is_official=False,
        active=payload.active if payload.active is not None else True,
        source=payload.source or "user",
        vendor=payload.vendor,
        setting_id=payload.setting_id,
        external_id=payload.external_id,
        default_print_profile_slug=payload.default_print_profile_slug,
        nozzle_diameters=nozzle_diameters,
        printable_area=printable_area,
        printable_height_mm=printable_height_mm,
        extra_metadata=payload.extra_metadata,
        orcaslicer_settings=profile_orcaslicer_settings,
        start_gcode=start_gcode,
        end_gcode=end_gcode,
        notes=notes,
    )
    db.add(profile)
    await db.flush()
    
    # Обновляем fhub_id после получения ID
    if profile.orcaslicer_settings:
        profile.orcaslicer_settings["fhub_id"] = profile.id

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

    is_valid, error_msg = await validate_text_field(payload.name, db, "print_profile_name")
    if not is_valid:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=payload.fhub_id,
            status="error",
            message=error_msg,
        )

    for field_value, label in [
        (payload.description, "print_profile_description"),
        (payload.notes, "print_profile_notes"),
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
    
    # Проверяем метки из orcaslicer_settings (приоритетный способ идентификации)
    orcaslicer_settings = payload.orcaslicer_settings or {}
    fhub_id_from_metadata = orcaslicer_settings.get("fhub_id")
    fhub_source = orcaslicer_settings.get("fhub_source")
    
    # Приоритет 1: Ищем по fhub_id из payload (явное указание)
    if payload.fhub_id:
        profile = await db.get(PrintProfile, payload.fhub_id)
        if profile:
            # Проверяем права доступа
            if profile.owner_user_id not in (None, current_user.id) and current_user.role != UserRole.ADMIN:
                return OrcaSyncResult(
                    external_id=payload.external_id,
                    fhub_id=payload.fhub_id,
                    status="error",
                    message=ERR_NO_PERMISSION,
                )
            logger.info(f"Found print profile by fhub_id from payload: {payload.fhub_id}")
    
    # Приоритет 2: Ищем по меткам из orcaslicer_settings
    if profile is None:
        if fhub_id_from_metadata and fhub_source == "filamenthub":
            try:
                fhub_id_int = int(fhub_id_from_metadata)
                profile = await db.get(PrintProfile, fhub_id_int)
                if profile:
                    # Проверяем права доступа
                    if profile.owner_user_id not in (None, current_user.id) and current_user.role != UserRole.ADMIN:
                        return OrcaSyncResult(
                            external_id=payload.external_id,
                            fhub_id=fhub_id_int,
                            status="error",
                            message=ERR_NO_PERMISSION,
                        )
                    logger.info(f"Found print profile by fhub_id from metadata: {fhub_id_int}")
            except (ValueError, TypeError):
                logger.warning(f"Invalid fhub_id in metadata: {fhub_id_from_metadata}")
    
    # Приоритет 3: Ищем по external_id (fallback)
    if profile is None and payload.external_id:
        result = await db.execute(
            select(PrintProfile).where(
                PrintProfile.external_id == payload.external_id,
                PrintProfile.owner_user_id == current_user.id,
            )
        )
        profile = result.scalars().first()
        if profile:
            logger.info(
                f"Found print profile by external_id {payload.external_id} instead of fhub_id {payload.fhub_id}"
            )

    # Приоритет 4: Ищем по slug (fallback)
    if profile is None and payload.slug:
        result = await db.execute(
            select(PrintProfile).where(
                PrintProfile.slug == payload.slug,
                PrintProfile.owner_user_id == current_user.id,
            )
        )
        profile = result.scalars().first()

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
                message=ERR_NO_PERMISSION,
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
        if payload.orcaslicer_settings:
            # Сохраняем метки FilamentHub при обновлении
            updated_settings = dict(payload.orcaslicer_settings)
            
            # Приоритет: метки из payload.orcaslicer_settings (если есть), иначе существующие метки
            if "fhub_id" in updated_settings and "fhub_source" in updated_settings:
                # Метки пришли из OrcaSlicer - используем их
                logger.info(f"Using fhub_id and fhub_source from payload.orcaslicer_settings for print profile {profile.id}")
            elif profile.orcaslicer_settings:
                # Если метки не пришли, но были раньше - сохраняем существующие
                existing_fhub_id = profile.orcaslicer_settings.get("fhub_id")
                existing_fhub_source = profile.orcaslicer_settings.get("fhub_source")
                
                if existing_fhub_id and existing_fhub_source == "filamenthub":
                    updated_settings["fhub_id"] = existing_fhub_id
                    updated_settings["fhub_source"] = existing_fhub_source
                    logger.info(f"Preserving existing fhub_id and fhub_source for print profile {profile.id}")
            
            profile.orcaslicer_settings = updated_settings
        else:
            profile.orcaslicer_settings = profile.orcaslicer_settings or {}
        if payload.extra_metadata:
            profile.extra_metadata = payload.extra_metadata
        if payload.compatible_printers_condition:
            extra = dict(profile.extra_metadata or {})
            extra["compatible_printers_condition"] = payload.compatible_printers_condition
            profile.extra_metadata = extra
        profile.notes = payload.notes
        profile.is_official = profile.is_official if current_user.role != UserRole.ADMIN else profile.is_official
        await _sync_imported_print_profile_links(db=db, profile=profile)

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

    # Подготавливаем orcaslicer_settings с метками
    profile_orcaslicer_settings = dict(payload.orcaslicer_settings or {})
    
    # Добавляем метки FilamentHub для синхронизации
    profile_orcaslicer_settings["fhub_id"] = None  # Будет установлен после flush
    profile_orcaslicer_settings["fhub_source"] = "filamenthub"
    
    profile = PrintProfile(
        name=payload.name,
        slug=slug,
        description=payload.description,
        category=payload.category,
        owner_user_id=current_user.id,
        is_official=False,
        active=payload.active if payload.active is not None else True,
        source=payload.source or "user",
        vendor=payload.vendor,
        external_id=payload.external_id,
        setting_id=payload.setting_id,
        quality_tier=payload.quality_tier,
        default_nozzle=payload.default_nozzle,
        layer_height_mm=payload.layer_height_mm,
        compatible_printers=compatible_printers,
        compatible_filaments=compatible_filaments,
        orcaslicer_settings=profile_orcaslicer_settings,
        extra_metadata=_merge_extra_metadata(payload.extra_metadata, payload.compatible_printers_condition),
        notes=payload.notes,
    )
    db.add(profile)
    await db.flush()
    
    # Обновляем fhub_id после получения ID
    if profile.orcaslicer_settings:
        profile.orcaslicer_settings["fhub_id"] = profile.id
    await _sync_imported_print_profile_links(db=db, profile=profile)

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
        raise_error(status.HTTP_403_FORBIDDEN, ERR_EXPORT_PRINTER_DISABLED)
    
    query = select(PrinterProfile).options(selectinload(PrinterProfile.printer))
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
        raise_error(status.HTTP_403_FORBIDDEN, ERR_EXPORT_PRINT_DISABLED)
    
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


@router.get(
    "/presets/{preset_id}/info",
    status_code=status.HTTP_200_OK,
)
async def get_preset_info_file(
    preset_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> str:
    """
    Получить .info файл для пресета FilamentHub.
    
    Используется OrcaSlicer для записи меток после импорта пресета.
    Возвращает содержимое .info файла в формате plain text.
    """
    preset = await db.get(Preset, preset_id)
    if not preset:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_NOT_FOUND)

    # Проверяем права доступа (публичный пресет или свой пресет)
    if not preset.active and preset.user_id != current_user.id:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    
    # Генерируем .info файл
    from app.services.orcaslicer_exporter import preset_to_orcaslicer_info
    info_content = preset_to_orcaslicer_info(preset)
    
    # Возвращаем как plain text (не JSON)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=info_content, media_type="text/plain")


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
        raise_error(status.HTTP_403_FORBIDDEN, ERR_IMPORT_PRINTER_DISABLED)
    
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
        raise_error(status.HTTP_403_FORBIDDEN, ERR_IMPORT_PRINT_DISABLED)
    
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


async def _ensure_user_materials_brand(
    *,
    db: AsyncSession,
) -> int:
    """
    Найти или создать служебный бренд "User Materials" для черновиков.
    
    Возвращает ID бренда. Ищет по названию, чтобы не перезаписывать существующие бренды.
    """
    from app.services.slug_service import generate_unique_slug
    
    USER_MATERIALS_NAME = "User Materials"
    USER_MATERIALS_SLUG = "user-materials"
    USER_MATERIALS_DESCRIPTION = (
        "User-imported materials from OrcaSlicer (drafts). "
        "These materials are imported as inactive drafts and can be activated and assigned to your brand via the UI."
    )
    
    # Ищем бренд по названию (безопаснее, чем по ID)
    result = await db.execute(
        select(Brand).where(Brand.name == USER_MATERIALS_NAME)
    )
    brand = result.scalar_one_or_none()
    
    if brand:
        logger.debug(f"Found User Materials brand (id={brand.id}, name='{brand.name}')")
        return brand.id
    
    # Если не найден - создаём новый
    logger.info("User Materials brand not found, creating new one...")
    
    # Генерируем уникальный slug (на случай если slug "user-materials" уже занят)
    unique_slug = await generate_unique_slug(
        db=db,
        model=Brand,
        source=USER_MATERIALS_SLUG,
        fallback="user-materials-drafts",
    )
    
    brand = Brand(
        name=USER_MATERIALS_NAME,
        slug=unique_slug,
        description=USER_MATERIALS_DESCRIPTION,
        verified=False,
        active=True,
    )
    db.add(brand)
    try:
        await db.flush()  # Получаем ID бренда
    except IntegrityError:
        await db.rollback()
        # Race condition: другой запрос создал бренд параллельно
        result = await db.execute(
            select(Brand).where(Brand.slug == USER_MATERIALS_SLUG)
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info(f"Race condition resolved: found brand {existing.id}")
            return existing.id
        raise

    logger.info(f"Created User Materials brand (id={brand.id}, name='{brand.name}', slug='{brand.slug}')")
    return brand.id


async def _find_existing_filament(
    *,
    filament_name: str,
    material_type: str,
    db: AsyncSession,
) -> Filament | None:
    """
    Найти существующий филамент в базе по имени и типу материала.
    
    Ищет ВО ВСЕХ брендах, приоритет:
    1. Точное совпадение имени + material_type (активные)
    2. Нормализованное совпадение (без учёта регистра и лишних пробелов)
    
    Возвращает существующий филамент или None, если не найден.
    """
    if not filament_name:
        return None
    
    material_type = material_type or "PLA"
    
    # 1. Точное совпадение имени + material_type (активные филаменты)
    result = await db.execute(
        select(Filament).where(
            Filament.name == filament_name,
            Filament.material_type == material_type,
            Filament.active == True,  # Только активные (в каталоге)
        ).order_by(Filament.id.asc())  # Берём самый первый (старейший)
    )
    filament = result.scalar_one_or_none()
    
    if filament:
        logger.debug(
            f"Found existing active Filament (id={filament.id}, name='{filament_name}', "
            f"material_type='{material_type}', brand_id={filament.brand_id})"
        )
        return filament
    
    # 2. Нормализованное совпадение (без учёта регистра, убираем лишние пробелы)
    filament_name_normalized = _normalize_for_match(filament_name)
    material_type_normalized = _normalize_for_match(material_type)
    
    # Получаем все активные филаменты и проверяем нормализованные значения
    result = await db.execute(
        select(Filament).where(
            Filament.active == True,
        )
    )
    all_filaments = result.scalars().all()
    
    for f in all_filaments:
        f_name_normalized = _normalize_for_match(f.name)
        f_material_normalized = _normalize_for_match(f.material_type or "")
        
        if f_name_normalized == filament_name_normalized and f_material_normalized == material_type_normalized:
            logger.debug(
                f"Found existing active Filament by normalized match (id={f.id}, name='{f.name}', "
                f"material_type='{f.material_type}', brand_id={f.brand_id})"
            )
            return f
    
    return None


def _extract_values_from_orcaslicer_settings(settings: dict) -> dict:
    """Извлечь реальные значения параметров печати из OrcaSlicer JSON.

    OrcaSlicer хранит значения как массивы строк, например: ["220"], ["0.98"].
    Функция обрабатывает массивы, скаляры и строки.
    """
    def _first_float(val) -> float | None:
        """Извлечь первое числовое значение из значения OrcaSlicer."""
        if val is None:
            return None
        if isinstance(val, (list, tuple)):
            if not val:
                return None
            val = val[0]
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _first_int(val) -> int | None:
        """Извлечь первое целочисленное значение из значения OrcaSlicer."""
        f = _first_float(val)
        return int(f) if f is not None else None

    result: dict = {}

    # extruder_temp: nozzle_temperature → fallback nozzle_temperature_initial_layer
    ext_temp = _first_float(settings.get("nozzle_temperature"))
    if ext_temp is None:
        ext_temp = _first_float(settings.get("nozzle_temperature_initial_layer"))
    if ext_temp is not None:
        result["extruder_temp"] = ext_temp

    # bed_temp: hot_plate_temp → fallback cool_plate_temp → eng_plate_temp → textured_plate_temp
    bed_temp = _first_float(settings.get("hot_plate_temp"))
    if bed_temp is None:
        bed_temp = _first_float(settings.get("cool_plate_temp"))
    if bed_temp is None:
        bed_temp = _first_float(settings.get("eng_plate_temp"))
    if bed_temp is None:
        bed_temp = _first_float(settings.get("textured_plate_temp"))
    if bed_temp is not None:
        result["bed_temp"] = bed_temp

    # flow_rate: filament_flow_ratio (множитель 0.xx → процент)
    flow_ratio = _first_float(settings.get("filament_flow_ratio"))
    if flow_ratio is not None:
        # OrcaSlicer хранит как множитель (например 0.98), мы храним как процент (98)
        if flow_ratio <= 2.0:
            result["flow_rate"] = round(flow_ratio * 100, 1)
        else:
            result["flow_rate"] = flow_ratio  # Уже в процентах

    # fan_speed: fan_min_speed (это базовый fan speed в OrcaSlicer) → fallback fan_max_speed
    fan = _first_int(settings.get("fan_min_speed"))
    if fan is None:
        fan = _first_int(settings.get("fan_max_speed"))
    if fan is not None:
        result["fan_speed"] = fan

    # retraction_length: filament_retraction_length
    retract_len = _first_float(settings.get("filament_retraction_length"))
    if retract_len is not None:
        result["retraction_length"] = retract_len

    # retraction_speed: filament_retraction_speed
    retract_spd = _first_float(settings.get("filament_retraction_speed"))
    if retract_spd is not None:
        result["retraction_speed"] = retract_spd

    # print_speed, travel_speed, layer_height — НЕТ в филамент-пресетах OrcaSlicer
    # (они в print/printer profile, не в filament profile)

    return result


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

    # Логика определения типа пресета:
    # 1. [fh] или @fh в названии - наши пресеты (активные)
    # 2. Остальные - пользовательские пресеты из OrcaSlicer (черновики)
    #
    # Примечание: системные пресеты OrcaSlicer не отправляются (фильтруются в OrcaSlicer по preset.is_system)

    preset_name = payload.name or ""
    is_our_preset = "[fh]" in preset_name or "@fh" in preset_name

    if is_our_preset:
        logger.info(f"Importing our FilamentHub preset '{preset_name}' (will be active)")
    else:
        logger.info(f"Importing user filament preset '{preset_name}' as draft template")

    # Валидация текстовых полей
    is_valid, error_msg = await validate_text_field(payload.name, db, "preset_name")
    if not is_valid:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=payload.fhub_id,
            status="error",
            message=error_msg,
        )

    for field_value, label in [
        (payload.description, "preset_description"),
        (payload.notes, "preset_notes"),
        (payload.filament_name, "filament_name"),
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

    # =====================================================================
    # 1. НАЙТИ ПРЕСЕТ (ПЕРЕД филаментом — чтобы переиспользовать filament_id)
    # =====================================================================
    preset: Preset | None = None

    # Читаем .info файл (если есть в payload) — САМЫЙ ПРИОРИТЕТНЫЙ источник
    fhub_id_from_info = None
    if payload.info_content:
        for line in payload.info_content.split('\n'):
            line = line.strip()
            if line.startswith('sync_info = '):
                sync_info = line.split(' = ', 1)[1].strip()
                if sync_info.startswith('fhub:'):
                    parts = sync_info.split(':')
                    if len(parts) >= 2:
                        try:
                            fhub_id_from_info = int(parts[1])
                            logger.info(f"Extracted fhub_id from .info file: {fhub_id_from_info}")
                        except ValueError:
                            logger.warning(f"Failed to parse fhub_id from sync_info: {sync_info}")
                break

    # Метки из orcaslicer_settings
    orcaslicer_settings = payload.orcaslicer_settings or {}
    fhub_id_from_metadata = orcaslicer_settings.get("fhub_id")
    fhub_source = orcaslicer_settings.get("fhub_source")
    fhub_draft_id = orcaslicer_settings.get("fhub_draft_id")

    # Приоритет 1: fhub_id из .info файла (самый надежный)
    if fhub_id_from_info:
        preset = await db.get(Preset, fhub_id_from_info)
        if preset:
            if (
                preset.user_id != current_user.id
                and current_user.role != UserRole.ADMIN
            ):
                logger.info(
                    f"Preset fhub_id={fhub_id_from_info} (from .info) belongs to user_id={preset.user_id}, "
                    f"current user_id={current_user.id} — will create new preset instead"
                )
                preset = None
            else:
                logger.info(f"Found preset by fhub_id from .info file: {fhub_id_from_info} (preset.name='{preset.name}')")

    # Приоритет 2: fhub_id из payload (явное указание)
    if not preset and payload.fhub_id:
        preset = await db.get(Preset, payload.fhub_id)
        if preset:
            if (
                preset.user_id != current_user.id
                and current_user.role != UserRole.ADMIN
            ):
                logger.info(
                    f"Preset fhub_id={payload.fhub_id} belongs to user_id={preset.user_id}, "
                    f"current user_id={current_user.id} — will create new preset instead"
                )
                preset = None
            else:
                logger.info(f"Found preset by fhub_id from payload: {payload.fhub_id}")

    # Приоритет 3: fhub_id из orcaslicer_settings metadata
    if preset is None:
        if fhub_id_from_metadata and fhub_source == "filamenthub":
            try:
                # Parse FHUB-prefix format: "FHUB000013" → 13, or plain int "13" → 13
                fhub_id_str = str(fhub_id_from_metadata)
                if fhub_id_str.upper().startswith("FHUB"):
                    fhub_id_int = int(fhub_id_str[4:])
                else:
                    fhub_id_int = int(fhub_id_str)
                preset = await db.get(Preset, fhub_id_int)
                if preset:
                    if (
                        preset.user_id != current_user.id
                        and current_user.role != UserRole.ADMIN
                    ):
                        logger.info(
                            f"Preset fhub_id={fhub_id_int} (from metadata) belongs to user_id={preset.user_id}, "
                            f"current user_id={current_user.id} — will create new preset instead"
                        )
                        preset = None
                    else:
                        logger.info(f"Found preset by fhub_id from metadata: {fhub_id_int}")
            except (ValueError, TypeError):
                logger.warning(f"Invalid fhub_id in metadata: {fhub_id_from_metadata}")

        elif fhub_draft_id:
            result = await db.execute(
                select(Preset).where(
                    cast(Preset.orcaslicer_settings, JSONB)['fhub_draft_id'].astext == fhub_draft_id,
                    Preset.user_id == current_user.id,
                )
            )
            preset = result.scalars().first()
            if preset:
                logger.info(
                    f"Found draft preset by fhub_draft_id: {fhub_draft_id} "
                    f"(preset_id={preset.id}, name='{preset.name}')"
                )

    # Приоритет 4: external_id (OrcaSlicer's preset.setting_id)
    # Ищем БЕЗ привязки к filament_id — пресет мог поменять филамент
    if preset is None and payload.external_id:
        result = await db.execute(
            select(Preset).where(
                Preset.external_id == payload.external_id,
                Preset.user_id == current_user.id,
            )
        )
        preset = result.scalars().first()

        # Если найден промоутированный черновик — не пересоздавать
        if preset and preset.active and preset.filament_id and not is_our_preset:
            logger.info(
                f"Template '{payload.name}' external_id='{payload.external_id}' "
                f"already promoted to preset id={preset.id} name='{preset.name}' — skipping"
            )
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=preset.id,
                status="skipped",
                message="Template already promoted to FilamentHub preset",
            )

        if preset:
            logger.info(
                f"Found preset by external_id '{payload.external_id}' "
                f"(id={preset.id}, name='{preset.name}', active={preset.active})"
            )

    # Приоритет 5: Fallback — имя + user_id
    if preset is None and payload.name:
        result = await db.execute(
            select(Preset).where(
                Preset.name == payload.name,
                Preset.user_id == current_user.id,
            )
        )
        preset = result.scalars().first()

        if preset is None:
            clean_name = payload.name
            for suffix in (' [fh]', ' @fh', '[fh]', '@fh', ' @FilamentHub', '@FilamentHub'):
                clean_name = clean_name.replace(suffix, '')
            clean_name = clean_name.strip()
            if clean_name != payload.name:
                result = await db.execute(
                    select(Preset).where(
                        Preset.name == clean_name,
                        Preset.user_id == current_user.id,
                    )
                )
                preset = result.scalars().first()

        # Reverse match: DB name has "[fh]" suffix, payload.name doesn't
        if preset is None:
            suffixed_name = f"{payload.name} [fh]"
            result = await db.execute(
                select(Preset).where(
                    Preset.name == suffixed_name,
                    Preset.user_id == current_user.id,
                )
            )
            preset = result.scalars().first()
            if preset:
                logger.info(
                    f"Found preset by reverse [fh] name match: "
                    f"'{payload.name}' → '{preset.name}' (id={preset.id})"
                )

    # =====================================================================
    # 2. ОПРЕДЕЛИТЬ FILAMENT
    # Если пресет уже существует и привязан к филаменту — переиспользуем его
    # =====================================================================
    filament: Filament | None = None

    if preset and preset.filament_id:
        # Пресет найден и привязан к филаменту — проверяем что филамент ещё жив
        filament = await db.get(Filament, preset.filament_id)
        if filament:
            logger.info(
                f"Reusing existing filament from preset (filament_id={filament.id}, "
                f"name='{filament.name}') — skipping filament search"
            )
        else:
            logger.warning(
                f"Preset {preset.id} had filament_id={preset.filament_id} but filament was deleted. "
                f"Will search for a replacement."
            )

    # Если филамент ещё не определён — ищем/создаём
    if not filament:
        if payload.filament_id:
            # Явное указание filament_id в payload
            filament = await db.get(Filament, payload.filament_id)
            if filament is None:
                return OrcaSyncResult(
                    external_id=payload.external_id,
                    fhub_id=payload.fhub_id,
                    status="error",
                    message="Filament not found in FilamentHub",
                )
            if (
                filament.brand_id is not None
                and current_user.brand_id != filament.brand_id
                and current_user.role != UserRole.ADMIN
            ):
                return OrcaSyncResult(
                    external_id=payload.external_id,
                    fhub_id=payload.fhub_id,
                    status="error",
                    message=ERR_NO_PERMISSION,
                )
        elif payload.filament_name:
            # Определяем material_type: inherits приоритетнее payload (OrcaSlicer часто шлёт неточный тип)
            if payload.inherits:
                material_type = _extract_material_type_from_inherits(payload.inherits)
            else:
                material_type = payload.material_type or "PLA"

            if is_our_preset:
                clean_filament_name = payload.filament_name.replace(' [fh]', '').replace('[fh]', '').strip()

                existing_filament = await _find_existing_filament(
                    filament_name=clean_filament_name,
                    material_type=material_type,
                    db=db,
                )

                if existing_filament:
                    filament = existing_filament
                    logger.info(
                        f"Found existing Filament (id={filament.id}, name='{filament.name}') "
                        f"for preset '{payload.name}' (searched as '{clean_filament_name}')"
                    )
                else:
                    logger.warning(
                        f"Existing Filament not found for preset '{payload.name}' "
                        f"(searched: name='{clean_filament_name}', material_type='{material_type}'). "
                        f"Will try dedup guard or create new."
                    )
            else:
                # Черновики — НЕ создаем Filament
                filament = None
                logger.info(f"Preset '{payload.name}' is a draft - will create Preset without Filament")

    # Dedup guard: если филамент не найден, но is_our_preset — попробуем найти по brand + name
    if is_our_preset and not filament:
        if not current_user.brand_id:
            logger.warning(
                f"[fh] preset '{payload.name}' has no matching catalog filament "
                f"and user has no brand_id. Storing as draft."
            )
            is_our_preset = False
        else:
            filament_name = payload.filament_name or "Imported from OrcaSlicer"
            if payload.inherits:
                material_type = _extract_material_type_from_inherits(payload.inherits)
            else:
                material_type = payload.material_type or "PLA"

            # Dedup: проверяем нет ли уже такого филамента у бренда
            clean_name = filament_name.replace(' [fh]', '').replace('[fh]', '').strip()
            result = await db.execute(
                select(Filament).where(
                    Filament.name == clean_name,
                    Filament.brand_id == current_user.brand_id,
                ).order_by(Filament.id.asc())
            )
            existing_brand_filament = result.scalars().first()

            if existing_brand_filament:
                filament = existing_brand_filament
                logger.info(
                    f"Dedup guard: found existing filament (id={filament.id}, name='{filament.name}') "
                    f"for brand_id={current_user.brand_id} — reusing instead of creating duplicate"
                )
            else:
                filament_slug = await generate_unique_slug(
                    db=db,
                    model=Filament,
                    source=clean_name,
                    fallback=f"filament-{current_user.id}-{int(datetime.now(timezone.utc).timestamp())}",
                )

                filament = Filament(
                    name=clean_name,
                    slug=filament_slug,
                    material_type=material_type,
                    brand_id=current_user.brand_id,
                    diameter=1.75,
                    active=True,
                )
                db.add(filament)
                await db.flush()

                logger.info(
                    f"Created Filament (id={filament.id}, name='{clean_name}') "
                    f"for preset '{payload.name}'"
                )

    # Обновляем external_id если его нет
    if preset and not preset.external_id and payload.external_id:
        preset.external_id = payload.external_id
        logger.info(f"Updated preset {preset.id} external_id to {payload.external_id}")

    # Приоритет 6: Проверка derived-меток (anti-cycle)
    # Если пресет не найден — возможно, черновик уже был промоутирован в FH-пресет.
    # Проверяем, есть ли активный пресет, созданный из шаблона с таким же external_id или draft_id.
    if preset is None and not is_our_preset:
        derived_preset = None

        # 5a. Проверяем по derived_from_external_id
        if payload.external_id:
            result = await db.execute(
                select(Preset).where(
                    cast(Preset.orcaslicer_settings, JSONB)['derived_from_external_id'].astext == payload.external_id,
                    Preset.user_id == current_user.id,
                    Preset.active == True,
                )
            )
            derived_preset = result.scalars().first()

        # 5b. Проверяем по derived_from_draft_id (для шаблонов без external_id)
        if derived_preset is None:
            # Генерируем draft_id так же, как при создании черновика
            if fhub_draft_id:
                check_draft_id = fhub_draft_id
            elif payload.external_id:
                check_draft_id = f"draft_{current_user.id}_{payload.external_id}"
            else:
                name_hash = hashlib.md5((payload.name or "").encode()).hexdigest()[:8]
                check_draft_id = f"draft_{current_user.id}_{name_hash}"

            result = await db.execute(
                select(Preset).where(
                    cast(Preset.orcaslicer_settings, JSONB)['derived_from_draft_id'].astext == check_draft_id,
                    Preset.user_id == current_user.id,
                    Preset.active == True,
                )
            )
            derived_preset = result.scalars().first()

        if derived_preset:
            logger.info(
                f"Skipping template '{payload.name}' — already promoted to "
                f"FH preset id={derived_preset.id} name='{derived_preset.name}'"
            )
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=derived_preset.id,
                status="skipped",
                message="Template already promoted to FilamentHub preset",
            )

    if preset:
        # Обновляем существующий пресет
        # Проверяем конфликты (timestamp-based resolution)
        # Сравниваем версии: обновляем только если версия из OrcaSlicer новее
        should_update = True
        
        # Получаем timestamp из FilamentHub (preset.updated_at)
        preset_db_updated_at = preset.updated_at
        
        # Получаем timestamp из OrcaSlicer (из payload или orcaslicer_settings)
        payload_updated_at = None
        
        # 1. Проверяем updated_at в orcaslicer_settings
        if payload.orcaslicer_settings:
            payload_updated_at = payload.orcaslicer_settings.get("updated_at")
        
        # 2. Если нет updated_at в orcaslicer_settings - сравниваем содержимое пресета
        # OrcaSlicer НЕ отправляет updated_at в JSON (только в .info файле)
        # Сравниваем весь orcaslicer_settings целиком (включая start_gcode, end_gcode и все параметры)
        if not payload_updated_at:
            # Нормализуем JSON для сравнения (сортируем ключи, убираем None)
            def normalize_for_hash(data: dict | None) -> str:
                if not data:
                    return ""
                # Убираем None значения, сортируем ключи
                cleaned = {k: v for k, v in data.items() if v is not None}
                return json.dumps(cleaned, sort_keys=True, ensure_ascii=False)
            
            # Сравниваем orcaslicer_settings целиком
            payload_settings_hash = hashlib.md5(
                normalize_for_hash(payload.orcaslicer_settings).encode('utf-8')
            ).hexdigest()
            
            preset_settings_hash = hashlib.md5(
                normalize_for_hash(preset.orcaslicer_settings).encode('utf-8')
            ).hexdigest()
            
            settings_changed = payload_settings_hash != preset_settings_hash
            
            # Также проверяем базовые параметры (на случай если они не в orcaslicer_settings)
            basic_params_changed = (
                (payload.extruder_temp is not None and preset.extruder_temp != payload.extruder_temp) or
                (payload.bed_temp is not None and preset.bed_temp != payload.bed_temp) or
                (payload.print_speed is not None and preset.print_speed != payload.print_speed) or
                (payload.name and preset.name != payload.name.replace(' @fh', '').replace('@fh', '').replace(' @FilamentHub', '').replace('@FilamentHub', '').strip())
            )
            
            if settings_changed or basic_params_changed:
                should_update = True
                logger.info(
                    f"Preset {preset.id} will update: content changed "
                    f"(settings_changed={settings_changed}, basic_params_changed={basic_params_changed})"
                )
            else:
                should_update = False
                logger.debug(
                    f"Preset {preset.id} not updated: no changes detected "
                    f"(name='{preset.name}', external_id={preset.external_id})"
                )
        else:
            # Есть updated_at в payload - сравниваем
            try:
                payload_dt = datetime.fromisoformat(payload_updated_at.replace("Z", "+00:00"))
                
                # Сравниваем с preset.updated_at
                if preset_db_updated_at:
                    # Убеждаемся что оба datetime с timezone
                    preset_dt = preset_db_updated_at
                    if preset_dt.tzinfo is None:
                        preset_dt = preset_dt.replace(tzinfo=timezone.utc)
                    if payload_dt.tzinfo is None:
                        payload_dt = payload_dt.replace(tzinfo=timezone.utc)
                    
                    if payload_dt > preset_dt:
                        # OrcaSlicer версия новее - обновляем
                        should_update = True
                        logger.debug(
                            f"Preset {preset.id} will update: OrcaSlicer is newer "
                            f"(OrcaSlicer: {payload_dt}, FilamentHub: {preset_db_updated_at})"
                        )
                    else:
                        # FilamentHub версия новее или равна - не обновляем
                        should_update = False
                        logger.info(
                            f"Preset {preset.id} not updated: FilamentHub version is newer or equal "
                            f"(FilamentHub: {preset_db_updated_at}, OrcaSlicer: {payload_dt})"
                        )
                else:
                    # Нет preset.updated_at - обновляем
                    should_update = True
            except (ValueError, AttributeError) as e:
                logger.warning(f"Failed to parse updated_at timestamp '{payload_updated_at}': {e}")
                # Если не удалось распарсить, не обновляем (для безопасности)
                should_update = False
        
        # КРИТИЧНО: Убеждаемся, что запись в user_saved_presets существует (даже если пресет не обновляется)
        # Это важно для пресетов, импортированных до добавления логики user_saved_presets
        from app.models.user_saved_preset import UserSavedPreset
        saved_preset_check = await db.execute(
            select(UserSavedPreset).where(
                UserSavedPreset.user_id == current_user.id,
                UserSavedPreset.preset_id == preset.id,
            )
        )
        existing_saved_preset = saved_preset_check.scalar_one_or_none()
        
        if not existing_saved_preset:
            # Создаём запись в user_saved_presets если её нет
            saved_preset = UserSavedPreset(
                user_id=current_user.id,
                preset_id=preset.id,
                sync=True,  # По умолчанию включаем синхронизацию
            )
            db.add(saved_preset)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                logger.debug(f"user_saved_preset already exists (race condition) for preset {preset.id}")
            else:
                logger.info(f"Created user_saved_preset record for existing preset {preset.id}")
        else:
            logger.debug(f"user_saved_preset record already exists for preset {preset.id}")

        if should_update:
            # Убираем постфиксы FilamentHub из названия для отображения на сайте
            clean_name = payload.name if payload.name else preset.name
            for suffix in (' [fh]', ' @fh', '[fh]', '@fh', ' @FilamentHub', '@FilamentHub'):
                clean_name = clean_name.replace(suffix, '')
            preset.name = clean_name
            # Обновляем filament_id только для наших пресетов (не для черновиков)
            # КРИТИЧНО: Для черновиков filament_id остается None до активации пользователем
            if is_our_preset and filament and preset.filament_id != filament.id:
                logger.info(
                    f"Updating preset {preset.id} filament_id from {preset.filament_id} to {filament.id} "
                    f"(filament: '{filament.name}')"
                )
                preset.filament_id = filament.id
            if payload.description is not None:
                preset.description = payload.description
            # Извлекаем реальные значения из orcaslicer_settings для fallback
            extracted = _extract_values_from_orcaslicer_settings(payload.orcaslicer_settings or {})
            if payload.extruder_temp is not None:
                preset.extruder_temp = payload.extruder_temp
            elif extracted.get("extruder_temp") is not None:
                preset.extruder_temp = extracted["extruder_temp"]
            if payload.bed_temp is not None:
                preset.bed_temp = payload.bed_temp
            elif extracted.get("bed_temp") is not None:
                preset.bed_temp = extracted["bed_temp"]
            if payload.print_speed is not None:
                preset.print_speed = payload.print_speed
            elif extracted.get("print_speed") is not None:
                preset.print_speed = extracted["print_speed"]
            if payload.travel_speed is not None:
                preset.travel_speed = payload.travel_speed
            elif extracted.get("travel_speed") is not None:
                preset.travel_speed = extracted["travel_speed"]
            if payload.layer_height is not None:
                preset.layer_height = payload.layer_height
            elif extracted.get("layer_height") is not None:
                preset.layer_height = extracted["layer_height"]
            if payload.first_layer_height is not None:
                preset.first_layer_height = payload.first_layer_height
            elif extracted.get("first_layer_height") is not None:
                preset.first_layer_height = extracted["first_layer_height"]
            if payload.flow_rate is not None:
                preset.flow_rate = payload.flow_rate
            elif extracted.get("flow_rate") is not None:
                preset.flow_rate = extracted["flow_rate"]
            if payload.fan_speed is not None:
                preset.fan_speed = payload.fan_speed
            elif extracted.get("fan_speed") is not None:
                preset.fan_speed = extracted["fan_speed"]
            if payload.retraction_length is not None:
                preset.retraction_length = payload.retraction_length
            elif extracted.get("retraction_length") is not None:
                preset.retraction_length = extracted["retraction_length"]
            if payload.retraction_speed is not None:
                preset.retraction_speed = payload.retraction_speed
            elif extracted.get("retraction_speed") is not None:
                preset.retraction_speed = extracted["retraction_speed"]
            if payload.orcaslicer_settings:
                # Сохраняем метки FilamentHub при обновлении
                # Если это черновик - сохраняем fhub_draft_id
                # Если это наш пресет - сохраняем fhub_id и fhub_source
                updated_settings = dict(payload.orcaslicer_settings)

                # Сохраняем существующие метки, если они есть
                if preset.orcaslicer_settings:
                    existing_fhub_draft_id = preset.orcaslicer_settings.get("fhub_draft_id")
                    existing_fhub_id = preset.orcaslicer_settings.get("fhub_id")
                    existing_fhub_source = preset.orcaslicer_settings.get("fhub_source")

                    # Если это черновик - сохраняем fhub_draft_id
                    if existing_fhub_draft_id and not preset.active:
                        updated_settings["fhub_draft_id"] = existing_fhub_draft_id
                    # Если это наш пресет - сохраняем метки
                    elif existing_fhub_id and existing_fhub_source == "filamenthub":
                        updated_settings["fhub_id"] = existing_fhub_id
                        updated_settings["fhub_source"] = existing_fhub_source
                    # Если это наш пресет, но меток еще нет - добавляем их
                    elif is_our_preset and not existing_fhub_id:
                        updated_settings["fhub_id"] = str(preset.id)
                        updated_settings["fhub_source"] = "filamenthub"
                        logger.info(f"Added fhub_id and fhub_source to preset {preset.id} (found by cleaned name)")
                
                preset.orcaslicer_settings = updated_settings
            # Примечание: Preset НЕ имеет поля notes, сохраняем в orcaslicer_settings если нужно
            if payload.notes is not None:
                if preset.orcaslicer_settings is None:
                    preset.orcaslicer_settings = {}
                preset.orcaslicer_settings["notes"] = payload.notes
            if payload.source:
                preset.source = payload.source
            if payload.external_id:
                preset.external_id = payload.external_id
            # Для наших пресетов всегда active=True (это пресеты из каталога)
            if is_our_preset and not preset.active:
                preset.active = True
                logger.info(f"Activated preset {preset.id} (found by cleaned name for [fh] preset)")
            # Обновляем updated_at вручную, чтобы отметить, что пресет был изменен
            preset.updated_at = datetime.now(timezone.utc)
            await _apply_orca_import_moderation(preset, filament, db)

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
        # Перед созданием нового пресета проверим, нет ли уже существующего с таким же именем
        # Для пресетов с Filament - ищем по filament_id
        # Для черновиков - ищем по filament_id IS NULL

        if filament:
            result = await db.execute(
                select(Preset).where(
                    Preset.filament_id == filament.id,
                    Preset.name == payload.name,
                    Preset.user_id == current_user.id,
                )
            )
        else:
            # Для черновиков ищем по filament_id IS NULL
            result = await db.execute(
                select(Preset).where(
                    Preset.filament_id.is_(None),
                    Preset.name == payload.name,
                    Preset.user_id == current_user.id,
                )
            )
        existing_preset = result.scalar_one_or_none()

        if existing_preset:
            # Обновляем существующий preset вместо создания нового
            logger.info(f"Found existing preset {existing_preset.id} for filament {filament.id} and name '{payload.name}', updating instead of creating")
            preset = existing_preset

            # Обновляем поля (аналогично выше)
            # Стрипаем постфиксы FilamentHub из имени
            update_name = payload.name or preset.name
            for suffix in (' [fh]', ' @fh', '[fh]', '@fh', ' @FilamentHub', '@FilamentHub'):
                update_name = update_name.replace(suffix, '')
            preset.name = update_name
            if payload.description is not None:
                preset.description = payload.description
            # Извлекаем реальные значения из orcaslicer_settings для fallback
            extracted = _extract_values_from_orcaslicer_settings(payload.orcaslicer_settings or {})
            if payload.extruder_temp is not None:
                preset.extruder_temp = payload.extruder_temp
            elif extracted.get("extruder_temp") is not None:
                preset.extruder_temp = extracted["extruder_temp"]
            if payload.bed_temp is not None:
                preset.bed_temp = payload.bed_temp
            elif extracted.get("bed_temp") is not None:
                preset.bed_temp = extracted["bed_temp"]
            if payload.print_speed is not None:
                preset.print_speed = payload.print_speed
            elif extracted.get("print_speed") is not None:
                preset.print_speed = extracted["print_speed"]
            if payload.travel_speed is not None:
                preset.travel_speed = payload.travel_speed
            elif extracted.get("travel_speed") is not None:
                preset.travel_speed = extracted["travel_speed"]
            if payload.layer_height is not None:
                preset.layer_height = payload.layer_height
            elif extracted.get("layer_height") is not None:
                preset.layer_height = extracted["layer_height"]
            if payload.first_layer_height is not None:
                preset.first_layer_height = payload.first_layer_height
            elif extracted.get("first_layer_height") is not None:
                preset.first_layer_height = extracted["first_layer_height"]
            if payload.flow_rate is not None:
                preset.flow_rate = payload.flow_rate
            elif extracted.get("flow_rate") is not None:
                preset.flow_rate = extracted["flow_rate"]
            if payload.fan_speed is not None:
                preset.fan_speed = payload.fan_speed
            elif extracted.get("fan_speed") is not None:
                preset.fan_speed = extracted["fan_speed"]
            if payload.retraction_length is not None:
                preset.retraction_length = payload.retraction_length
            elif extracted.get("retraction_length") is not None:
                preset.retraction_length = extracted["retraction_length"]
            if payload.retraction_speed is not None:
                preset.retraction_speed = payload.retraction_speed
            elif extracted.get("retraction_speed") is not None:
                preset.retraction_speed = extracted["retraction_speed"]
            if payload.orcaslicer_settings:
                # Сохраняем метки FilamentHub при обновлении
                updated_settings = dict(payload.orcaslicer_settings)

                # Сохраняем существующие метки, если они есть
                if preset.orcaslicer_settings:
                    existing_fhub_draft_id = preset.orcaslicer_settings.get("fhub_draft_id")
                    existing_fhub_id = preset.orcaslicer_settings.get("fhub_id")
                    existing_fhub_source = preset.orcaslicer_settings.get("fhub_source")
                    
                    # Если это черновик - сохраняем fhub_draft_id
                    if existing_fhub_draft_id and not preset.active:
                        updated_settings["fhub_draft_id"] = existing_fhub_draft_id
                    # Если это наш пресет - сохраняем метки
                    elif existing_fhub_id and existing_fhub_source == "filamenthub":
                        updated_settings["fhub_id"] = existing_fhub_id
                        updated_settings["fhub_source"] = existing_fhub_source
                
                preset.orcaslicer_settings = updated_settings
            if payload.external_id:
                preset.external_id = payload.external_id
            # КРИТИЧНО: НЕ меняем sync_enabled автоматически! Это исключительно пользовательский выбор.
            await _apply_orca_import_moderation(preset, filament, db)

            await db.commit()
            await db.refresh(preset)

            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=preset.id,
                status="updated",
                message="Preset updated (existing found by name)",
            )

        # Создаем новый пресет (черновик)
        # Примечание: Preset не имеет поля slug (только Filament имеет slug)

        # Извлекаем реальные значения из orcaslicer_settings
        extracted = _extract_values_from_orcaslicer_settings(payload.orcaslicer_settings or {})
        extruder_temp = payload.extruder_temp or extracted.get("extruder_temp") or 200.0
        bed_temp = payload.bed_temp or extracted.get("bed_temp") or 60.0
        print_speed = payload.print_speed or extracted.get("print_speed") or 50.0
        travel_speed = payload.travel_speed or extracted.get("travel_speed")

        # Убираем постфиксы FilamentHub из названия для отображения на сайте
        clean_name = payload.name if payload.name else 'Unnamed Preset'
        for suffix in (' [fh]', ' @fh', '[fh]', '@fh', ' @FilamentHub', '@FilamentHub'):
            clean_name = clean_name.replace(suffix, '')

        # Подготавливаем orcaslicer_settings с метками
        preset_orcaslicer_settings = dict(payload.orcaslicer_settings or {})
        
        # Если это не наш пресет (черновик) - добавляем fhub_draft_id для предотвращения дубликатов
        if not is_our_preset:
            # Генерируем уникальный ID черновика
            # Используем хеш имени вместо 'new' для уникальности при null external_id
            if fhub_draft_id:
                draft_id = fhub_draft_id
            elif payload.external_id:
                draft_id = f"draft_{current_user.id}_{payload.external_id}"
            else:
                name_hash = hashlib.md5((payload.name or "").encode()).hexdigest()[:8]
                draft_id = f"draft_{current_user.id}_{name_hash}"
            preset_orcaslicer_settings["fhub_draft_id"] = draft_id
            logger.debug(f"Adding fhub_draft_id={draft_id} to new draft preset")

            # Store orphaned preset metadata if present
            if payload.orphaned:
                preset_orcaslicer_settings["orphaned"] = True
                preset_orcaslicer_settings["orphaned_reason"] = payload.orphaned_reason or "parent_not_found"
                if payload.original_inherits:
                    preset_orcaslicer_settings["original_inherits"] = payload.original_inherits
        else:
            # Для наших пресетов добавляем fhub_id и fhub_source
            preset_orcaslicer_settings["fhub_id"] = None  # Будет установлен после flush
            preset_orcaslicer_settings["fhub_source"] = "filamenthub"

        preset = Preset(
            name=clean_name,
            description=payload.description,
            filament_id=filament.id if filament else None,  # КРИТИЧНО: Для черновиков filament_id=None
            user_id=current_user.id,
            extruder_temp=extruder_temp,
            bed_temp=bed_temp,
            print_speed=print_speed,
            travel_speed=travel_speed,
            layer_height=payload.layer_height or extracted.get("layer_height"),
            first_layer_height=payload.first_layer_height or extracted.get("first_layer_height"),
            flow_rate=payload.flow_rate or extracted.get("flow_rate"),
            fan_speed=payload.fan_speed if payload.fan_speed is not None else extracted.get("fan_speed"),
            retraction_length=payload.retraction_length or extracted.get("retraction_length"),
            retraction_speed=payload.retraction_speed or extracted.get("retraction_speed"),
            orcaslicer_settings=preset_orcaslicer_settings,
            is_official=False,
            # ВАЖНО: Для пресетов с @FilamentHub всегда active=True (это наши пресеты из каталога)
            # Для остальных - active=False (черновики пользователя)
            active=True if is_our_preset else (payload.active if payload.active is not None else False),
            moderation_status=PresetModerationStatus.PENDING,
            source=payload.source or "orcaslicer",
            external_id=payload.external_id,
            # КРИТИЧНО: Этого поля больше НЕТ в модели Preset!
            # sync теперь управляется через user_saved_presets
            # Запись в user_saved_presets создаётся автоматически при создании пресета (см. presets.py:249)
            # Примечание: Preset НЕ имеет поля notes, сохраняем в orcaslicer_settings если нужно
        )
        db.add(preset)
        await db.flush()  # Получаем ID пресета
        
        # КРИТИЧНО: Создаём запись в user_saved_presets (аналогично presets.py:249)
        # Это нужно для единой логики синхронизации - все пресеты в "Профили филамента" хранят sync в user_saved_presets
        from app.models.user_saved_preset import UserSavedPreset
        saved_preset = UserSavedPreset(
            user_id=current_user.id,
            preset_id=preset.id,
            sync=True,  # По умолчанию синхронизация включена (пользователь явно экспортировал пресет)
        )
        db.add(saved_preset)
        
        # Обновляем fhub_id для наших пресетов после получения ID
        if is_our_preset:
            if preset.orcaslicer_settings is None:
                preset.orcaslicer_settings = {}
            # ВАЖНО: Сохраняем как строку для консистентности с JSON
            preset.orcaslicer_settings["fhub_id"] = str(preset.id)
            preset.orcaslicer_settings["fhub_source"] = "filamenthub"

        await _apply_orca_import_moderation(preset, filament, db)

        # Enrich draft presets with material defaults
        if not is_our_preset:
            from app.services.preset_enrichment_service import enrich_preset
            try:
                enrich_preset(preset)
            except Exception:
                logger.exception(f"Failed to enrich preset id={preset.id}")

        if filament:
            logger.info(
                f"🆕 Created new Preset (id={preset.id}, name='{payload.name}') "
                f"for Filament '{filament.name}' (id={filament.id}) from OrcaSlicer. "
                f"This is a {'active' if is_our_preset else 'draft'} preset."
            )
        else:
            logger.info(
                f"🆕 Created new draft Preset (id={preset.id}, name='{payload.name}') "
                f"from OrcaSlicer without Filament. "
                f"User can activate it by selecting/creating a Filament in UI."
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
    """Import or update filament presets submitted by OrcaSlicer.

    Импортирует ТОЛЬКО пользовательские пресеты (с постфиксом @FilamentHub).
    Системные пресеты OrcaSlicer пропускаются, черновики не создаются автоматически.
    """
    try:
        logger.info(f"Import filament presets request: user_id={current_user.id}, profiles_count={len(payload.profiles)}")
        
        # Проверяем разрешение на импорт filament presets
        if not current_user.allow_filament_presets_import:
            raise_error(status.HTTP_403_FORBIDDEN, ERR_IMPORT_FILAMENT_DISABLED)

        # Лимит на количество профилей (50 для MVP)
        MAX_PROFILES_PER_REQUEST = 50
        if len(payload.profiles) > MAX_PROFILES_PER_REQUEST:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ERR_TOO_MANY_PROFILES,
                {"count": len(payload.profiles), "max": MAX_PROFILES_PER_REQUEST},
            )

        results: list[OrcaSyncResult] = []

        for idx, item in enumerate(payload.profiles):
            try:
                logger.debug(f"Processing filament preset {idx+1}/{len(payload.profiles)}: name='{item.name}', external_id='{item.external_id}'")
                result = await _upsert_filament_preset(
                    payload=item,
                    current_user=current_user,
                    db=db,
                )
                logger.debug(f"Filament preset {idx+1} processed: status={result.status}, fhub_id={result.fhub_id}")
            except HTTPException as exc:
                logger.warning(f"Failed to sync filament preset {idx+1} (name='{item.name}'): {exc.detail}")
                result = OrcaSyncResult(
                    external_id=getattr(item, "external_id", None),
                    fhub_id=getattr(item, "fhub_id", None),
                    status="error",
                    message=exc.detail,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"Unexpected error while syncing filament preset {idx+1} (name='{getattr(item, 'name', 'unknown')}')")
                result = OrcaSyncResult(
                    external_id=getattr(item, "external_id", None),
                    fhub_id=getattr(item, "fhub_id", None),
                    status="error",
                    message=f"Unexpected error: {exc}",
                )
            results.append(result)

        await db.commit()
        return FilamentPresetSyncResponse(results=results)
    except HTTPException:
        # Пробрасываем HTTPException как есть
        raise
    except Exception as exc:  # noqa: BLE001
        # Ловим все остальные исключения и возвращаем 500 с деталями
        logger.exception("Critical error in import_filament_presets endpoint")
        await db.rollback()
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_INTERNAL_ERROR)


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
    title = "deleted_presets_detected"
    message = "deleted_presets_detected_message"

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
            existing_notification.title = "deleted_presets_detected"
            existing_notification.message = "deleted_presets_detected_message"
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
        raise_error(404, ERR_NOTIFICATION_NOT_FOUND)

    # Получаем список удалённых пресетов из extra_data
    if not notification.extra_data:
        raise_error(400, ERR_NO_NOTIFICATION_DATA)
    deleted_presets = notification.extra_data.get("deleted_presets", [])

    # Фильтруем пресеты по выбранным preset_ids (если apply_to_all=False)
    if action.preset_ids:
        deleted_presets = [p for p in deleted_presets if p["preset_id"] in action.preset_ids]
    elif not action.apply_to_all:
        # Если не указаны preset_ids и не apply_to_all, возвращаем ошибку
        raise_error(400, ERR_PRESET_IDS_REQUIRED)

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
        # Пропускаем (не удаляем маппинг, но НЕ меняем sync_enabled автоматически!)
        # КРИТИЧНО: sync_enabled меняется ТОЛЬКО пользователем в UI, никогда автоматически!
        # Пользователь сам решит, включать или выключать синхронизацию для этого пресета
        processed_count = len(deleted_presets)
        
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


# ══════════════════════════════════════════════════════════════
# SyncPlan & Validation endpoints (Phase 1 Refactoring)
# ══════════════════════════════════════════════════════════════

from app.schemas.sync_plan import (
    SyncPlanRequest,
    SyncPlanResponse,
    SyncCompleteRequest,
    SyncStatusResponse,
    DeletedPresetsRequest as SyncDeletedPresetsRequest,
    DeletedPresetsResponse as SyncDeletedPresetsResponse,
)
from app.schemas.preset_validation import (
    ParentPresetValidationRequest,
    ParentPresetValidationResponse,
    PresetBatchValidationRequest,
    PresetBatchValidationResponse,
)
from app.services.sync_orchestrator import SyncOrchestrator
from app.services.orcaslicer_validator import (
    validate_parent_preset,
    validate_preset_batch,
)


@router.post("/orcaslicer/sync-plan", response_model=SyncPlanResponse)
async def create_sync_plan(
    request: SyncPlanRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Генерирует план синхронизации для устройства."""
    orchestrator = SyncOrchestrator(db)
    plan = await orchestrator.create_sync_plan(
        user_id=current_user.id,
        device_fingerprint=request.device_fingerprint,
        preset_type=request.preset_type,
        force_full_sync=request.force_full_sync,
        orcaslicer_version=request.orcaslicer_version,
    )
    await db.commit()
    return SyncPlanResponse(**plan)


@router.post("/orcaslicer/sync-complete")
async def complete_sync(
    request: SyncCompleteRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Подтверждение завершения синхронизации — инкрементирует sync_version."""
    orchestrator = SyncOrchestrator(db)
    device = await orchestrator.complete_sync(
        user_id=current_user.id,
        device_fingerprint=request.device_fingerprint,
    )
    await db.commit()
    return {"sync_version": device.sync_version, "last_sync_at": device.last_sync_at.isoformat()}


@router.get("/orcaslicer/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(
    device_fingerprint: Annotated[str, Query(...)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Получить статус последней синхронизации устройства."""
    orchestrator = SyncOrchestrator(db)
    status = await orchestrator.get_sync_status(
        user_id=current_user.id,
        device_fingerprint=device_fingerprint,
    )
    return SyncStatusResponse(**status)


@router.post("/orcaslicer/validate-parent", response_model=ParentPresetValidationResponse)
async def validate_parent(
    request: ParentPresetValidationRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Валидация родительского пресета OrcaSlicer."""
    result = await validate_parent_preset(
        inherits=request.inherits,
        orcaslicer_version=request.orcaslicer_version,
        db=db,
    )
    return ParentPresetValidationResponse(**result.to_dict())


@router.post("/orcaslicer/validate-batch", response_model=PresetBatchValidationResponse)
async def validate_batch(
    request: PresetBatchValidationRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Валидация нескольких пресетов за один запрос."""
    presets_data = [p.model_dump() for p in request.presets]
    results = await validate_preset_batch(presets_data, db)

    result_items = [r.to_dict() for r in results]
    valid_count = sum(1 for r in results if r.is_valid)

    return PresetBatchValidationResponse(
        results=result_items,
        total=len(results),
        valid_count=valid_count,
        error_count=len(results) - valid_count,
    )


@router.post("/orcaslicer/deleted-presets", response_model=SyncDeletedPresetsResponse)
async def get_deleted_presets(
    request: SyncDeletedPresetsRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Получить список пресетов удалённых на сервере."""
    orchestrator = SyncOrchestrator(db)
    deleted = await orchestrator.get_deleted_presets(
        user_id=current_user.id,
        device_fingerprint=request.device_fingerprint,
        preset_type=request.preset_type,
    )
    return SyncDeletedPresetsResponse(deleted=deleted)


@router.get("/orcaslicer/spool-preset-mapping")
async def spool_preset_mapping(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    spool_ids: str = Query(..., description="Comma-separated spool IDs"),
):
    """Resolve spool IDs to OrcaSlicer preset setting_ids.

    Used by MoonrakerPrinterAgent to map HH gate spool assignments
    to the correct installed filament preset during AMS sync.
    """
    id_list = [int(x) for x in spool_ids.split(",") if x.strip().isdigit()]
    if not id_list:
        return {"mapping": {}}

    spool_result = await db.execute(
        select(UserSpool.id, UserSpool.filament_id)
        .where(UserSpool.id.in_(id_list), UserSpool.user_id == current_user.id)
    )
    spool_to_filament: dict[int, int] = {}
    filament_ids: set[int] = set()
    for spool_id, filament_id in spool_result.all():
        if filament_id is not None:
            spool_to_filament[spool_id] = filament_id
            filament_ids.add(filament_id)

    filament_to_preset: dict[int, int] = {}
    if filament_ids:
        preset_result = await db.execute(
            select(Preset.id, Preset.filament_id)
            .where(
                Preset.filament_id.in_(filament_ids),
                Preset.active == True,
                Preset.moderation_status == PresetModerationStatus.APPROVED,
            )
            .order_by(Preset.is_official.desc(), Preset.usage_count.desc())
        )
        for preset_id, filament_id in preset_result.all():
            if filament_id not in filament_to_preset:
                filament_to_preset[filament_id] = preset_id

    mapping: dict[str, dict | None] = {}
    for sid in id_list:
        fil_id = spool_to_filament.get(sid)
        preset_id = filament_to_preset.get(fil_id) if fil_id else None
        if preset_id is not None:
            mapping[str(sid)] = {
                "setting_id": f"FHUB{preset_id:06d}",
                "preset_id": preset_id,
            }
        else:
            mapping[str(sid)] = None

    return {"mapping": mapping}
