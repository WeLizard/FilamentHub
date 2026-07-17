"""Saved presets endpoints - избранные пресеты пользователя."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_PRESET_INACTIVE,
    ERR_PRESET_NOT_FOUND,
    ERR_PRINTER_PROFILE_NOT_FOUND,
    ERR_SAVED_PRESET_NOT_FOUND,
    raise_error,
)
from app.db.session import get_db
from app.models.preset import Preset
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.user_saved_preset import (
    UserSavedPresetCreate,
    UserSavedPresetListResponse,
    UserSavedPresetResponse,
    UserSavedPresetScopeUpdate,
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
        raise_error(404, ERR_PRESET_NOT_FOUND)

    if not preset.active:
        raise_error(400, ERR_PRESET_INACTIVE)

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
        sync=True,  # По умолчанию синхронизация включена
    )
    db.add(saved_preset)
    preset.usage_count += 1
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent save of the same preset: the unique (user_id, preset_id)
        # index fired. Return the row the other request created.
        await db.rollback()
        existing_result = await db.execute(
            select(UserSavedPreset).where(
                UserSavedPreset.user_id == current_user.id,
                UserSavedPreset.preset_id == data.preset_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is None:
            raise
        return UserSavedPresetResponse.model_validate(existing)
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
        raise_error(404, ERR_SAVED_PRESET_NOT_FOUND)

    # Удаляем
    await db.delete(saved_preset)
    await db.commit()


@router.patch("/{preset_id}/sync", response_model=UserSavedPresetResponse)
async def toggle_saved_preset_sync(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    sync: bool = Query(..., description="Включить или выключить синхронизацию"),
) -> UserSavedPresetResponse:
    """Переключить синхронизацию сохраненного пресета."""
    # Находим сохранённый пресет
    result = await db.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == current_user.id,
            UserSavedPreset.preset_id == preset_id,
        )
    )
    saved_preset = result.scalar_one_or_none()

    if not saved_preset:
        raise_error(404, ERR_SAVED_PRESET_NOT_FOUND)

    # Обновляем sync
    saved_preset.sync = sync
    await db.commit()
    await db.refresh(saved_preset)

    return UserSavedPresetResponse.model_validate(saved_preset)


@router.patch("/{preset_id}/scope", response_model=UserSavedPresetResponse)
async def update_saved_preset_scope(
    preset_id: int,
    data: UserSavedPresetScopeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserSavedPresetResponse:
    """Задать scope библиотеки: универсальный или под конкретный принтер-профиль.

    targeted принимает только собственный профиль пользователя — targeting a
    foreign machine profile would leak someone else's library structure into
    the export.
    """
    result = await db.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == current_user.id,
            UserSavedPreset.preset_id == preset_id,
        )
    )
    saved_preset = result.scalar_one_or_none()
    if not saved_preset:
        raise_error(404, ERR_SAVED_PRESET_NOT_FOUND)

    if data.scope == "targeted":
        if data.target_printer_profile_id is None:
            raise_error(404, ERR_PRINTER_PROFILE_NOT_FOUND)
        profile_result = await db.execute(
            select(PrinterProfile).where(
                PrinterProfile.id == data.target_printer_profile_id,
                PrinterProfile.owner_user_id == current_user.id,
                PrinterProfile.active.is_(True),
            )
        )
        if profile_result.scalar_one_or_none() is None:
            raise_error(404, ERR_PRINTER_PROFILE_NOT_FOUND)
        saved_preset.scope = "targeted"
        saved_preset.target_printer_profile_id = data.target_printer_profile_id
    else:
        saved_preset.scope = "unscoped"
        saved_preset.target_printer_profile_id = None

    await db.commit()
    await db.refresh(saved_preset)
    return UserSavedPresetResponse.model_validate(saved_preset)

