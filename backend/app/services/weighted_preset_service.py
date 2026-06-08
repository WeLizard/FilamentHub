"""Сервис для управления динамическими взвешенными пресетами."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.services.preset_recommender import get_recommended_preset_values


async def create_or_update_weighted_preset(
    filament_id: int,
    db: AsyncSession,
    min_presets_count: int = 4,
) -> Preset | None:
    """
    Создать или обновить динамический взвешенный пресет для филамента.

    Взвешенный пресет автоматически пересчитывается на основе всех пресетов
    для этого материала (исключая сам взвешенный пресет).

    Args:
        filament_id: ID филамента
        db: Database session
        min_presets_count: Минимальное количество пресетов для создания взвешенного (по умолчанию 4)

    Returns:
        Preset или None, если недостаточно пресетов для расчета
    """
    # Проверяем существование филамента
    filament_result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = filament_result.scalar_one_or_none()

    if not filament:
        raise ValueError(f"Filament {filament_id} not found")

    # Получаем все пресеты для филамента (исключая взвешенные)
    query = select(Preset).where(
        Preset.filament_id == filament_id,
        Preset.active == True,
        Preset.is_weighted == False,  # Исключаем взвешенные пресеты
        Preset.moderation_status == PresetModerationStatus.APPROVED,
    )
    result = await db.execute(query)
    presets = result.scalars().all()

    # Проверяем минимальное количество пресетов
    if len(presets) < min_presets_count:
        # Если недостаточно пресетов, удаляем существующий взвешенный пресет (если есть)
        existing_weighted = await db.execute(
            select(Preset).where(
                Preset.filament_id == filament_id,
                Preset.is_weighted == True,
            )
        )
        weighted_preset = existing_weighted.scalar_one_or_none()
        if weighted_preset:
            weighted_preset.active = False
            await db.commit()
        return None

    # Вычисляем взвешенные значения (используем существующую функцию)
    try:
        recommended_values = await get_recommended_preset_values(filament_id, db)
    except ValueError:
        # Если не удалось вычислить (например, нет пресетов), удаляем взвешенный пресет
        existing_weighted = await db.execute(
            select(Preset).where(
                Preset.filament_id == filament_id,
                Preset.is_weighted == True,
            )
        )
        weighted_preset = existing_weighted.scalar_one_or_none()
        if weighted_preset:
            weighted_preset.active = False
            await db.commit()
        return None

    # Ищем существующий взвешенный пресет
    existing_weighted_result = await db.execute(
        select(Preset).where(
            Preset.filament_id == filament_id,
            Preset.is_weighted == True,
        )
    )
    weighted_preset = existing_weighted_result.scalar_one_or_none()

    # Формируем название: "{Название материала} Gen"
    preset_name = f"{filament.name} Gen"

    # Описание
    preset_description = f"Генеративно вычисляется на основе {recommended_values['presets_count']} пресетов для этого материала"

    if weighted_preset:
        # Обновляем существующий взвешенный пресет
        weighted_preset.name = preset_name
        weighted_preset.description = preset_description
        weighted_preset.extruder_temp = recommended_values['extruder_temp']
        weighted_preset.bed_temp = recommended_values['bed_temp']
        weighted_preset.print_speed = recommended_values['print_speed']
        weighted_preset.travel_speed = recommended_values.get('travel_speed')
        weighted_preset.layer_height = recommended_values.get('layer_height')
        weighted_preset.first_layer_height = recommended_values.get('first_layer_height')
        weighted_preset.flow_rate = recommended_values.get('flow_rate')
        weighted_preset.fan_speed = recommended_values.get('fan_speed')
        weighted_preset.retraction_length = recommended_values.get('retraction_length')
        weighted_preset.retraction_speed = recommended_values.get('retraction_speed')
        weighted_preset.active = True
        weighted_preset.moderation_status = PresetModerationStatus.APPROVED

        await db.commit()
        await db.refresh(weighted_preset)
        return weighted_preset
    else:
        # Создаем новый взвешенный пресет
        weighted_preset = Preset(
            filament_id=filament_id,
            user_id=None,  # Системный пресет
            name=preset_name,
            description=preset_description,
            extruder_temp=recommended_values['extruder_temp'],
            bed_temp=recommended_values['bed_temp'],
            print_speed=recommended_values['print_speed'],
            travel_speed=recommended_values.get('travel_speed'),
            layer_height=recommended_values.get('layer_height'),
            first_layer_height=recommended_values.get('first_layer_height'),
            flow_rate=recommended_values.get('flow_rate'),
            fan_speed=recommended_values.get('fan_speed'),
            retraction_length=recommended_values.get('retraction_length'),
            retraction_speed=recommended_values.get('retraction_speed'),
            is_official=False,
            is_weighted=True,  # Маркер взвешенного пресета
            active=True,
            moderation_status=PresetModerationStatus.APPROVED,
            usage_count=0,
            rating=None,
            success_rate=None,
        )

        db.add(weighted_preset)
        await db.commit()
        await db.refresh(weighted_preset)
        return weighted_preset

