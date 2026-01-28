"""Сервис для экспорта профилей FilamentHub в формат OrcaSlicer."""

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament import Filament
from app.models.preset import Preset
from app.services.material_mapping_service import get_material_preset
from app.services.profile_validator import (
    validate_filament_profile,
    log_validation_result,
)

logger = logging.getLogger(__name__)


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


async def preset_to_orcaslicer_json(
    preset: Preset,
    filament: Filament,
    db: AsyncSession | None = None,
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
        "name": preset.name,  # Имя пресета (будет добавлен постфикс [FilamentHub] в C++)
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

    # Вентилятор
    if preset.fan_speed is not None:
        fan_speed = max(0, min(100, preset.fan_speed))  # Ограничиваем 0-100
        profile["fan_min_speed"] = to_array(fan_speed)
        profile["fan_max_speed"] = to_array(100)
        profile["overhang_fan_speed"] = to_array(100)

    # Плотность филамента
    if filament.density is not None:
        profile["filament_density"] = to_array(round(filament.density, 2))

    # Диаметр филамента
    if filament.diameter is not None:
        profile["filament_diameter"] = to_array(str(filament.diameter))

    # Стоимость филамента (цена за кг в рублях, конвертируем в копейки для OrcaSlicer)
    if filament.price_per_kg is not None:
        # OrcaSlicer хранит стоимость в копейках за грамм
        price_per_g = int(filament.price_per_kg * 100 / 1000)  # рубли -> копейки за грамм
        profile["filament_cost"] = to_array(str(price_per_g))

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
    if preset.flow_rate:
        # flow_rate в FilamentHub это процент (например 100 = 100%)
        # В OrcaSlicer это множитель (например 1.0 = 100%)
        flow_ratio = preset.flow_rate / 100.0 if preset.flow_rate > 1 else preset.flow_rate
        profile["filament_flow_ratio"] = to_array(str(round(flow_ratio, 2)))

    # Расширенные параметры из JSON поля orcaslicer_settings
    # Эти параметры имеют приоритет над базовыми и добавляются в конец
    # Полезно для специальных настроек, которых нет в базовых полях FilamentHub
    if preset.orcaslicer_settings and isinstance(preset.orcaslicer_settings, dict) and len(preset.orcaslicer_settings) > 0:
        for key, value in preset.orcaslicer_settings.items():
            # Пропускаем только если значение None или пустое
            if value is not None:
                try:
                    # Конвертируем значение в массив строк если это еще не массив
                    if isinstance(value, list):
                        # Уже массив, проверяем что все элементы - строки
                        profile[key] = [str(v) for v in value]
                    else:
                        # Одиночное значение, конвертируем в массив строк (стандарт OrcaSlicer)
                        profile[key] = to_array(value)
                except Exception as e:
                    # Логируем ошибку, но продолжаем обработку остальных ключей
                    # Не критично если какой-то параметр не удалось экспортировать
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Error exporting key '{key}' from orcaslicer_settings: {str(e)}")
                    # Пропускаем проблемный ключ
                    continue

    # Если цвет не был выставлен расширенными настройками, берём его из данных филамента
    if "default_filament_colour" not in profile:
        if filament.color_hex:
            profile["default_filament_colour"] = [filament.color_hex]

    # Совместимые принтеры (пусто по умолчанию = совместим со всеми)
    # Можно расширить в будущем для специфических принтеров
    profile["compatible_printers"] = []

    # Метаданные FilamentHub для синхронизации
    # Добавляем метки в корень JSON профиля для идентификации "наших" пресетов
    # Эти метки безопасны и не конфликтуют с BambuLab синхронизацией
    # ВАЖНО: OrcaSlicer ожидает строки для fhub_id, не числа!
    profile["fhub_id"] = str(preset.id)
    profile["fhub_source"] = "filamenthub"
    
    # Для черновиков добавляем fhub_draft_id в корень JSON
    # Это позволяет найти черновик при следующей синхронизации
    if not preset.active and preset.orcaslicer_settings and isinstance(preset.orcaslicer_settings, dict):
        fhub_draft_id = preset.orcaslicer_settings.get("fhub_draft_id")
        if fhub_draft_id:
            # Убеждаемся, что fhub_draft_id - строка
            profile["fhub_draft_id"] = str(fhub_draft_id)
    
    # ВАЖНО: НЕ обновляем orcaslicer_settings в базе при экспорте!
    # Это вызывает изменение updated_at и бесконечный цикл экспорта.
    # Метки fhub_id и fhub_source обновляются только при импорте из OrcaSlicer.
    # При экспорте мы просто читаем существующие метки и добавляем их в JSON.

    # Итоговая структура JSON:
    # - Обязательные поля: version, name, from, inherits, filament_settings_id
    # - Уникальные идентификаторы: setting_id, filament_id
    # - Параметры печати: температуры, вентилятор, ретракт и т.д.
    # - Расширенные параметры: orcaslicer_settings (если есть)
    # - Метаданные FilamentHub: fhub_id, fhub_source (для синхронизации)
    #
    # При импорте в OrcaSlicer:
    # 1. Находит родительский пресет через inherits
    # 2. Копирует весь конфиг родителя
    # 3. Применяет параметры из этого JSON поверх родительского конфига
    # 4. Сохраняет как пользовательский пресет
    # 5. Метаданные fhub_id и fhub_source сохраняются в JSON профиля для обратной синхронизации

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

