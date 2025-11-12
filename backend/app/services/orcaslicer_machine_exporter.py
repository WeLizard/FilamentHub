"""Экспорт системных профилей принтеров/печати в формат OrcaSlicer."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from app.models.printer_profile import PrinterProfile
from app.models.print_profile import PrintProfile


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


def printer_profile_to_orca_json(profile: PrinterProfile) -> dict[str, Any]:
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

    # Базовые поля (обязательные для OrcaSlicer)
    settings["type"] = "machine"
    settings["name"] = profile.name
    settings["from"] = "system" if profile.is_official else profile.source or "user"
    # OrcaSlicer ожидает строку "true"/"false"
    settings["instantiation"] = str(settings.get("instantiation", "true")).lower()

    if profile.setting_id:
        settings["setting_id"] = profile.setting_id
    else:
        # Запасной идентификатор
        settings.setdefault("setting_id", f"FHUB_M_{profile.id}")

    # Nozzle options
    if profile.nozzle_diameters:
        settings["nozzle_diameter"] = [str(v) for v in profile.nozzle_diameters]
    # Если нет в профиле, пробуем взять из принтера
    elif profile.printer and profile.printer.nozzle_diameter:
        settings["nozzle_diameter"] = [str(profile.printer.nozzle_diameter)]

    # Printable area / height
    if profile.printable_area:
        area = profile.printable_area
        settings["printable_area"] = [
            f"{area['x_min']}x{area['y_min']}",
            f"{area['x_max']}x{area['y_min']}",
            f"{area['x_max']}x{area['y_max']}",
            f"{area['x_min']}x{area['y_max']}",
        ]
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
    
    if profile.printable_height_mm:
        settings["printable_height"] = str(profile.printable_height_mm)

    # Старт/финишный G-code из отдельного поля модели имеют приоритет
    if profile.start_gcode:
        settings["machine_start_gcode"] = profile.start_gcode
    if profile.end_gcode:
        settings["machine_end_gcode"] = profile.end_gcode

    # Default print profile
    if profile.extra_metadata:
        default_print_profile = profile.extra_metadata.get("default_print_profile")
        if default_print_profile:
            settings["default_print_profile"] = default_print_profile
    if (
        "default_print_profile" not in settings
        and profile.default_print_profile_slug
    ):
        settings["default_print_profile"] = profile.default_print_profile_slug

    return settings


def export_printer_profile(profile: PrinterProfile) -> str:
    """Вернуть JSON-строку с профилем принтера."""
    return json.dumps(
        printer_profile_to_orca_json(profile),
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


def print_profile_to_orca_json(profile: PrintProfile) -> dict[str, Any]:
    """Преобразовать `PrintProfile` (process) в JSON OrcaSlicer."""
    settings = _merge_settings(profile.orcaslicer_settings)

    settings["type"] = "process"
    settings["name"] = profile.name
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

    # Совместимые принтеры/филаменты
    if profile.compatible_printers:
        settings["compatible_printers"] = [
            printer for printer in profile.compatible_printers if printer
        ]
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

    return settings


def export_print_profile(profile: PrintProfile) -> str:
    """Вернуть JSON-строку с профилем печати."""
    return json.dumps(
        print_profile_to_orca_json(profile),
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


