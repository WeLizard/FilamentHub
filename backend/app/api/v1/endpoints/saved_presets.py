"""Saved presets endpoints - избранные пресеты пользователя."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.preset import Preset
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.user_saved_preset import (
    UserSavedPresetCreate,
    UserSavedPresetListResponse,
    UserSavedPresetResponse,
)

router = APIRouter(prefix="/saved-presets", tags=["saved-presets"])


@router.get("/", response_model=UserSavedPresetListResponse)
async def list_saved_presets(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserSavedPresetListResponse:
    """Получить список сохранённых пресетов текущего пользователя."""
    # Получаем все сохранённые пресеты пользователя
    result = await db.execute(
        select(UserSavedPreset).where(UserSavedPreset.user_id == current_user.id)
    )
    saved_presets = result.scalars().all()

    items = [UserSavedPresetResponse.model_validate(sp) for sp in saved_presets]

    return UserSavedPresetListResponse(items=items, total=len(items))


@router.post("/", response_model=UserSavedPresetResponse, status_code=201)
async def save_preset(
    data: UserSavedPresetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserSavedPresetResponse:
    """Сохранить пресет в профиль пользователя."""
    # Проверяем, существует ли пресет
    preset_result = await db.execute(select(Preset).where(Preset.id == data.preset_id))
    preset = preset_result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    if not preset.active:
        raise HTTPException(status_code=400, detail="Cannot save inactive preset")

    # Проверяем, не сохранён ли уже этот пресет
    existing_result = await db.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == current_user.id,
            UserSavedPreset.preset_id == data.preset_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        # Если уже сохранён, просто возвращаем существующую запись
        return UserSavedPresetResponse.model_validate(existing)

    # Создаём новую запись
    saved_preset = UserSavedPreset(
        user_id=current_user.id,
        preset_id=data.preset_id,
    )
    db.add(saved_preset)
    await db.commit()
    await db.refresh(saved_preset)

    return UserSavedPresetResponse.model_validate(saved_preset)


@router.delete("/{preset_id}", status_code=204)
async def unsave_preset(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Убрать пресет из сохранённых."""
    # Находим сохранённый пресет
    result = await db.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == current_user.id,
            UserSavedPreset.preset_id == preset_id,
        )
    )
    saved_preset = result.scalar_one_or_none()

    if not saved_preset:
        raise HTTPException(status_code=404, detail="Saved preset not found")

    # Удаляем
    await db.delete(saved_preset)
    await db.commit()

