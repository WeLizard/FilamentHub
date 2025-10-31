"""Preset recommender service (weighted average algorithm)."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset import Preset, PresetModerationStatus
from app.models.filament import Filament


def calculate_preset_weight(preset: Preset) -> float:
    """
    Вычислить вес пресета для weighted average.
    
    Формула: base_weight * usage_factor * official_bonus
    
    - base_weight: rating (если есть) или usage_count / 10
    - usage_factor: 1 + (usage_count / 100)
    - official_bonus: 1.5 для официальных, 1.0 для пользовательских
    """
    base_weight = preset.rating if preset.rating is not None else (preset.usage_count / 10.0)
    if base_weight <= 0:
        base_weight = 1.0  # Минимальный вес для участия в расчете
    
    usage_factor = 1 + (preset.usage_count / 100.0)
    official_bonus = 1.5 if preset.is_official else 1.0
    
    return base_weight * usage_factor * official_bonus


def weighted_average_optional(values_and_weights: list[tuple[float, float]]) -> float | None:
    """
    Вычислить weighted average для опциональных параметров.
    
    Возвращает None если нет значений.
    """
    filtered = [(v, w) for v, w in values_and_weights if v is not None]
    if not filtered:
        return None
    
    total_weight = sum(w for _, w in filtered)
    if total_weight == 0:
        return None
    
    return sum(v * w for v, w in filtered) / total_weight


async def get_recommended_preset_values(
    filament_id: int,
    db: AsyncSession,
) -> dict[str, float | int | None]:
    """
    Получить рекомендованные значения настроек для материала (weighted average).
    
    Returns:
        dict с ключами: extruder_temp, bed_temp, print_speed, travel_speed,
        layer_height, first_layer_height, flow_rate, fan_speed,
        retraction_length, retraction_speed, avg_rating, presets_count
    """
    # Проверяем существование материала
    filament_result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = filament_result.scalar_one_or_none()
    
    if not filament:
        raise ValueError(f"Filament {filament_id} not found")
    
    # Получаем все одобренные пресеты для материала
    query = select(Preset).where(
        Preset.filament_id == filament_id,
        Preset.active == True,
        or_(
            Preset.moderation_status == PresetModerationStatus.APPROVED,
            Preset.is_official == True
        )
    )
    result = await db.execute(query)
    presets = result.scalars().all()
    
    if not presets:
        raise ValueError(f"No approved presets found for filament {filament_id}")
    
    # Вычисляем веса
    weights = [calculate_preset_weight(p) for p in presets]
    total_weight = sum(weights)
    
    if total_weight == 0:
        raise ValueError("Unable to calculate recommendation (zero total weight)")
    
    # Вычисляем weighted average для обязательных параметров
    extruder_temp = sum(p.extruder_temp * w for p, w in zip(presets, weights)) / total_weight
    bed_temp = sum(p.bed_temp * w for p, w in zip(presets, weights)) / total_weight
    print_speed = sum(p.print_speed * w for p, w in zip(presets, weights)) / total_weight
    
    # Вычисляем weighted average для опциональных параметров
    travel_speed = weighted_average_optional(
        [(p.travel_speed, w) if p.travel_speed is not None else (None, w) for p, w in zip(presets, weights)]
    )
    layer_height = weighted_average_optional(
        [(p.layer_height, w) if p.layer_height is not None else (None, w) for p, w in zip(presets, weights)]
    )
    first_layer_height = weighted_average_optional(
        [(p.first_layer_height, w) if p.first_layer_height is not None else (None, w) for p, w in zip(presets, weights)]
    )
    flow_rate = weighted_average_optional(
        [(p.flow_rate, w) if p.flow_rate is not None else (None, w) for p, w in zip(presets, weights)]
    )
    
    # fan_speed - целое число
    fan_speed_values = [(p.fan_speed, w) for p, w in zip(presets, weights) if p.fan_speed is not None]
    fan_speed = None
    if fan_speed_values:
        fan_speed_avg = sum(v * w for v, w in fan_speed_values) / sum(w for _, w in fan_speed_values)
        fan_speed = round(fan_speed_avg)
    
    retraction_length = weighted_average_optional(
        [(p.retraction_length, w) if p.retraction_length is not None else (None, w) for p, w in zip(presets, weights)]
    )
    retraction_speed = weighted_average_optional(
        [(p.retraction_speed, w) if p.retraction_speed is not None else (None, w) for p, w in zip(presets, weights)]
    )
    
    # Вычисляем средний рейтинг
    ratings = [p.rating for p in presets if p.rating is not None]
    avg_rating = sum(ratings) / len(ratings) if ratings else None
    
    return {
        "extruder_temp": round(extruder_temp, 1),
        "bed_temp": round(bed_temp, 1),
        "print_speed": round(print_speed, 1),
        "travel_speed": round(travel_speed, 1) if travel_speed is not None else None,
        "layer_height": round(layer_height, 3) if layer_height is not None else None,
        "first_layer_height": round(first_layer_height, 3) if first_layer_height is not None else None,
        "flow_rate": round(flow_rate, 1) if flow_rate is not None else None,
        "fan_speed": fan_speed,
        "retraction_length": round(retraction_length, 2) if retraction_length is not None else None,
        "retraction_speed": round(retraction_speed, 1) if retraction_speed is not None else None,
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "presets_count": len(presets),
    }

