"""Валидация профилей OrcaSlicer перед экспортом.

Проверяет что JSON профиль соответствует требованиям OrcaSlicer Wiki
и будет успешно импортирован.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Результат валидации профиля."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Добавить критичную ошибку."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Добавить предупреждение (не критично)."""
        self.warnings.append(message)


# Обязательные поля для каждого типа профиля
FILAMENT_REQUIRED_FIELDS = [
    "type",
    "name",
    "version",
    "from",
    "inherits",
    "filament_settings_id",
    "setting_id",
]

PRINT_REQUIRED_FIELDS = [
    "type",
    "name",
    "version",
    "from",
    "print_settings_id",
    "setting_id",
    "compatible_printers",  # ВАЖНО: не должен быть пустым!
]

PRINTER_REQUIRED_FIELDS = [
    "type",
    "name",
    "version",
    "from",
    "printer_settings_id",
    "setting_id",
]

# Допустимые значения
VALID_TYPES = ["filament", "process", "machine"]
VALID_FROM_VALUES = ["system", "user"]
VERSION_PATTERN = r"^\d+\.\d+\.\d+(\.\d+)?$"


def _check_filamenthub_marker(profile: dict[str, Any], result: ValidationResult) -> None:
    """Verify profile carries a FilamentHub identity marker.

    Accepts either the new `bundle_id` field (Orca 2.4 bundle model — format
    `"filamenthub:<id>"`) or the legacy `fhub_source`/`fhub_id` pair. Emits a
    warning only if neither is present; this is non-fatal so third-party
    profiles still pass validation.
    """
    bundle_id = profile.get("bundle_id")
    if isinstance(bundle_id, str) and bundle_id.startswith("filamenthub:"):
        return

    fhub_source = profile.get("fhub_source")
    if fhub_source == "filamenthub":
        return

    if bundle_id and not (isinstance(bundle_id, str) and bundle_id.startswith("filamenthub:")):
        result.add_warning(
            f"bundle_id has unexpected format: {bundle_id!r} (expected 'filamenthub:<id>')"
        )
        return

    result.add_warning(
        "Profile has no FilamentHub identity marker — "
        "expected either bundle_id='filamenthub:<id>' (preferred) or fhub_source='filamenthub'"
    )


def validate_filament_profile(profile: dict[str, Any]) -> ValidationResult:
    """
    Валидация профиля филамента.

    Проверяет:
    - Наличие обязательных полей
    - Корректность типов данных
    - Валидность значений (type, from, version)
    - Наличие fhub_source для синхронизации

    Args:
        profile: JSON профиля филамента

    Returns:
        ValidationResult с результатом валидации
    """
    result = ValidationResult(is_valid=True)

    # 1. Проверяем обязательные поля
    for field_name in FILAMENT_REQUIRED_FIELDS:
        if field_name not in profile:
            result.add_error(f"Отсутствует обязательное поле: {field_name}")
        elif profile[field_name] is None:
            result.add_error(f"Поле '{field_name}' не может быть None")
        elif isinstance(profile[field_name], str) and not profile[field_name].strip():
            result.add_error(f"Поле '{field_name}' не может быть пустой строкой")

    # 2. Проверяем type
    if "type" in profile:
        if profile["type"] != "filament":
            result.add_error(f"type должен быть 'filament', получено: {profile['type']}")

    # 3. Проверяем from
    if "from" in profile:
        if profile["from"] not in VALID_FROM_VALUES:
            result.add_error(f"from должен быть 'system' или 'user', получено: {profile['from']}")

    # 4. Проверяем version (формат X.Y.Z.W)
    if "version" in profile:
        import re
        if not re.match(VERSION_PATTERN, str(profile["version"])):
            result.add_warning(f"version должен быть в формате X.Y.Z[.W], получено: {profile['version']}")

    # 5. Проверяем filament_settings_id (должен быть массивом)
    if "filament_settings_id" in profile:
        if not isinstance(profile["filament_settings_id"], list):
            result.add_error("filament_settings_id должен быть массивом")
        elif len(profile["filament_settings_id"]) == 0:
            result.add_error("filament_settings_id не может быть пустым массивом")

    # 6. Проверяем inherits (должен быть непустой строкой)
    if "inherits" in profile:
        if not isinstance(profile["inherits"], str) or not profile["inherits"].strip():
            result.add_error("inherits должен быть непустой строкой")

    # 7. FilamentHub identity marker (bundle_id preferred, fhub_source fallback)
    _check_filamenthub_marker(profile, result)

    # 8. Проверяем температуры (если есть)
    temp_fields = ["nozzle_temperature", "hot_plate_temp", "cool_plate_temp"]
    for temp_field in temp_fields:
        if temp_field in profile:
            if not isinstance(profile[temp_field], list):
                result.add_warning(f"{temp_field} должен быть массивом")
            elif profile[temp_field]:
                try:
                    temp_value = int(profile[temp_field][0])
                    if temp_value < 0 or temp_value > 500:
                        result.add_warning(f"{temp_field} имеет нереалистичное значение: {temp_value}")
                except (ValueError, TypeError):
                    result.add_warning(f"{temp_field} должен содержать числовые значения")

    return result


def validate_print_profile(profile: dict[str, Any]) -> ValidationResult:
    """
    Валидация профиля печати (process).

    ВАЖНО: compatible_printers НЕ должен быть пустым для print profiles!

    Args:
        profile: JSON профиля печати

    Returns:
        ValidationResult с результатом валидации
    """
    result = ValidationResult(is_valid=True)

    # 1. Проверяем обязательные поля
    for field_name in PRINT_REQUIRED_FIELDS:
        if field_name not in profile:
            result.add_error(f"Отсутствует обязательное поле: {field_name}")
        elif profile[field_name] is None:
            result.add_error(f"Поле '{field_name}' не может быть None")

    # 2. Проверяем type
    if "type" in profile:
        if profile["type"] != "process":
            result.add_error(f"type должен быть 'process', получено: {profile['type']}")

    # 3. Проверяем from
    if "from" in profile:
        if profile["from"] not in VALID_FROM_VALUES:
            result.add_error(f"from должен быть 'system' или 'user', получено: {profile['from']}")

    # 4. Проверяем print_settings_id (в живых Orca process JSON обычно строка, но legacy может быть массивом)
    if "print_settings_id" in profile:
        print_settings_id = profile["print_settings_id"]
        if isinstance(print_settings_id, str):
            if not print_settings_id.strip():
                result.add_error("print_settings_id не может быть пустой строкой")
        elif isinstance(print_settings_id, list):
            if len(print_settings_id) == 0 or not any(str(item).strip() for item in print_settings_id):
                result.add_error("print_settings_id не может быть пустым массивом")
        else:
            result.add_error("print_settings_id должен быть строкой или массивом")

    # 5. ВАЖНО: compatible_printers НЕ должен быть пустым для print profiles!
    if "compatible_printers" in profile:
        if not isinstance(profile["compatible_printers"], list):
            result.add_error("compatible_printers должен быть массивом")
        elif len(profile["compatible_printers"]) == 0:
            result.add_error("compatible_printers не может быть пустым для профиля печати")

    # 6. FilamentHub identity marker (bundle_id preferred, fhub_source fallback)
    _check_filamenthub_marker(profile, result)

    return result


def validate_printer_profile(profile: dict[str, Any]) -> ValidationResult:
    """
    Валидация профиля принтера (machine).

    Args:
        profile: JSON профиля принтера

    Returns:
        ValidationResult с результатом валидации
    """
    result = ValidationResult(is_valid=True)

    # 1. Проверяем обязательные поля
    for field_name in PRINTER_REQUIRED_FIELDS:
        if field_name not in profile:
            result.add_error(f"Отсутствует обязательное поле: {field_name}")
        elif profile[field_name] is None:
            result.add_error(f"Поле '{field_name}' не может быть None")

    # 2. Проверяем type
    if "type" in profile:
        if profile["type"] != "machine":
            result.add_error(f"type должен быть 'machine', получено: {profile['type']}")

    # 3. Проверяем from
    if "from" in profile:
        if profile["from"] not in VALID_FROM_VALUES:
            result.add_error(f"from должен быть 'system' или 'user', получено: {profile['from']}")

    # 4. Проверяем printer_settings_id (в Orca machine JSON — строка ConfigOptionString;
    #    legacy может быть массивом)
    if "printer_settings_id" in profile:
        printer_settings_id = profile["printer_settings_id"]
        if isinstance(printer_settings_id, str):
            if not printer_settings_id.strip():
                result.add_error("printer_settings_id не может быть пустой строкой")
        elif isinstance(printer_settings_id, list):
            if len(printer_settings_id) == 0 or not any(str(item).strip() for item in printer_settings_id):
                result.add_error("printer_settings_id не может быть пустым массивом")
        else:
            result.add_error("printer_settings_id должен быть строкой или массивом")

    # 5. Проверяем nozzle_diameter (должен быть массивом чисел)
    if "nozzle_diameter" in profile:
        if not isinstance(profile["nozzle_diameter"], list):
            result.add_warning("nozzle_diameter должен быть массивом")
        elif profile["nozzle_diameter"]:
            try:
                nozzle = float(profile["nozzle_diameter"][0])
                if nozzle < 0.1 or nozzle > 2.0:
                    result.add_warning(f"nozzle_diameter имеет нереалистичное значение: {nozzle}")
            except (ValueError, TypeError):
                result.add_warning("nozzle_diameter должен содержать числовые значения")

    # 6. FilamentHub identity marker (bundle_id preferred, fhub_source fallback)
    _check_filamenthub_marker(profile, result)

    return result


def validate_profile(profile: dict[str, Any]) -> ValidationResult:
    """
    Автоматически определить тип профиля и провести валидацию.

    Args:
        profile: JSON профиля любого типа

    Returns:
        ValidationResult с результатом валидации
    """
    # Определяем тип по наличию *_settings_id
    if "filament_settings_id" in profile:
        return validate_filament_profile(profile)
    elif "print_settings_id" in profile:
        return validate_print_profile(profile)
    elif "printer_settings_id" in profile:
        return validate_printer_profile(profile)
    else:
        result = ValidationResult(is_valid=False)
        result.add_error(
            "Не удалось определить тип профиля: отсутствуют "
            "filament_settings_id, print_settings_id или printer_settings_id"
        )
        return result


def log_validation_result(
    result: ValidationResult,
    profile_name: str,
    profile_type: str,
) -> None:
    """Логировать результат валидации."""
    if result.is_valid:
        if result.warnings:
            logger.warning(
                f"Profile '{profile_name}' ({profile_type}) passed validation with warnings: "
                f"{', '.join(result.warnings)}"
            )
        else:
            logger.debug(f"Profile '{profile_name}' ({profile_type}) passed validation")
    else:
        logger.error(
            f"Profile '{profile_name}' ({profile_type}) failed validation: "
            f"{', '.join(result.errors)}"
        )
        if result.warnings:
            logger.warning(f"Additional warnings: {', '.join(result.warnings)}")


def validate_profile_strict(
    profile: dict[str, Any],
    profile_name: str | None = None,
) -> None:
    """
    Строгая валидация профиля - выбрасывает исключение при ошибках.

    Используется при публикации черновиков или создании профилей через UI.
    При ошибках вызывает ValueError с детальным описанием проблем.

    Args:
        profile: JSON профиля любого типа
        profile_name: Имя профиля для сообщений об ошибках

    Raises:
        ValueError: Если профиль не прошел валидацию
    """
    result = validate_profile(profile)
    name = profile_name or profile.get("name", "Unknown")

    if not result.is_valid:
        error_details = "; ".join(result.errors)
        raise ValueError(
            f"Profile '{name}' validation failed: {error_details}"
        )

    # Логируем предупреждения даже при успешной валидации
    if result.warnings:
        logger.warning(
            f"Profile '{name}' validation warnings: {', '.join(result.warnings)}"
        )


def get_validation_errors(profile: dict[str, Any]) -> list[str]:
    """
    Получить список ошибок валидации профиля.

    Полезно для UI когда нужно показать пользователю что исправить.

    Args:
        profile: JSON профиля любого типа

    Returns:
        Список сообщений об ошибках (пустой если профиль валиден)
    """
    result = validate_profile(profile)
    return result.errors


def get_validation_warnings(profile: dict[str, Any]) -> list[str]:
    """
    Получить список предупреждений валидации профиля.

    Предупреждения не блокируют экспорт, но указывают на потенциальные проблемы.

    Args:
        profile: JSON профиля любого типа

    Returns:
        Список предупреждений (пустой если всё идеально)
    """
    result = validate_profile(profile)
    return result.warnings
