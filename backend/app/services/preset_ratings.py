"""Сервис для обновления рейтингов пресетов на основе отзывов."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament_review import FilamentReview
from app.models.preset import Preset


async def update_preset_ratings(preset_id: int, db: AsyncSession) -> None:
    """
    Обновить рейтинг и успешность пресета на основе отзывов.
    
    Вычисляет:
    - preset.rating: средний рейтинг всех активных отзывов этого пресета
    - preset.success_rate: процент успешных печатей по этому пресету
    """
    # Получаем все активные отзывы для этого пресета
    reviews_result = await db.execute(
        select(FilamentReview).where(
            FilamentReview.preset_id == preset_id,
            FilamentReview.active == True,
        )
    )
    reviews = reviews_result.scalars().all()
    
    if not reviews:
        # Если нет отзывов, очищаем рейтинги
        preset_result = await db.execute(select(Preset).where(Preset.id == preset_id))
        preset = preset_result.scalar_one_or_none()
        if preset:
            preset.rating = None
            preset.success_rate = None
            await db.commit()
        return
    
    # Вычисляем средний рейтинг
    total_reviews = len(reviews)
    avg_rating = sum(r.rating for r in reviews) / total_reviews
    
    # Вычисляем процент успешных печатей
    success_count = sum(1 for r in reviews if r.success)
    success_rate = (success_count / total_reviews) * 100.0
    
    # Обновляем пресет
    preset_result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = preset_result.scalar_one_or_none()
    if preset:
        preset.rating = round(avg_rating, 2)
        preset.success_rate = round(success_rate, 1)
        await db.commit()


async def calculate_filament_weighted_rating(filament_id: int, db: AsyncSession) -> tuple[float | None, float | None]:
    """
    Вычислить взвешенный рейтинг филамента на основе рейтингов пресетов.
    
    Формула: Σ(preset.rating × preset.usage_count × preset.success_rate / 100) / Σ(preset.usage_count × preset.success_rate / 100)
    
    Возвращает: (avg_rating, success_rate)
    """
    # Получаем все активные пресеты этого филамента с рейтингами
    presets_result = await db.execute(
        select(Preset).where(
            Preset.filament_id == filament_id,
            Preset.active == True,
            Preset.rating.isnot(None),
        )
    )
    presets = presets_result.scalars().all()
    
    if not presets:
        return None, None
    
    # Вычисляем взвешенное среднее
    total_weighted_rating = 0.0
    total_weighted_success = 0.0
    total_weight = 0.0
    
    for preset in presets:
        if preset.rating is None or preset.success_rate is None:
            continue
        
        # Вес = usage_count × success_rate (чем больше использований и успешность, тем больше вес)
        weight = preset.usage_count * (preset.success_rate / 100.0)
        
        if weight > 0:
            total_weighted_rating += preset.rating * weight
            total_weighted_success += preset.success_rate * weight
            total_weight += weight
    
    if total_weight == 0:
        return None, None
    
    avg_rating = total_weighted_rating / total_weight
    avg_success_rate = total_weighted_success / total_weight
    
    return round(avg_rating, 2), round(avg_success_rate, 1)

