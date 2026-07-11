"""
Preset recommender service («мудрость толпы» через взвешенную медиану).

Применяет:
- Взвешенную медиану: робастную к выбросам/опечаткам оценку центра по выборке пресетов
- Метку уверенности: качество оценки растёт с размером выборки (малая выборка — предварительно)
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament import Filament
from app.models.preset import PUBLIC_PRESET_STATUSES, Preset


def calculate_preset_weight(preset: Preset) -> float:
    """
    Вычислить вес пресета для weighted average (закон больших чисел).

    Формула: base_weight * usage_factor * official_bonus

    - base_weight: rating (если есть) или usage_count / 10 (метод Ферми: оценка через порядок величины)
    - usage_factor: 1 + (usage_count / 100) - больше использований = больше доверия
    - official_bonus: 1.5 для официальных, 1.0 для пользовательских

    Метод Ферми: если нет рейтинга, оцениваем через порядок величины usage_count / 10
    """
    # Метод Ферми: оценка веса через порядок величины
    base_weight = preset.rating if preset.rating is not None else (preset.usage_count / 10.0)
    if base_weight <= 0:
        base_weight = 1.0  # Минимальный вес для участия в расчете

    # Закон больших чисел: больше использований = больше доверия
    usage_factor = 1 + (preset.usage_count / 100.0)
    official_bonus = 1.5 if preset.is_official else 1.0

    return base_weight * usage_factor * official_bonus


def weighted_median(values_and_weights: list[tuple[float | None, float]]) -> float | None:
    """Взвешенная медиана — робастный оценщик «мудрости толпы».

    В отличие от взвешенного среднего, пара выбросов/опечаток (например кто-то
    вписал 260 °C для PLA) не тянет результат: берём значение, на котором
    накопленный вес впервые достигает половины суммарного. None — если нет
    пригодных значений.
    """
    pairs = sorted(
        ((v, w) for v, w in values_and_weights if v is not None and w > 0),
        key=lambda vw: vw[0],
    )
    if not pairs:
        return None
    half = sum(w for _, w in pairs) / 2
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= half:
            return value
    return pairs[-1][0]


def confidence_from_sample_size(n: int) -> str:
    """Уверенность оценки по размеру выборки (мудрость толпы включается на объёме).

    Малая выборка — «предварительно»; большая — «уверенно». Не выдаём грубую
    оценку по 4 пресетам за истину.
    """
    if n >= 20:
        return "high"
    if n >= 8:
        return "medium"
    return "low"


async def get_recommended_preset_values(
    filament_id: int,
    db: AsyncSession,
) -> dict[str, float | int | None]:
    """
    Получить рекомендованные значения настроек для материала.

    «Мудрость толпы» через взвешенную медиану (робастную к выбросам/опечаткам):
    - веса пресетов = usage_count × success_rate (доверие к источнику);
    - все значения — свойства этой катушки, поэтому cohort задан filament_id;
    - уверенность оценки растёт с размером выборки (см. confidence).

    Returns:
        dict с ключами: extruder_temp, bed_temp, print_speed, travel_speed,
        layer_height, first_layer_height, flow_rate, fan_speed,
        retraction_length, retraction_speed, avg_rating, presets_count,
        confidence ("low" | "medium" | "high" по размеру выборки)
    """
    # Проверяем существование материала
    filament_result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = filament_result.scalar_one_or_none()

    if not filament:
        raise ValueError(f"Filament {filament_id} not found")

    # Получаем все одобренные пресеты для материала
    # Исключаем взвешенные пресеты (is_weighted=True), чтобы избежать рекурсии
    query = select(Preset).where(
        Preset.filament_id == filament_id,
        Preset.active == True,
        Preset.is_weighted == False,  # Исключаем взвешенные пресеты
        or_(
            Preset.moderation_status.in_(PUBLIC_PRESET_STATUSES),
            Preset.is_official == True
        )
    )
    result = await db.execute(query)
    presets = result.scalars().all()

    if not presets:
        raise ValueError(f"No approved presets found for filament {filament_id}")

    # Метод Ферми: минимальный порог для статистической значимости
    # При малом количестве данных оценка менее точна
    # Порог 4 пресета - компромисс между точностью и доступностью данных
    # (проверка на минимум выполняется в weighted_preset_service, здесь только комментарий)

    # Закон больших чисел: вычисляем веса для взвешенного среднего
    # Чем больше пресетов, тем точнее будет результат (n → ∞ → точность ↑)
    weights = [calculate_preset_weight(p) for p in presets]
    total_weight = sum(weights)

    if total_weight == 0:
        raise ValueError("Unable to calculate recommendation (zero total weight)")

    # Взвешенная медиана по всем параметрам — робастность к выбросам/опечаткам.
    # Все значения — свойства этой катушки (material scope после Ф5), поэтому cohort
    # уже задан filament_id; принтер их не разводит на «разные распределения».
    def _median(getter) -> float | None:
        return weighted_median([(getter(p), w) for p, w in zip(presets, weights, strict=False)])

    extruder_temp = _median(lambda p: p.extruder_temp)
    bed_temp = _median(lambda p: p.bed_temp)
    flow_rate = _median(lambda p: p.flow_rate)

    fan_median = _median(lambda p: p.fan_speed)
    fan_speed = round(fan_median) if fan_median is not None else None

    retraction_length = _median(lambda p: p.retraction_length)
    retraction_speed = _median(lambda p: p.retraction_speed)

    # Вычисляем средний рейтинг
    ratings = [p.rating for p in presets if p.rating is not None]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    return {
        "extruder_temp": round(extruder_temp, 1),
        "bed_temp": round(bed_temp, 1),
        "flow_rate": round(flow_rate, 1) if flow_rate is not None else None,
        "fan_speed": fan_speed,
        "retraction_length": round(retraction_length, 2) if retraction_length is not None else None,
        "retraction_speed": round(retraction_speed, 1) if retraction_speed is not None else None,
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "presets_count": len(presets),
        "confidence": confidence_from_sample_size(len(presets)),
    }

