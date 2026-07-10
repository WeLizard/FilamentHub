"""Экспорт системных профилей принтеров/печати в формат OrcaSlicer."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.print_profile import PrintProfile
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.services.profile_validator import (
    log_validation_result,
    validate_print_profile,
    validate_printer_profile,
)

logger = logging.getLogger(__name__)


def _coerce_list(value: Any) -> list[str] | None:
    """Преобразовать значение в список строк (формат OrcaSlicer)."""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _merge_settings(base: Mapping[str, Any] | None) -> dict[str, Any]:
    """Скопировать словарь настроек, игнорируя None."""
    return dict(base or {})


def _parse_printable_area_point(raw_point: Any) -> tuple[float, float] | None:
    """Разобрать точку printable_area формата XxY."""
    if raw_point is None:
        return None

    normalized = str(raw_point).strip().replace("X", "x")
    if not normalized:
        return None

    x_raw, separator, y_raw = normalized.partition("x")
    if not separator:
        return None

    try:
        return float(x_raw), float(y_raw)
    except (TypeError, ValueError):
        return None


def _normalize_printable_area(area: Any) -> list[str] | None:
    """Нормализовать printable_area в Orca-совместимый список точек."""
    if not area:
        return None

    if isinstance(area, list):
        normalized_points: list[str] = []
        for raw_point in area:
            parsed = _parse_printable_area_point(raw_point)
            if parsed is None:
                return None
            x, y = parsed
            normalized_points.append(f"{x:g}x{y:g}")

        return normalized_points or None

    if isinstance(area, dict):
        if "x" in area and "y" in area:
            x_size = float(area.get("x", 0))
            y_size = float(area.get("y", 0))
            return [
                "0x0",
                f"{x_size:g}x0",
                f"{x_size:g}x{y_size:g}",
                f"0x{y_size:g}",
            ]

        if "x_min" in area and "y_min" in area and "x_max" in area and "y_max" in area:
            return [
                f"{float(area['x_min']):g}x{float(area['y_min']):g}",
                f"{float(area['x_max']):g}x{float(area['y_min']):g}",
                f"{float(area['x_max']):g}x{float(area['y_max']):g}",
                f"{float(area['x_min']):g}x{float(area['y_max']):g}",
            ]

    return None


# OrcaSlicer rejects a single-JSON preset that has no version and detects the
# preset type by the presence of *_settings_id (PresetBundle.cpp load_from_json:
# `if (!version) return false` + `config.has("printer_settings_id")`). Mirror the
# value used by the filament exporter for consistency.
ORCA_PROFILE_VERSION = "2.3.0.0"


def _generate_orca_tag(printer: Printer | None, vendor: str | None) -> str:
    """
    Генерировать тег для OrcaSlicer на основе принтера или vendor.

    Примеры:
    - @Voron (из printer.manufacturer)
    - @BambuLab (из printer.manufacturer)
    - @Arena (из vendor или printer.vendor)
    - @fh (по умолчанию для пользовательских)
    """
    if printer:
        # Приоритет: manufacturer принтера
        if printer.manufacturer:
            # Нормализуем: убираем лишние пробелы, делаем короткий тег
            tag = printer.manufacturer.strip()
            # Убираем суффиксы типа "Lab", "Labs" для краткости
            if tag.endswith(" Lab"):
                tag = tag[:-4]
            elif tag.endswith(" Labs"):
                tag = tag[:-5]
            return tag

        # Если нет manufacturer, используем vendor
        if printer.vendor:
            return printer.vendor.strip()

    # Используем vendor из профиля
    if vendor:
        return vendor.strip()

    # По умолчанию для пользовательских профилей
    return "fh"


def _format_printer_profile_name_for_orca(
    profile: PrinterProfile,
    printer: Printer | None,
    nozzle: float | None = None,
) -> str:
    """
    Сформировать имя PrinterProfile в формате OrcaSlicer.

    Формат: "{Printer.name} {nozzle} nozzle"
    Примеры:
    - "Voron 2.4 350 0.4 nozzle"
    - "Bambu Lab X1 Carbon 0.4 nozzle"

    Если printer не указан или nozzle не указан, использует profile.name как есть.
    """
    # Имя PrinterProfile само по себе — это имя машина-пресета в OrcaSlicer
    # (напр. "Bambu Lab X1 Carbon 0.4 nozzle" для системных/импортированных).
    # Оно каноничное и должно использоваться напрямую, чтобы compatible_printers
    # матчился по точному имени. Реконструируем только для служебных заглушек.
    profile_name = (profile.name or "").strip()
    is_placeholder = (
        not profile_name
        or profile_name.startswith("Принтер ")
        or profile_name.startswith("Printer ")
    )
    if not is_placeholder:
        return profile_name

    # Определяем правильное имя принтера
    printer_name = None
    if printer:
        # Если printer.name содержит "Принтер 1234" или похожее - используем manufacturer + model
        if printer.name and (printer.name.startswith("Принтер ") or printer.name.startswith("Printer ")):
            # Пытаемся сформировать из manufacturer и model
            if printer.manufacturer and printer.model:
                printer_name = f"{printer.manufacturer} {printer.model}".strip()
            elif printer.manufacturer:
                printer_name = printer.manufacturer.strip()
            elif printer.model:
                printer_name = printer.model.strip()
            else:
                # Если ничего нет, используем текущее имя профиля (без "Принтер 1234")
                if profile.name and not (profile.name.startswith("Принтер ") or profile.name.startswith("Printer ")):
                    printer_name = profile.name.rsplit(" ", 1)[0] if " " in profile.name else profile.name
        else:
            # Используем printer.name как есть
            printer_name = printer.name

    if not printer_name:
        # Если нет принтера или имени, используем текущее имя профиля
        return profile.name

    # Получаем диаметр сопла
    nozzle_diameter = nozzle
    if nozzle_diameter is None:
        # Пытаемся взять из nozzle_diameters (первый элемент)
        if profile.nozzle_diameters and len(profile.nozzle_diameters) > 0:
            nozzle_diameter = profile.nozzle_diameters[0]
        # Если нет, берем из printer
        elif printer and printer.nozzle_diameter:
            nozzle_diameter = printer.nozzle_diameter

    if nozzle_diameter is None:
        # Если всё равно нет сопла, используем имя принтера без "nozzle"
        return printer_name

    # Форматируем: "{Printer.name} {nozzle} nozzle"
    # Преобразуем 0.4 в "0.4", 0.6 в "0.6" и т.д.
    nozzle_str = str(nozzle_diameter).rstrip("0").rstrip(".")
    return f"{printer_name} {nozzle_str} nozzle"


def _format_print_profile_name_for_orca(
    profile: PrintProfile,
    tag: str | None = None,
) -> str:
    """
    Сформировать имя PrintProfile в формате OrcaSlicer.

    Формат: "{layer_height}mm {quality} @{tag}"
    Примеры:
    - "0.20mm Standard @Voron"
    - "0.12mm Fine @BBL X1C"
    - "0.24mm Draft @Arena X1C"

    Если tag не указан, пытается извлечь из profile.name или использовать vendor.
    Если layer_height или quality не указаны, использует profile.name как есть.
    """
    # Определяем tag
    if not tag:
        # Пытаемся извлечь tag из текущего имени (если там есть @tag)
        if "@" in profile.name:
            parts = profile.name.split("@", 1)
            if len(parts) > 1:
                tag = parts[1].strip()
        # Если нет в имени, используем vendor
        if not tag:
            tag = profile.vendor or "fh"

    # Определяем layer_height и quality
    layer_height = profile.layer_height_mm
    quality = profile.quality_tier

    # Если есть layer_height и quality, формируем стандартное имя
    if layer_height is not None and quality:
        # Форматируем layer_height: 0.2 -> "0.20mm", 0.12 -> "0.12mm"
        layer_str = f"{layer_height:.2f}".rstrip("0").rstrip(".")
        if "." in layer_str:
            # Оставляем минимум 2 знака после запятой
            if len(layer_str.split(".")[1]) < 2:
                layer_str = f"{layer_height:.2f}".rstrip("0").rstrip(".")
        layer_str = f"{layer_str}mm"

        # Нормализуем quality tier
        quality_map = {
            "superdraft": "Extra Draft",
            "draft": "Draft",
            "standard": "Standard",
            "optimal": "Optimal",
            "fine": "Fine",
            "highdetail": "Extra Fine",
        }
        quality_display = quality_map.get(quality.lower(), quality.capitalize())

        return f"{layer_str} {quality_display} @{tag}"

    # Если нет layer_height или quality, проверяем текущее имя
    # Если оно уже в формате OrcaSlicer, используем его
    if profile.name and ("mm" in profile.name or "@" in profile.name):
        # Обновляем tag если нужно
        if "@" not in profile.name:
            return f"{profile.name} @{tag}"
        # Если tag уже есть, но другой - заменяем
        if "@" in profile.name:
            parts = profile.name.rsplit("@", 1)
            if len(parts) == 2:
                return f"{parts[0].rstrip()} @{tag}"
        return profile.name

    # Если ничего не подходит, используем текущее имя и добавляем tag
    if tag and tag != "fh":
        return f"{profile.name} @{tag}"

    return profile.name


async def printer_profile_to_orca_json(
    profile: PrinterProfile,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """Преобразовать `PrinterProfile` в JSON-формат OrcaSlicer (`machine`)."""
    # Начинаем с настроек из профиля
    settings = _merge_settings(profile.orcaslicer_settings)

    # УМНАЯ СИСТЕМА: Если orcaslicer_settings пуст или содержит только базовые поля,
    # используем данные из printer.extra_metadata
    # Это позволяет экспортировать принтеры, созданные через админку, в валидный формат OrcaSlicer
    # Проверяем, что в settings нет важных полей OrcaSlicer (например, printer_structure, gcode_flavor)
    important_fields = {
        "printer_structure", "gcode_flavor", "printer_technology",
        "machine_max_speed_x", "machine_max_speed_y", "machine_max_speed_z",
        "machine_start_gcode", "machine_end_gcode",
    }
    has_important_fields = any(key in settings for key in important_fields)

    # Если нет важных полей, пробуем взять из printer.extra_metadata
    if not has_important_fields and profile.printer and profile.printer.extra_metadata:
        printer_metadata = dict(profile.printer.extra_metadata)
        # Исключаем поля, которые не относятся к OrcaSlicer
        EXCLUDE_FIELDS = {"_inherits_chain"}  # Служебные поля
        for key in EXCLUDE_FIELDS:
            printer_metadata.pop(key, None)
        # Объединяем: сначала printer.extra_metadata, затем orcaslicer_settings (приоритет)
        # Это означает, что если в orcaslicer_settings есть поле, оно перезапишет значение из extra_metadata
        merged = {}
        merged.update(printer_metadata)
        merged.update(settings)
        settings = merged

    # Генерируем имя в формате OrcaSlicer
    printer = profile.printer
    nozzle = None
    if profile.nozzle_diameters and len(profile.nozzle_diameters) > 0:
        nozzle = profile.nozzle_diameters[0]
    elif printer and printer.nozzle_diameter:
        nozzle = printer.nozzle_diameter

    orca_name = _format_printer_profile_name_for_orca(profile, printer, nozzle)

    # Базовые поля (обязательные для OrcaSlicer)
    settings["type"] = "machine"
    settings["name"] = orca_name
    # OrcaSlicer определяет тип пресета по наличию printer_settings_id и требует
    # version, иначе одиночный JSON не загружается (PresetBundle.cpp).
    settings["printer_settings_id"] = orca_name
    settings.setdefault("version", ORCA_PROFILE_VERSION)
    settings["from"] = "system" if profile.is_official else profile.source or "user"
    # OrcaSlicer ожидает строку "true"/"false"
    settings["instantiation"] = str(settings.get("instantiation", "true")).lower()

    if profile.setting_id:
        settings["setting_id"] = profile.setting_id
    else:
        # Запасной идентификатор
        settings.setdefault("setting_id", f"FHUB_M_{profile.id}")

    # Nozzle options - используем значения из orcaslicer_settings (приоритет), если нет - из отдельных колонок
    if "nozzle_diameter" not in settings:
        if profile.nozzle_diameters:
            settings["nozzle_diameter"] = [str(v) for v in profile.nozzle_diameters]
        # Если нет в профиле, пробуем взять из принтера
        elif profile.printer and profile.printer.nozzle_diameter:
            settings["nozzle_diameter"] = [str(profile.printer.nozzle_diameter)]

    # Printable area / height - используем значения из orcaslicer_settings (приоритет), если нет - из отдельных колонок
    if "printable_area" not in settings:
        if profile.printable_area:
            normalized_area = _normalize_printable_area(profile.printable_area)
            if normalized_area:
                settings["printable_area"] = normalized_area
        # Если нет в профиле, пробуем построить из build_volume принтера
        elif profile.printer:
            printer = profile.printer
            if printer.build_volume_x and printer.build_volume_y:
                settings["printable_area"] = [
                    "0x0",
                    f"{printer.build_volume_x}x0",
                    f"{printer.build_volume_x}x{printer.build_volume_y}",
                    f"0x{printer.build_volume_y}",
                ]
            if printer.build_volume_z:
                settings["printable_height"] = str(printer.build_volume_z)

    if "printable_height" not in settings and profile.printable_height_mm:
        settings["printable_height"] = str(profile.printable_height_mm)

    if profile.extra_metadata:
        for key in ("bed_custom_model", "bed_custom_texture"):
            if key not in settings and profile.extra_metadata.get(key):
                settings[key] = str(profile.extra_metadata[key])

    # printer_model - используем значения из orcaslicer_settings (приоритет), если нет - из printer.name
    if "printer_model" not in settings:
        if printer and printer.name:
            settings["printer_model"] = printer.name
        elif profile.extra_metadata and profile.extra_metadata.get("printer_model"):
            settings["printer_model"] = profile.extra_metadata["printer_model"]

    # Старт/финишный G-code из отдельного поля модели имеют приоритет
    # Используем значения из orcaslicer_settings (приоритет), если нет - из отдельных колонок
    if "machine_start_gcode" not in settings and profile.start_gcode:
        settings["machine_start_gcode"] = profile.start_gcode
    if "machine_end_gcode" not in settings and profile.end_gcode:
        settings["machine_end_gcode"] = profile.end_gcode

    # Printer notes - используем значения из orcaslicer_settings, но пустое значение
    # не должно блокировать заметки, отредактированные в веб-профиле.
    existing_printer_notes = settings.get("printer_notes")
    if profile.notes and (
        "printer_notes" not in settings
        or existing_printer_notes is None
        or (isinstance(existing_printer_notes, str) and existing_printer_notes.strip() == "")
    ):
        settings["printer_notes"] = profile.notes

    # Default print profile - преобразуем slug в name
    default_print_profile_name = None
    if profile.extra_metadata:
        default_print_profile_name = profile.extra_metadata.get("default_print_profile")

    # Если в extra_metadata есть name, используем его
    if not default_print_profile_name and profile.default_print_profile_slug and db:
        # Ищем PrintProfile по slug и берем его name
        result = await db.execute(
            select(PrintProfile).where(PrintProfile.slug == profile.default_print_profile_slug)
        )
        print_profile = result.scalar_one_or_none()
        if print_profile:
            # Генерируем name в формате OrcaSlicer для PrintProfile
            tag = _generate_orca_tag(printer, profile.vendor)
            default_print_profile_name = _format_print_profile_name_for_orca(print_profile, tag)

    # Если всё равно нет, используем slug как есть (fallback)
    if not default_print_profile_name and profile.default_print_profile_slug:
        default_print_profile_name = profile.default_print_profile_slug

    # default_print_profile - используем значения из orcaslicer_settings (приоритет), если нет - из преобразованного slug
    if "default_print_profile" not in settings and default_print_profile_name:
        settings["default_print_profile"] = default_print_profile_name

    # Bundle metadata — совместимость с upstream OrcaSlicer 2.4 (Orca Cloud) bundle model.
    settings["bundle_id"] = f"filamenthub:{profile.id}"

    # Backward compatibility: старый C++ форк читает fhub_id/fhub_source.
    # TODO(post-2026-12): удалить после миграции всех юзеров на форк с bundle_id поддержкой.
    settings["fhub_id"] = str(profile.id)
    settings["fhub_source"] = "filamenthub"

    # Валидация профиля перед экспортом (мягкая - только логирование)
    validation_result = validate_printer_profile(settings)
    log_validation_result(validation_result, profile.name, "printer")

    return settings


async def export_printer_profile(
    profile: PrinterProfile,
    db: AsyncSession | None = None,
) -> str:
    """Вернуть JSON-строку с профилем принтера."""
    return json.dumps(
        await printer_profile_to_orca_json(profile, db),
        indent=4,
        ensure_ascii=False,
    )


def printer_profile_info(profile: PrinterProfile) -> str:
    """Сформировать .info-файл для профиля принтера."""
    setting_id = profile.setting_id or f"FHUB_M_{profile.id}"
    updated_at = profile.updated_at or profile.created_at or datetime.utcnow()
    lines = [
        "sync_info = ",
        f"user_id = {profile.owner_user_id or ''}",
        f"setting_id = {setting_id}",
        f"base_id = {profile.extra_metadata.get('base_id', 'null') if profile.extra_metadata else 'null'}",
        f"updated_time = {int(updated_at.timestamp())}",
    ]
    return "\n".join(lines)


async def print_profile_to_orca_json(
    profile: PrintProfile,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """Преобразовать `PrintProfile` (process) в JSON OrcaSlicer."""
    settings = _merge_settings(profile.orcaslicer_settings)

    # Генерируем tag для OrcaSlicer
    # Пытаемся взять из связанных принтеров (приоритет), иначе из vendor
    tag = None
    if db and profile.printer_links:
        # Берем первый связанный принтер для генерации tag
        printer_ids = [link.printer_id for link in profile.printer_links if link.printer_id]
        if printer_ids:
            result = await db.execute(
                select(Printer).where(Printer.id == printer_ids[0])
            )
            printer = result.scalar_one_or_none()
            if printer:
                tag = _generate_orca_tag(printer, profile.vendor)

    if not tag:
        tag = _generate_orca_tag(None, profile.vendor)

    # Генерируем имя в формате OrcaSlicer
    orca_name = _format_print_profile_name_for_orca(profile, tag)

    settings["type"] = "process"
    settings["name"] = orca_name
    # Тип определяется наличием print_settings_id; version обязателен для загрузки
    # одиночного JSON (PresetBundle.cpp).
    settings["print_settings_id"] = orca_name
    settings.setdefault("version", ORCA_PROFILE_VERSION)
    settings["from"] = "system" if profile.is_official else profile.source or "user"
    settings["instantiation"] = (
        settings.get("instantiation", "true")
        if profile.is_official
        else settings.get("instantiation", "false")
    )

    if profile.setting_id:
        settings["setting_id"] = profile.setting_id
    else:
        settings.setdefault("setting_id", f"FHUB_P_{profile.id}")

    # Совместимые принтеры - преобразуем из slug в name PrinterProfile
    if db and profile.printer_links:
        # Батч-загрузка принтеров и их профилей вместо запроса на каждый link (N+1)
        printer_ids = [link.printer_id for link in profile.printer_links if link.printer_id]
        printers_by_id: dict[int, Printer] = {}
        profile_by_printer_id: dict[int, PrinterProfile] = {}
        if printer_ids:
            printers_result = await db.execute(
                select(Printer).where(Printer.id.in_(printer_ids))
            )
            printers_by_id = {p.id: p for p in printers_result.scalars().all()}

            pp_result = await db.execute(
                select(PrinterProfile)
                .where(PrinterProfile.printer_id.in_(printer_ids))
                .where(PrinterProfile.active == True)
                .order_by(PrinterProfile.id.asc())
            )
            # Первый активный профиль на принтер (запрос упорядочен по id)
            for pp in pp_result.scalars().all():
                profile_by_printer_id.setdefault(pp.printer_id, pp)

        compatible_printer_names = []
        for link in profile.printer_links:
            if link.printer_id:
                printer = printers_by_id.get(link.printer_id)
                printer_profile = profile_by_printer_id.get(link.printer_id)
                if printer and printer_profile:
                    # Генерируем name в формате OrcaSlicer
                    nozzle = None
                    if printer_profile.nozzle_diameters and len(printer_profile.nozzle_diameters) > 0:
                        nozzle = printer_profile.nozzle_diameters[0]
                    elif printer.nozzle_diameter:
                        nozzle = printer.nozzle_diameter
                    printer_profile_name = _format_printer_profile_name_for_orca(
                        printer_profile, printer, nozzle
                    )
                    compatible_printer_names.append(printer_profile_name)
            elif link.printer_slug:
                # Fallback: используем printer_slug как есть (для условий)
                compatible_printer_names.append(link.printer_slug)

        if compatible_printer_names:
            settings["compatible_printers"] = compatible_printer_names
    elif profile.compatible_printers:
        # Fallback: используем как есть (если нет доступа к БД)
        settings["compatible_printers"] = [
            printer for printer in profile.compatible_printers if printer
        ]

    # Совместимые филаменты - оставляем как есть (slug или name)
    if profile.compatible_filaments:
        settings["compatible_filaments"] = [
            filament for filament in profile.compatible_filaments if filament
        ]

    if profile.category:
        settings.setdefault("category", profile.category)
    if profile.default_nozzle:
        settings.setdefault("default_nozzle_diameter", profile.default_nozzle)
    if profile.layer_height_mm:
        settings.setdefault("layer_height", str(profile.layer_height_mm))

    if profile.extra_metadata:
        condition = profile.extra_metadata.get("compatible_printers_condition")
        if condition:
            settings["compatible_printers_condition"] = condition

    # Bundle metadata — совместимость с upstream OrcaSlicer 2.4 (Orca Cloud) bundle model.
    settings["bundle_id"] = f"filamenthub:{profile.id}"

    # Backward compatibility: старый C++ форк читает fhub_id/fhub_source.
    # TODO(post-2026-12): удалить после миграции всех юзеров на форк с bundle_id поддержкой.
    settings["fhub_id"] = str(profile.id)
    settings["fhub_source"] = "filamenthub"

    # Валидация профиля перед экспортом (мягкая - только логирование)
    validation_result = validate_print_profile(settings)
    log_validation_result(validation_result, profile.name, "print")

    return settings


async def export_print_profile(
    profile: PrintProfile,
    db: AsyncSession | None = None,
) -> str:
    """Вернуть JSON-строку с профилем печати."""
    return json.dumps(
        await print_profile_to_orca_json(profile, db),
        indent=4,
        ensure_ascii=False,
    )


def print_profile_info(profile: PrintProfile) -> str:
    """Сформировать .info-файл для профиля печати."""
    setting_id = profile.setting_id or f"FHUB_P_{profile.id}"
    updated_at = profile.updated_at or profile.created_at or datetime.utcnow()
    lines = [
        "sync_info = ",
        f"user_id = {profile.owner_user_id or ''}",
        f"setting_id = {setting_id}",
        f"base_id = {profile.extra_metadata.get('base_id', 'null') if profile.extra_metadata else 'null'}",
        f"updated_time = {int(updated_at.timestamp())}",
    ]
    return "\n".join(lines)
