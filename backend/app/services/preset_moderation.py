"""Сервис автоматической модерации пресетов."""

import logging
import re
from typing import Any, Optional

from better_profanity import profanity
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament import Filament

# BadWord импортируется лениво в _load_bad_words_from_db, чтобы не падать при отсутствии таблицы
from app.models.preset import Preset, PresetModerationStatus

logger = logging.getLogger(__name__)

# Инициализируем библиотеку better-profanity
# По умолчанию она работает с английским языком
try:
    profanity.load_censor_words()
except Exception:
    logger.warning("Failed to load profanity censor words", exc_info=True)


# Справочные данные для типов материалов (температуры в градусах Цельсия)
# Структура: {"min": минимальное значение (жёсткое ограничение),
#            "max": максимальное значение (жёсткое ограничение),
#            "soft_min": мягкое ограничение (предупреждение),
#            "soft_max": мягкое ограничение (предупреждение),
#            "typical": типичное значение}

MATERIAL_SETTINGS_RANGES = {
    "PLA": {
        "extruder_temp": {"min": 150, "max": 280, "soft_min": 170, "soft_max": 250, "typical": 200},
        "bed_temp": {"min": 0, "max": 100, "soft_min": 40, "soft_max": 80, "typical": 60},
        "print_speed": {"min": 10, "max": 200, "soft_min": 20, "soft_max": 150, "typical": 60},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 30, "soft_max": 100, "typical": 100},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.5, "soft_max": 10, "typical": 5.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 20, "soft_max": 120, "typical": 45},
    },
    "PLA+": {
        "extruder_temp": {"min": 170, "max": 290, "soft_min": 190, "soft_max": 260, "typical": 215},
        "bed_temp": {"min": 0, "max": 100, "soft_min": 45, "soft_max": 80, "typical": 60},
        "print_speed": {"min": 10, "max": 200, "soft_min": 25, "soft_max": 150, "typical": 60},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 40, "soft_max": 100, "typical": 100},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.5, "soft_max": 10, "typical": 5.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 20, "soft_max": 120, "typical": 45},
    },
    "ABS": {
        "extruder_temp": {"min": 200, "max": 320, "soft_min": 220, "soft_max": 290, "typical": 250},
        "bed_temp": {"min": 50, "max": 130, "soft_min": 75, "soft_max": 115, "typical": 90},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 40, "typical": 0},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 5.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 40},
    },
    "ABS+": {
        "extruder_temp": {"min": 210, "max": 320, "soft_min": 225, "soft_max": 290, "typical": 250},
        "bed_temp": {"min": 50, "max": 130, "soft_min": 75, "soft_max": 115, "typical": 90},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 40, "typical": 0},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 5.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 40},
    },
    "PETG": {
        "extruder_temp": {"min": 200, "max": 300, "soft_min": 215, "soft_max": 270, "typical": 240},
        "bed_temp": {"min": 50, "max": 110, "soft_min": 65, "soft_max": 95, "typical": 80},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 15, "soft_max": 90, "typical": 50},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 3.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 20, "soft_max": 100, "typical": 35},
    },
    "PETG+": {
        "extruder_temp": {"min": 210, "max": 300, "soft_min": 225, "soft_max": 270, "typical": 245},
        "bed_temp": {"min": 50, "max": 110, "soft_min": 65, "soft_max": 95, "typical": 80},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 15, "soft_max": 90, "typical": 50},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 3.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 20, "soft_max": 100, "typical": 35},
    },
    "TPU": {
        "extruder_temp": {"min": 190, "max": 280, "soft_min": 205, "soft_max": 260, "typical": 230},
        "bed_temp": {"min": 0, "max": 90, "soft_min": 35, "soft_max": 75, "typical": 50},
        "print_speed": {"min": 5, "max": 80, "soft_min": 10, "soft_max": 60, "typical": 30},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 60, "typical": 30},
        "retraction_length": {"min": 0, "max": 10, "soft_min": 0.3, "soft_max": 5, "typical": 1.0},
        "retraction_speed": {"min": 5, "max": 80, "soft_min": 10, "soft_max": 60, "typical": 20},
    },
    "ASA": {
        "extruder_temp": {"min": 220, "max": 320, "soft_min": 235, "soft_max": 290, "typical": 260},
        "bed_temp": {"min": 50, "max": 130, "soft_min": 75, "soft_max": 115, "typical": 90},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 40, "typical": 0},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 5.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 40},
    },
    "PC": {
        "extruder_temp": {"min": 240, "max": 350, "soft_min": 255, "soft_max": 320, "typical": 280},
        "bed_temp": {"min": 70, "max": 140, "soft_min": 85, "soft_max": 125, "typical": 100},
        "print_speed": {"min": 5, "max": 120, "soft_min": 15, "soft_max": 100, "typical": 40},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 60, "typical": 30},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 4.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 40},
    },
    "PA": {
        "extruder_temp": {"min": 220, "max": 320, "soft_min": 235, "soft_max": 290, "typical": 260},
        "bed_temp": {"min": 50, "max": 120, "soft_min": 65, "soft_max": 105, "typical": 80},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 60, "typical": 30},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 4.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 40},
    },
    "PA-CF": {
        "extruder_temp": {"min": 230, "max": 330, "soft_min": 245, "soft_max": 300, "typical": 270},
        "bed_temp": {"min": 60, "max": 130, "soft_min": 75, "soft_max": 115, "typical": 90},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 60, "typical": 30},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 4.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 40},
    },
    "PLA-CF": {
        "extruder_temp": {"min": 180, "max": 280, "soft_min": 195, "soft_max": 250, "typical": 220},
        "bed_temp": {"min": 0, "max": 100, "soft_min": 45, "soft_max": 80, "typical": 60},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 40, "soft_max": 100, "typical": 100},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.5, "soft_max": 10, "typical": 5.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 20, "soft_max": 120, "typical": 45},
    },
    "PEEK": {
        "extruder_temp": {"min": 340, "max": 450, "soft_min": 350, "soft_max": 430, "typical": 390},
        "bed_temp": {"min": 100, "max": 170, "soft_min": 115, "soft_max": 155, "typical": 130},
        "print_speed": {"min": 5, "max": 80, "soft_min": 10, "soft_max": 60, "typical": 30},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 40, "typical": 0},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 3.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 20, "soft_max": 100, "typical": 40},
    },
    "HIPS": {
        "extruder_temp": {"min": 200, "max": 300, "soft_min": 215, "soft_max": 270, "typical": 240},
        "bed_temp": {"min": 50, "max": 130, "soft_min": 75, "soft_max": 115, "typical": 90},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 60, "typical": 30},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 5.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 40},
    },
    "PP": {
        "extruder_temp": {"min": 200, "max": 300, "soft_min": 215, "soft_max": 270, "typical": 240},
        "bed_temp": {"min": 50, "max": 120, "soft_min": 65, "soft_max": 105, "typical": 80},
        "print_speed": {"min": 10, "max": 150, "soft_min": 25, "soft_max": 120, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 0, "soft_max": 60, "typical": 30},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.8, "soft_max": 10, "typical": 3.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 20, "soft_max": 100, "typical": 35},
    },
    "PVA": {
        "extruder_temp": {"min": 160, "max": 250, "soft_min": 175, "soft_max": 230, "typical": 200},
        "bed_temp": {"min": 0, "max": 80, "soft_min": 35, "soft_max": 65, "typical": 50},
        "print_speed": {"min": 10, "max": 120, "soft_min": 25, "soft_max": 100, "typical": 50},
        "fan_speed": {"min": 0, "max": 100, "soft_min": 40, "soft_max": 100, "typical": 80},
        "retraction_length": {"min": 0, "max": 15, "soft_min": 0.5, "soft_max": 10, "typical": 4.0},
        "retraction_speed": {"min": 10, "max": 150, "soft_min": 20, "soft_max": 120, "typical": 40},
    },
}

# Кэш для слов из БД (чтобы не грузить каждый раз)
_BAD_WORDS_CACHE: dict[str, list[str]] = {}


async def _load_bad_words_from_db(db: AsyncSession) -> tuple[list[str], list[str]]:
    """Загрузить списки плохих слов из БД (с кэшированием)."""
    global _BAD_WORDS_CACHE

    # Если кэш не пустой, возвращаем из кэша
    if "ru" in _BAD_WORDS_CACHE and "en" in _BAD_WORDS_CACHE:
        return _BAD_WORDS_CACHE["ru"], _BAD_WORDS_CACHE["en"]

    # Загружаем из БД с обработкой ошибок (на случай, если таблица еще не создана)
    try:
        # Ленивый импорт модели, чтобы не падать при инициализации модуля
        from app.models.bad_word import BadWord

        result = await db.execute(select(BadWord))
        bad_words = result.scalars().all()

        bad_words_ru = []
        bad_words_en = []

        for word in bad_words:
            if word.language == "ru":
                bad_words_ru.append(word.word.lower())
            elif word.language == "en":
                bad_words_en.append(word.word.lower())

        # Кэшируем результаты
        _BAD_WORDS_CACHE["ru"] = bad_words_ru
        _BAD_WORDS_CACHE["en"] = bad_words_en

        return bad_words_ru, bad_words_en
    except Exception as e:
        # Если таблицы нет или произошла ошибка, возвращаем пустые списки и кэшируем их
        # Это предотвращает повторные попытки запроса к несуществующей таблице
        # Логируем ошибку для отладки, но не падаем
        logger.warning("Failed to load bad words from DB: %s. Using empty lists.", e)

        _BAD_WORDS_CACHE["ru"] = []
        _BAD_WORDS_CACHE["en"] = []
        return [], []


async def validate_text_field(text: str | None, db: AsyncSession, field_name: str = "field") -> tuple[bool, Optional[dict | str]]:
    """
    Универсальная функция для проверки текстового поля на плохие слова.

    Args:
        text: Текст для проверки (может быть None)
        db: Сессия БД для загрузки слов из базы
        field_name: Название поля (для сообщения об ошибке)

    Returns:
        (is_valid, reason): (True, None) если всё ок, (False, error_detail) если найдены проблемы.
        error_detail is a dict {"code": "ERR_...", "params": {...}} ready for HTTPException detail.
    """
    if not text:
        return True, None

    return await check_bad_words(text, db, field_name)


async def check_bad_words(text: str, db: AsyncSession, field_name: str = "field") -> tuple[bool, Optional[dict]]:
    """
    Проверить текст на наличие плохих слов.

    Использует библиотеку better-profanity для английского языка
    и пользовательский список из БД для русского и английского.

    Args:
        text: Текст для проверки
        db: Сессия БД для загрузки слов из базы

    Returns:
        (is_valid, reason): (True, None) если всё ок,
        (False, {"code": ..., "params": ...}) если найдены плохие слова
    """
    if not text:
        return True, None

    text_lower = text.lower()

    bad_words_error = {"code": "ERR_BAD_WORDS", "params": {"field_name": field_name}}

    # 1. Проверяем через библиотеку better-profanity (английский язык)
    try:
        if profanity.contains_profanity(text):
            return False, bad_words_error
    except Exception:
        logger.warning("Profanity check failed", exc_info=True)

    # 2. Загружаем пользовательские слова из БД
    bad_words_ru, bad_words_en = await _load_bad_words_from_db(db)

    # 3. Проверяем русские плохие слова из БД
    for word in bad_words_ru:
        # Проверяем точное вхождение слова (word boundaries)
        pattern = r'\b' + re.escape(word) + r'\b'
        if re.search(pattern, text_lower, re.IGNORECASE):
            return False, bad_words_error

    # 4. Проверяем английские плохие слова из БД (дополнительно к библиотеке)
    for word in bad_words_en:
        pattern = r'\b' + re.escape(word) + r'\b'
        if re.search(pattern, text_lower, re.IGNORECASE):
            return False, bad_words_error

    # 5. Проверка на спам (повторяющиеся символы)
    if re.search(r'(.)\1{4,}', text):  # 5+ одинаковых символов подряд
        return False, {"code": "ERR_REPEATED_CHARS", "params": {"field_name": field_name}}

    # 6. Проверка на только спецсимволы (только для полей с обязательным текстом)
    if not re.search(r'[a-zA-Zа-яА-Я0-9]', text):
        return False, {"code": "ERR_NO_LETTERS_OR_DIGITS", "params": {"field_name": field_name}}

    return True, None


def validate_preset_settings(
    preset: Preset, filament: Filament
) -> tuple[bool, Optional[dict]]:
    """
    Проверить настройки пресета на разумность для типа материала.

    Returns:
        (is_valid, reason): (True, None) если всё ок,
        (False, {"code": ..., "params": ...}) если найдены проблемы
    """
    material_type = filament.material_type.upper() if filament.material_type else None

    # Если тип материала не найден в справочнике, используем общие ограничения
    if material_type not in MATERIAL_SETTINGS_RANGES:
        # Общие ограничения (жёсткие) - отсекаем только совсем абсурдные значения
        ranges = {
            "extruder_temp": {"min": 100, "max": 500},
            "bed_temp": {"min": 0, "max": 200},
            "print_speed": {"min": 1, "max": 300},
            "fan_speed": {"min": 0, "max": 100},
            "retraction_length": {"min": 0, "max": 20},
            "retraction_speed": {"min": 1, "max": 200},
        }
    else:
        ranges = MATERIAL_SETTINGS_RANGES[material_type]

    # Проверка температуры экструдера
    if preset.extruder_temp:
        if preset.extruder_temp < ranges["extruder_temp"]["min"]:
            return False, {"code": "ERR_EXTRUDER_TEMP_TOO_LOW", "params": {"value": preset.extruder_temp, "min": ranges["extruder_temp"]["min"]}}
        if preset.extruder_temp > ranges["extruder_temp"]["max"]:
            return False, {"code": "ERR_EXTRUDER_TEMP_TOO_HIGH", "params": {"value": preset.extruder_temp, "max": ranges["extruder_temp"]["max"]}}

    # Проверка температуры стола
    if preset.bed_temp:
        if preset.bed_temp < ranges["bed_temp"]["min"]:
            return False, {"code": "ERR_BED_TEMP_TOO_LOW", "params": {"value": preset.bed_temp, "min": ranges["bed_temp"]["min"]}}
        if preset.bed_temp > ranges["bed_temp"]["max"]:
            return False, {"code": "ERR_BED_TEMP_TOO_HIGH", "params": {"value": preset.bed_temp, "max": ranges["bed_temp"]["max"]}}

    # Проверка скорости печати
    if preset.print_speed:
        if preset.print_speed < ranges["print_speed"]["min"]:
            return False, {"code": "ERR_PRINT_SPEED_TOO_LOW", "params": {"value": preset.print_speed, "min": ranges["print_speed"]["min"]}}
        if preset.print_speed > ranges["print_speed"]["max"]:
            return False, {"code": "ERR_PRINT_SPEED_TOO_HIGH", "params": {"value": preset.print_speed, "max": ranges["print_speed"]["max"]}}

    # Проверка скорости вентилятора (всегда 0-100%)
    if preset.fan_speed is not None:
        if preset.fan_speed < ranges["fan_speed"]["min"]:
            return False, {"code": "ERR_FAN_SPEED_TOO_LOW", "params": {"value": preset.fan_speed, "min": ranges["fan_speed"]["min"], "max": ranges["fan_speed"]["max"]}}
        if preset.fan_speed > ranges["fan_speed"]["max"]:
            return False, {"code": "ERR_FAN_SPEED_TOO_HIGH", "params": {"value": preset.fan_speed, "min": ranges["fan_speed"]["min"], "max": ranges["fan_speed"]["max"]}}

    # Проверка длины ретракта
    if preset.retraction_length is not None:
        if preset.retraction_length < ranges["retraction_length"]["min"]:
            return False, {"code": "ERR_RETRACTION_LEN_TOO_LOW", "params": {"value": preset.retraction_length, "min": ranges["retraction_length"]["min"], "max": ranges["retraction_length"]["max"]}}
        if preset.retraction_length > ranges["retraction_length"]["max"]:
            return False, {"code": "ERR_RETRACTION_LEN_TOO_HIGH", "params": {"value": preset.retraction_length, "max": ranges["retraction_length"]["max"]}}

    # Проверка скорости ретракта
    if preset.retraction_speed is not None:
        if preset.retraction_speed < ranges["retraction_speed"]["min"]:
            return False, {"code": "ERR_RETRACTION_SPEED_TOO_LOW", "params": {"value": preset.retraction_speed, "min": ranges["retraction_speed"]["min"]}}
        if preset.retraction_speed > ranges["retraction_speed"]["max"]:
            return False, {"code": "ERR_RETRACTION_SPEED_TOO_HIGH", "params": {"value": preset.retraction_speed, "max": ranges["retraction_speed"]["max"]}}

    # Температура стола значительно выше температуры экструдера (абсурдно)
    if preset.bed_temp and preset.extruder_temp:
        if preset.bed_temp > preset.extruder_temp + 80:
            return False, {"code": "ERR_BED_TEMP_EXCEEDS_EXTRUDER", "params": {"bed_temp": preset.bed_temp, "extruder_temp": preset.extruder_temp}}

    return True, None


MANUAL_REVIEW_SCORE_THRESHOLD = 25


def _collect_soft_range_flags(preset: Preset, filament: Filament) -> list[dict[str, Any]]:
    """Собрать мягкие предупреждения (выбросы) по типичным диапазонам."""
    material_type = filament.material_type.upper() if filament.material_type else None
    if not material_type or material_type not in MATERIAL_SETTINGS_RANGES:
        return []

    ranges = MATERIAL_SETTINGS_RANGES[material_type]
    checks: list[tuple[str, float | int | None]] = [
        ("extruder_temp", preset.extruder_temp),
        ("bed_temp", preset.bed_temp),
        ("print_speed", preset.print_speed),
        ("fan_speed", preset.fan_speed),
        ("retraction_length", preset.retraction_length),
        ("retraction_speed", preset.retraction_speed),
    ]

    flags: list[dict[str, Any]] = []
    for field_name, value in checks:
        if value is None:
            continue

        field_range = ranges.get(field_name, {})
        soft_min = field_range.get("soft_min")
        soft_max = field_range.get("soft_max")
        if soft_min is None or soft_max is None:
            continue

        numeric_value = float(value)
        if soft_min <= numeric_value <= soft_max:
            continue

        # Нормализуем отклонение к [0..]
        if numeric_value < soft_min:
            deviation = (soft_min - numeric_value) / max(abs(float(soft_min)), 1.0)
        else:
            deviation = (numeric_value - soft_max) / max(abs(float(soft_max)), 1.0)

        if deviation >= 0.20:
            score = 20
            severity = "high"
        elif deviation >= 0.10:
            score = 14
            severity = "medium"
        else:
            score = 8
            severity = "low"

        flags.append(
            {
                "code": "WARN_PRESET_PARAM_OUTSIDE_TYPICAL_RANGE",
                "params": {
                    "field_name": field_name,
                    "value": round(numeric_value, 3),
                    "soft_min": soft_min,
                    "soft_max": soft_max,
                    "material_type": material_type,
                },
                "severity": severity,
                "score": score,
            }
        )

    return flags


def _is_setting_close(a: float | int | None, b: float | int | None, tolerance: float) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tolerance


def _looks_like_duplicate_settings(preset: Preset, candidate: Preset) -> bool:
    comparisons = [
        (preset.extruder_temp, candidate.extruder_temp, 3.0),
        (preset.bed_temp, candidate.bed_temp, 3.0),
        (preset.print_speed, candidate.print_speed, 8.0),
        (preset.flow_rate, candidate.flow_rate, 4.0),
        (preset.fan_speed, candidate.fan_speed, 12.0),
        (preset.retraction_length, candidate.retraction_length, 0.8),
        (preset.retraction_speed, candidate.retraction_speed, 8.0),
    ]

    compared = 0
    matched = 0
    for left, right, tolerance in comparisons:
        if left is None or right is None:
            continue
        compared += 1
        if _is_setting_close(left, right, tolerance):
            matched += 1

    if compared < 4:
        return False
    return matched >= max(3, compared - 1)


async def _find_duplicate_preset_flag(
    preset: Preset,
    db: AsyncSession,
) -> dict[str, Any] | None:
    """Проверить, не выглядит ли пресет как дубликат уже существующего."""
    if not preset.user_id or not preset.filament_id or not preset.name:
        return None

    normalized_name = preset.name.strip().lower()
    if not normalized_name:
        return None

    query = select(Preset).where(
        Preset.user_id == preset.user_id,
        Preset.filament_id == preset.filament_id,
        func.lower(Preset.name) == normalized_name,
        Preset.moderation_status != PresetModerationStatus.REJECTED,
    )
    if preset.id:
        query = query.where(Preset.id != preset.id)

    result = await db.execute(query.limit(10))
    candidates = result.scalars().all()
    for candidate in candidates:
        if _looks_like_duplicate_settings(preset, candidate):
            return {
                "code": "WARN_PRESET_POSSIBLE_DUPLICATE",
                "params": {
                    "duplicate_preset_id": candidate.id,
                    "duplicate_preset_name": candidate.name,
                },
                "severity": "medium",
                "score": 18,
            }

    return None


async def moderate_preset(
    preset: Preset,
    filament: Filament,
    db: AsyncSession,
    is_official: bool = False,
    allow_manual_review: bool = True,
) -> tuple[PresetModerationStatus, Optional[dict[str, Any] | str]]:
    """
    Автоматическая модерация пресета.

    Args:
        preset: Пресет для модерации
        filament: Материал пресета
        db: Сессия БД для проверки плохих слов
        is_official: Является ли пресет официальным (от производителя)
        allow_manual_review: Разрешать ли перевод в PENDING по мягким риск-сигналам

    Returns:
        (status, reason): Статус модерации и причина (если отклонен)
    """
    # Официальные пресеты всегда одобряются автоматически (доверяем производителям)
    if is_official:
        return PresetModerationStatus.APPROVED, None

    # Проверка названия на плохие слова
    if preset.name:
        is_valid_name, name_reason = await check_bad_words(preset.name, db)
        if not is_valid_name:
            return PresetModerationStatus.REJECTED, name_reason

    # Проверка описания на плохие слова (если есть)
    if preset.description:
        is_valid_desc, desc_reason = await check_bad_words(preset.description, db)
        if not is_valid_desc:
            return PresetModerationStatus.REJECTED, desc_reason

    # Проверка настроек на разумность
    is_valid_settings, settings_reason = validate_preset_settings(preset, filament)
    if not is_valid_settings:
        return PresetModerationStatus.REJECTED, settings_reason

    # Мягкие сигналы риска -> отправляем на ручную модерацию (если включено)
    flags = _collect_soft_range_flags(preset, filament)
    duplicate_flag = await _find_duplicate_preset_flag(preset, db)
    if duplicate_flag is not None:
        flags.append(duplicate_flag)

    risk_score = int(sum(int(flag.get("score", 0)) for flag in flags))
    if allow_manual_review and risk_score >= MANUAL_REVIEW_SCORE_THRESHOLD:
        return (
            PresetModerationStatus.PENDING,
            {
                "code": "ERR_PRESET_REQUIRES_MANUAL_REVIEW",
                "params": {
                    "risk_score": risk_score,
                    "flags_count": len(flags),
                },
                "flags": [
                    {
                        "code": flag.get("code"),
                        "params": flag.get("params", {}),
                        "severity": flag.get("severity", "low"),
                    }
                    for flag in flags
                ],
            },
        )

    if not allow_manual_review and risk_score >= MANUAL_REVIEW_SCORE_THRESHOLD:
        logger.info(
            "Preset auto-approved with manual review disabled (risk_score=%s, flags=%s)",
            risk_score,
            len(flags),
        )

    # Всё ок, одобряем автоматически
    return PresetModerationStatus.APPROVED, None
