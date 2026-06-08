"""Preset service layer."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus


async def get_preset_by_id(preset_id: int, db: AsyncSession) -> Preset | None:
    """Получить пресет по ID."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    return result.scalar_one_or_none()


async def list_presets(
    db: AsyncSession,
    active_only: bool = True,
    filament_id: int | None = None,
    is_official: bool | None = None,
    approved_only: bool = True,
    limit: int | None = None,
    offset: int = 0,
) -> list[Preset]:
    """Получить список пресетов."""
    query = select(Preset)

    if active_only:
        query = query.where(Preset.active == True)

    if filament_id:
        query = query.where(Preset.filament_id == filament_id)

    if is_official is not None:
        query = query.where(Preset.is_official == is_official)

    if approved_only:
        query = query.where(
            or_(
                Preset.moderation_status == PresetModerationStatus.APPROVED,
                Preset.is_official == True
            )
        )

    query = query.order_by(
        Preset.is_official.desc(),
        Preset.rating.desc().nulls_last(),
        Preset.created_at.desc()
    )

    if limit:
        query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    return list(result.scalars().all())


async def check_filament_exists(filament_id: int, db: AsyncSession) -> bool:
    """Проверить существование материала."""
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()
    return filament is not None


async def count_presets_for_filament(filament_id: int, db: AsyncSession) -> int:
    """Подсчитать количество пресетов для материала."""
    query = select(func.count()).select_from(Preset).where(
        Preset.filament_id == filament_id,
        Preset.active == True,
        or_(
            Preset.moderation_status == PresetModerationStatus.APPROVED,
            Preset.is_official == True
        )
    )
    result = await db.execute(query)
    return result.scalar() or 0

