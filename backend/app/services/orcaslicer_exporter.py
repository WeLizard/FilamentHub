"""Сервис для экспорта профилей FilamentHub в формат OrcaSlicer."""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament import Filament
from app.models.preset import Preset
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.services.material_mapping_service import get_material_preset
from app.services.orca_printer_identity import (
    is_orca_system_printer,
    resolve_orca_printer_model,
)
from app.services.profile_validator import (
    log_validation_result,
    validate_filament_profile,
)

logger = logging.getLogger(__name__)


# OrcaSlicer stores most preset settings as single-item string arrays,
# but a small set of metadata keys must remain scalar values.
ORCASLICER_SCALAR_SETTING_KEYS = {
    "inherits",
}


# Process-scope keys (OrcaSlicer `s_Preset_print_options`) belong to a print/process profile,
# not to a filament — a material must not carry them. Our frontend never emits these as filament
# settings, but a reverse-synced `orcaslicer_settings` blob could, so we drop them from the
# filament export. This is our layer's guard; Orca's own `remove_invalid_keys` is the final
# backstop on import. Curated to unambiguous process keys (not exhaustive by design).
PROCESS_SCOPE_KEYS = frozenset({
    "layer_height", "first_layer_height", "initial_layer_print_height",
    "print_speed", "travel_speed", "travel_speed_z", "initial_layer_speed",
    "initial_layer_infill_speed", "inner_wall_speed", "outer_wall_speed",
    "sparse_infill_speed", "internal_solid_infill_speed", "top_surface_speed",
    "gap_infill_speed", "bridge_speed", "internal_bridge_speed", "support_speed",
    "support_interface_speed", "small_perimeter_speed",
    "sparse_infill_density", "sparse_infill_pattern", "wall_loops", "wall_generator",
    "top_shell_layers", "top_shell_thickness", "bottom_shell_layers", "bottom_shell_thickness",
    "seam_position", "ironing_type", "ironing_speed",
    "enable_support", "support_type", "raft_layers", "brim_type", "brim_width",
    "line_width", "initial_layer_line_width", "inner_wall_line_width", "outer_wall_line_width",
    "sparse_infill_line_width", "internal_solid_infill_line_width", "top_surface_line_width",
    "support_line_width", "default_acceleration", "outer_wall_acceleration",
    "initial_layer_acceleration", "travel_acceleration", "post_process", "resolution",
    "skirt_loops", "skirt_distance",
})


def preset_to_orcaslicer_info(preset: Preset) -> str:
    """
    Генерировать .info файл для пресета FilamentHub.

    Формат .info файла (используется OrcaSlicer для metadata):
    sync_info = fhub:<preset_id>:<source>  # Метка FilamentHub (приоритетный источник истины)
    user_id = <orcaslicer_user_id>         # Заполняется OrcaSlicer
    setting_id = FHUB<preset_id_padded>    # FilamentHub preset ID
    base_id = <base_preset_name>           # Родительский пресет
    updated_time = <unix_timestamp>        # Время обновления

    Args:
        preset: Preset из FilamentHub

    Returns:
        str: Содержимое .info файла
    """
    # sync_info: Метка FilamentHub (приоритетный источник истины)
    # Формат: fhub:<preset_id>:<source>
    sync_info = f"fhub:{preset.id}:filamenthub"

    # setting_id: FilamentHub preset ID в формате FHUB + zero-padded
    # Используется как уникальный идентификатор в OrcaSlicer
    setting_id = f"FHUB{preset.id:06d}"

    # base_id: Базовый профиль (из inherits в orcaslicer_settings)
    # Извлекаем из orcaslicer_settings если есть, иначе используем умолчание
    orcaslicer_settings = preset.orcaslicer_settings or {}
    inherits = orcaslicer_settings.get("inherits", "fdm_filament_common")
    base_id = inherits

    # updated_time: Unix timestamp обновления
    import time
    from datetime import timezone
    if preset.updated_at:
        # Конвертируем datetime в unix timestamp
        if preset.updated_at.tzinfo is None:
            # Если naive datetime, предполагаем UTC
            updated_time = int(preset.updated_at.replace(tzinfo=timezone.utc).timestamp())
        else:
            updated_time = int(preset.updated_at.timestamp())
    else:
        updated_time = int(time.time())

    # user_id: Оставляем пустым (OrcaSlicer заполнит сам)
    # Это позволяет OrcaSlicer отслеживать к какому пользователю относится пресет

    return f"""sync_info = {sync_info}
user_id =
setting_id = {setting_id}
base_id = {base_id}
updated_time = {updated_time}
"""


def _escape_condition_value(value: str) -> str:
    """Escape double quotes for an Orca condition string literal."""
    return value.replace('"', '\\"')


def _target_profiles_condition(target_profiles: list["PrinterProfile"]) -> str | None:
    """Condition for a preset scoped to the user's machine profiles.

    Resolves each profile's linked catalog printer to a canonical Orca
    printer_model (robust against machine-preset renames) and ORs them.
    Returns None when any profile has no resolvable system model — the caller
    pins by exact profile names instead. Mixing a condition with a
    compatible_printers list is not an option: Orca ANDs them, which would
    break the OR semantics across targets.
    """
    models: list[str] = []
    for profile in target_profiles:
        printer = profile.printer
        if printer is None or not is_orca_system_printer(printer):
            return None
        model = resolve_orca_printer_model(printer)
        if not model:
            return None
        if model not in models:
            models.append(model)
    if not models:
        return None
    return " or ".join(f'printer_model=="{_escape_condition_value(m)}"' for m in models)


async def build_compatible_printers_condition(preset: Preset, db: AsyncSession) -> str | None:
    """Build an Orca ``compatible_printers_condition`` from the preset's links.

    Matches the preset's authored ``PresetPrinter`` printers by canonical
    ``printer_model``. Returns None to leave the preset compatible with all
    printers — when it has no links, or only links to non-system/custom printers
    whose names match no Orca machine preset (self-builds, generic Klipper).
    """
    result = await db.execute(
        select(Printer)
        .join(PresetPrinter, PresetPrinter.printer_id == Printer.id)
        .where(PresetPrinter.preset_id == preset.id)
    )
    printers = result.scalars().all()
    if not printers:
        return None

    models: list[str] = []
    skipped_non_system = False
    for printer in printers:
        if not is_orca_system_printer(printer):
            skipped_non_system = True
            continue
        model = resolve_orca_printer_model(printer)
        if model and model not in models:
            models.append(model)

    if not models:
        if skipped_non_system:
            logger.warning(
                "Preset %s links only non-system printers; leaving compatible_printers open",
                preset.id,
            )
        return None

    clauses = [f'printer_model=="{_escape_condition_value(m)}"' for m in models]
    return " or ".join(clauses)


async def preset_to_orcaslicer_json(
    preset: Preset,
    filament: Filament,
    db: AsyncSession | None = None,
    target_profiles: "list[PrinterProfile] | None" = None,
) -> dict[str, Any]:
    """
    Конвертировать Preset из FilamentHub в формат профиля OrcaSlicer.

    Механизм работы:
    1. OrcaSlicer при импорте находит родительский пресет через поле "inherits"
    2. Копирует весь конфиг родителя (например "Generic PLA @System")
    3. Применяет параметры из JSON поверх родительского конфига
    4. Поэтому мы указываем только отличия от родительского пресета

    Однако для упрощения и переносимости сохраняем все важные параметры.
    OrcaSlicer сам решит что применять через механизм apply().

    Args:
        preset: Preset из FilamentHub
        filament: Filament из FilamentHub (связанный с preset)

    Returns:
        dict: JSON профиль в формате OrcaSlicer
    """
    # ОБЯЗАТЕЛЬНЫЕ поля профиля (в соответствии с OrcaSlicer)
    # BBL_JSON_KEY constants: version, name, from, inherits, filament_settings_id
    # OrcaSlicer проверяет config.has("filament_settings_id") для определения типа профиля
    profile = {
        "version": "2.3.0.0",  # Версия профиля OrcaSlicer (совместимость с OrcaSlicer 2.3.x)
        "type": "filament",  # Тип профиля
        "name": preset.name,  # Имя пресета (будет добавлен постфикс [fh] в C++)
        "from": "system" if preset.is_official else "user",  # Источник пресета
        "instantiation": "true",  # Флаг инстанцирования
        "filament_settings_id": [preset.name],  # ОБЯЗАТЕЛЬНО: OrcaSlicer определяет тип профиля по наличию этого поля
    }

    # Уникальные идентификаторы
    profile["setting_id"] = f"FHUB{preset.id:06d}"
    profile["filament_id"] = f"FHUB{filament.id:06d}"

    # Наследование от базового профиля по типу материала (ОБЯЗАТЕЛЬНОЕ поле)
    # Мапим FilamentHub material_type на реальные имена системных пресетов OrcaSlicer
    #
    # Важно: OrcaSlicer использует find_preset(inherits_value, false, true) для поиска родителя
    # Поэтому нужно указывать ТОЧНОЕ имя системного пресета (например "Generic PLA @System")
    #
    # find_preset2 в ensure_parent_preset_exists (C++) умеет автопреобразовывать:
    # - "fdm_filament_pla" -> "Generic PLA @System" (через regex)
    # Но лучше использовать правильные имена сразу

    # Получаем базовый профиль для наследования через сервис маппинга материалов
    # Приоритет: MaterialMapping из БД > базовый маппинг > умный поиск > fallback
    if db:
        base_profile = await get_material_preset(
            filament.material_type,
            db,
            log_unknown=True,  # Логируем неизвестные типы для анализа
        )
    else:
        # Fallback если db session не передан (для обратной совместимости)
        logger.warning(
            f"preset_to_orcaslicer_json called without db session for material_type='{filament.material_type}', "
            "using fallback 'fdm_filament_common'"
        )
        base_profile = "fdm_filament_common"

    profile["inherits"] = base_profile

    # Все параметры в OrcaSlicer хранятся как массивы строк
    # Это связано с поддержкой мультиэкструдеров (каждый экструдер - элемент массива)
    def to_array(value: Any) -> list[str]:
        """
        Конвертировать значение в массив строк.

        OrcaSlicer хранит все параметры как массивы для поддержки мультиэкструдеров.
        Для обычного пресета используется массив из одного элемента [value].
        """
        if value is None:
            return ["0"]  # OrcaSlicer использует "0" для значений по умолчанию/неустановленных
        return [str(value)]

    # Температуры экструдера
    if preset.extruder_temp:
        profile["nozzle_temperature"] = to_array(int(preset.extruder_temp))
        profile["nozzle_temperature_initial_layer"] = to_array(int(preset.extruder_temp))

    # Температуры стола (bed_temp)
    if preset.bed_temp:
        bed_temp = int(preset.bed_temp)
        # OrcaSlicer различает типы столов
        profile["hot_plate_temp"] = to_array(bed_temp)
        profile["hot_plate_temp_initial_layer"] = to_array(bed_temp)
        profile["cool_plate_temp"] = to_array(bed_temp)
        profile["cool_plate_temp_initial_layer"] = to_array(bed_temp)
        profile["eng_plate_temp"] = to_array(bed_temp)
        profile["eng_plate_temp_initial_layer"] = to_array(bed_temp)
        profile["textured_plate_temp"] = to_array(bed_temp)
        profile["textured_plate_temp_initial_layer"] = to_array(bed_temp)
        # Новые типы пластин Orca (supertack PEI, текстурированная холодная)
        profile["supertack_plate_temp"] = to_array(bed_temp)
        profile["supertack_plate_temp_initial_layer"] = to_array(bed_temp)
        profile["textured_cool_plate_temp"] = to_array(bed_temp)
        profile["textured_cool_plate_temp_initial_layer"] = to_array(bed_temp)

    # Вентилятор
    if preset.fan_speed is not None:
        fan_speed = max(0, min(100, preset.fan_speed))  # Ограничиваем 0-100
        profile["fan_min_speed"] = to_array(fan_speed)
        profile["fan_max_speed"] = to_array(100)
        profile["overhang_fan_speed"] = to_array(100)

    # Плотность филамента
    if filament.density is not None:
        profile["filament_density"] = to_array(round(filament.density, 2))

    # Требуемая твёрдость сопла (свойство материала: абразивные требуют закалённого сопла)
    if filament.required_nozzle_hrc is not None:
        profile["required_nozzle_HRC"] = to_array(int(filament.required_nozzle_hrc))

    # Диаметр филамента
    if filament.diameter is not None:
        profile["filament_diameter"] = to_array(filament.diameter)

    # Стоимость филамента (OrcaSlicer ожидает money/kg)
    if filament.price_per_kg is not None:
        profile["filament_cost"] = to_array(str(filament.price_per_kg))

    # Тип материала
    profile["filament_type"] = to_array(filament.material_type)

    # Производитель
    # Проверяем что brand загружен и не None
    if hasattr(filament, 'brand') and filament.brand is not None:
        profile["filament_vendor"] = to_array(filament.brand.name)

    # Retraction
    if preset.retraction_length:
        profile["filament_retraction_length"] = to_array(str(preset.retraction_length))

    if preset.retraction_speed:
        profile["filament_retraction_speed"] = to_array(str(int(preset.retraction_speed)))

    # Flow ratio (коэффициент потока)
    # БД хранит проценты (50-150), OrcaSlicer ожидает множитель (0.5-1.5)
    if preset.flow_rate is not None:
        flow_ratio = preset.flow_rate / 100.0
        profile["filament_flow_ratio"] = to_array(str(round(flow_ratio, 2)))

    # Расширенные параметры из JSON поля orcaslicer_settings
    # Эти параметры имеют приоритет над базовыми и добавляются в конец
    # Полезно для специальных настроек, которых нет в базовых полях FilamentHub
    if preset.orcaslicer_settings and isinstance(preset.orcaslicer_settings, dict) and len(preset.orcaslicer_settings) > 0:
        for key, value in preset.orcaslicer_settings.items():
            # Process-scope ключи не место в filament-профиле — отбрасываем (см. PROCESS_SCOPE_KEYS)
            if key in PROCESS_SCOPE_KEYS:
                logger.debug(f"Dropping process-scope key '{key}' from filament export of preset {preset.id}")
                continue
            # Пропускаем только если значение None или пустое
            if value is not None:
                try:
                    if key in ORCASLICER_SCALAR_SETTING_KEYS:
                        if isinstance(value, list):
                            profile[key] = str(value[0]) if value else ""
                        else:
                            profile[key] = str(value)
                    # Конвертируем значение в массив строк если это еще не массив
                    elif isinstance(value, list):
                        # Уже массив, проверяем что все элементы - строки
                        profile[key] = [str(v) for v in value]
                    else:
                        # Одиночное значение, конвертируем в массив строк (стандарт OrcaSlicer)
                        profile[key] = to_array(value)
                except Exception as e:
                    # Логируем ошибку, но продолжаем обработку остальных ключей
                    # Не критично если какой-то параметр не удалось экспортировать
                    logger.warning(f"Error exporting key '{key}' from orcaslicer_settings: {str(e)}")
                    # Пропускаем проблемный ключ
                    continue

    # Авторитетные поля из БД FilamentHub — ВСЕГДА перезаписывают orcaslicer_settings.
    # orcaslicer_settings может содержать стейл данные от обратного синка из OrcaSlicer
    # (например filament_vendor: "Generic" вместо реального производителя).
    # БД FilamentHub — источник истины для этих полей.
    profile["filament_type"] = to_array(filament.material_type)
    if hasattr(filament, 'brand') and filament.brand is not None:
        profile["filament_vendor"] = to_array(filament.brand.name)
    if filament.color_hex:
        profile["default_filament_colour"] = [filament.color_hex]

    # Совместимые принтеры. Приоритет — library scope пользователя:
    # targeted/compatible пресет сужается до его собственных machine-профилей
    # (RFC §3.3), у остальных авторитет — авторская привязка PresetPrinter:
    # по умолчанию пусто (совместим со всеми), condition сужает по каноничному
    # printer_model привязанных системных принтеров. Переживает переименования
    # пресетов и перетирает стейл-condition из обратного синка.
    profile["compatible_printers"] = []
    condition = None
    if target_profiles:
        condition = _target_profiles_condition(target_profiles)
        if condition is None:
            # Хотя бы один профиль без разрешимой системной модели (самосбор,
            # generic Klipper): пиним весь набор по точным именам
            # machine-профилей — это имена пресетов принтеров в Orca
            # пользователя.
            profile["compatible_printers"] = [p.name for p in target_profiles]
    elif db is not None and preset.id is not None:
        condition = await build_compatible_printers_condition(preset, db)
    if condition:
        profile["compatible_printers_condition"] = condition
    else:
        profile.pop("compatible_printers_condition", None)

    # Bundle metadata — совместимость с upstream OrcaSlicer 2.4 (Orca Cloud) bundle model.
    # Формат `"filamenthub:<id>"` соответствует Orca Cloud convention `"<provider>:<uuid>"`.
    # В OrcaSlicer это поле читается как `Preset.bundle_id` и `is_from_bundle()` возвращает true.
    profile["bundle_id"] = f"filamenthub:{preset.id}"

    # Backward compatibility: старые версии нашего форка читают `fhub_id`/`fhub_source`.
    # Дублируем их в JSON, чтобы старый C++ код продолжал работать после migration to Orca 2.4.
    # TODO(post-2026-12): удалить после того как все юзеры обновились на форк с bundle_id поддержкой.
    profile["fhub_id"] = str(preset.id)
    profile["fhub_source"] = "filamenthub"

    # Hardware provenance (мешок железа) — отдаём как метаданные, Orca игнорирует
    # неизвестный ключ. Не блокирующая совместимость, а подсказка/происхождение.
    if preset.compat_context:
        profile["fhub_compat_context"] = json.dumps(preset.compat_context, ensure_ascii=False)

    # Draft preset: fhub_draft_id для поиска черновика при следующей синхронизации
    if not preset.active and preset.orcaslicer_settings and isinstance(preset.orcaslicer_settings, dict):
        fhub_draft_id = preset.orcaslicer_settings.get("fhub_draft_id")
        if fhub_draft_id:
            profile["fhub_draft_id"] = str(fhub_draft_id)

    # ВАЖНО: НЕ обновляем orcaslicer_settings в базе при экспорте!
    # Это вызывает изменение updated_at и бесконечный цикл экспорта.

    # Валидация профиля перед экспортом (мягкая - только логирование)
    validation_result = validate_filament_profile(profile)
    log_validation_result(validation_result, preset.name, "filament")

    return profile


async def export_preset_to_orcaslicer(
    preset: Preset,
    filament: Filament,
    db: AsyncSession | None = None,
) -> str:
    """
    Экспортировать Preset в JSON строку формата OrcaSlicer.

    Args:
        preset: Preset из FilamentHub
        filament: Filament из FilamentHub
        db: AsyncSession для запросов к БД (опционально, для маппинга материалов)

    Returns:
        str: JSON строка профиля OrcaSlicer
    """
    profile = await preset_to_orcaslicer_json(preset, filament, db)
    return json.dumps(profile, indent=4, ensure_ascii=False)


def generate_profile_info(preset: Preset, filament: Filament) -> str:
    """
    Генерировать .info файл в формате INI для OrcaSlicer.

    Формат .info файла OrcaSlicer (INI):
    sync_info = значение (или пустая строка)
    user_id = значение (или пустая строка)
    setting_id = значение
    base_id = значение (или "null")
    updated_time = timestamp (число)

    Args:
        preset: Preset из FilamentHub
        filament: Filament из FilamentHub

    Returns:
        str: Содержимое .info файла в формате INI
    """
    from datetime import datetime

    setting_id = f"FHUB{preset.id:06d}"

    # base_id обычно пустой для пользовательских профилей, или "null"
    base_id = "null"

    # user_id - ID пользователя из FilamentHub (если есть)
    user_id = str(preset.user_id) if preset.user_id else ""

    # sync_info - для FilamentHub пресетов указываем источник синхронизации
    # Формат: "filamenthub:preset:{preset_id}"
    if preset.user_id:  # Если пресет принадлежит пользователю (не системный)
        sync_info = f"filamenthub:preset:{preset.id}"
    else:
        sync_info = ""

    # updated_time - timestamp последнего обновления
    if preset.updated_at:
        updated_time = int(preset.updated_at.timestamp())
    elif preset.created_at:
        updated_time = int(preset.created_at.timestamp())
    else:
        updated_time = int(datetime.utcnow().timestamp())

    # Формируем INI файл
    info_lines = [
        f"sync_info = {sync_info}",
        f"user_id = {user_id}",
        f"setting_id = {setting_id}",
        f"base_id = {base_id}",
        f"updated_time = {updated_time}",
    ]

    return "\n".join(info_lines)
