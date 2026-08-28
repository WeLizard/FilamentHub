"""Saved presets endpoints - избранные пресеты пользователя."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_PRESET_INACTIVE,
    ERR_PRESET_NOT_FOUND,
    ERR_PRESET_VERSION_FORBIDDEN,
    ERR_PRESET_VERSION_NOT_FOUND,
    ERR_PRINTER_PROFILE_NOT_FOUND,
    ERR_SAVED_PRESET_NOT_FOUND,
    raise_error,
)
from app.db.session import get_db
from app.models.preset import PUBLIC_PRESET_STATUSES, Preset
from app.models.preset_version import PresetVersion
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset, UserSavedPresetTarget
from app.schemas.user_saved_preset import (
    UserSavedPresetCreate,
    UserSavedPresetListResponse,
    UserSavedPresetResponse,
    UserSavedPresetScopeUpdate,
    UserSavedPresetVersionAction,
)
from app.services import preset_version_service

router = APIRouter(prefix="/saved-presets", tags=["saved-presets"])


async def _saved_preset_responses(
    db: AsyncSession, saved_presets: list[UserSavedPreset]
) -> list[UserSavedPresetResponse]:
    """Serialize version state in one query instead of one query per card."""
    preset_ids = {item.preset_id for item in saved_presets}
    versions: list[tuple[int, int, int]] = []
    if preset_ids:
        versions = [
            (version_id, preset_id, version_number)
            for version_id, preset_id, version_number in (
                await db.execute(
                    select(
                        PresetVersion.id,
                        PresetVersion.preset_id,
                        PresetVersion.version_number,
                    )
                    .where(PresetVersion.preset_id.in_(preset_ids))
                    .order_by(
                        PresetVersion.preset_id.asc(),
                        PresetVersion.version_number.asc(),
                    )
                )
            ).all()
        ]
    by_id = {
        version_id: (version_id, preset_id, version_number)
        for version_id, preset_id, version_number in versions
    }
    latest_by_preset: dict[int, tuple[int, int, int]] = {}
    for version_id, preset_id, version_number in versions:
        latest_by_preset[preset_id] = (version_id, preset_id, version_number)

    responses: list[UserSavedPresetResponse] = []
    for item in saved_presets:
        latest = latest_by_preset.get(item.preset_id)
        selected = by_id.get(item.selected_version_id)
        if selected is None or selected[1] != item.preset_id:
            selected = latest
        update_available = bool(
            latest is not None
            and selected is not None
            and latest[0] != selected[0]
        )
        responses.append(
            UserSavedPresetResponse(
                id=item.id,
                user_id=item.user_id,
                preset_id=item.preset_id,
                saved_at=item.saved_at,
                sync=item.sync,
                scope=item.scope,
                target_printer_profile_ids=item.target_printer_profile_ids,
                selected_version_id=selected[0] if selected else None,
                selected_version_number=selected[2] if selected else None,
                latest_version_id=latest[0] if latest else None,
                latest_version_number=latest[2] if latest else None,
                update_available=update_available,
                update_unseen=bool(
                    update_available
                    and latest is not None
                    and item.seen_version_id != latest[0]
                ),
            )
        )
    return responses


async def _saved_preset_response(
    db: AsyncSession, saved_preset: UserSavedPreset
) -> UserSavedPresetResponse:
    return (await _saved_preset_responses(db, [saved_preset]))[0]


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

    items = await _saved_preset_responses(db, list(saved_presets))

    return UserSavedPresetListResponse(items=items, total=len(items))


@router.post("/", response_model=UserSavedPresetResponse, status_code=201)
async def save_preset(
    data: UserSavedPresetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserSavedPresetResponse:
    """Сохранить пресет в профиль пользователя."""
    # Keep scalar identity across a possible IntegrityError rollback. SQLAlchemy
    # expires ORM instances on rollback, and a concurrent duplicate save must
    # still be able to query the row committed by the winning request.
    user_id = current_user.id
    # Проверяем, существует ли пресет
    preset_result = await db.execute(select(Preset).where(Preset.id == data.preset_id))
    preset = preset_result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    if not preset.active:
        raise_error(400, ERR_PRESET_INACTIVE)

    from app.services.preset_access import can_manage_preset

    filament = None
    if preset.filament_id is not None:
        from app.models.filament import Filament

        filament = await db.get(Filament, preset.filament_id)
    can_manage = await can_manage_preset(db, current_user, preset, filament)
    is_catalog_public = bool(
        preset.is_official or preset.moderation_status in PUBLIC_PRESET_STATUSES
    )
    if not can_manage and not is_catalog_public:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    # Проверяем, не сохранён ли уже этот пресет
    existing_result = await db.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == user_id,
            UserSavedPreset.preset_id == data.preset_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    latest_version = await preset_version_service.get_latest_version(db, preset.id)
    # Some presets created by legacy/import/enrichment paths predate mandatory
    # version recording. Repair them at the installation boundary so a saved
    # preset is always pinned to real immutable content.
    if latest_version is None or (
        is_catalog_public
        and not preset_version_service.is_public_version(latest_version, preset)
    ):
        if is_catalog_public:
            from app.services.preset_publication import apply_managed_orca_identity

            apply_managed_orca_identity(preset)
        from app.models.preset_version import PresetVersionSource

        latest_version = await preset_version_service.record_version(
            db,
            preset,
            source=PresetVersionSource.MIGRATION,
        )
        if latest_version is None:
            latest_version = await preset_version_service.get_latest_version(
                db, preset.id
            )

    if latest_version is not None:
        # NULL never means "keep an older version"; it exists only on legacy
        # rows that predate selection. Repair every such installation when the
        # first usable version appears, without touching explicit selections.
        await db.execute(
            update(UserSavedPreset)
            .where(
                UserSavedPreset.preset_id == preset.id,
                UserSavedPreset.selected_version_id.is_(None),
            )
            .values(
                selected_version_id=latest_version.id,
                seen_version_id=latest_version.id,
            )
        )

    if existing:
        # Repair only legacy NULL selection. A real older selection is the
        # user's decision and must never be advanced implicitly.
        if existing.selected_version_id is None and latest_version is not None:
            existing.selected_version_id = latest_version.id
            existing.seen_version_id = latest_version.id
            await db.commit()
            await db.refresh(existing)
        return await _saved_preset_response(db, existing)

    # Создаём новую запись
    saved_preset = UserSavedPreset(
        user_id=user_id,
        preset_id=data.preset_id,
        sync=data.sync,
        selected_version_id=latest_version.id if latest_version else None,
        seen_version_id=latest_version.id if latest_version else None,
    )
    db.add(saved_preset)
    preset.usage_count += 1
    if preset.user_id is not None and preset.user_id != user_id:
        from app.services.preset_funnel_metrics import record_preset_funnel_event

        record_preset_funnel_event(db, "installed_or_used")
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent save of the same preset: the unique (user_id, preset_id)
        # index fired. Return the row the other request created.
        await db.rollback()
        existing_result = await db.execute(
            select(UserSavedPreset).where(
                UserSavedPreset.user_id == user_id,
                UserSavedPreset.preset_id == data.preset_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is None:
            raise
        return await _saved_preset_response(db, existing)
    await db.refresh(saved_preset)

    return await _saved_preset_response(db, saved_preset)


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

    return await _saved_preset_response(db, saved_preset)


@router.patch("/{preset_id}/scope", response_model=UserSavedPresetResponse)
async def update_saved_preset_scope(
    preset_id: int,
    data: UserSavedPresetScopeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserSavedPresetResponse:
    """Задать набор целевых принтер-профилей библиотечного пресета.

    Scope выводится из размера набора: пусто → unscoped, один → targeted,
    несколько → compatible. Принимаются только собственные активные профили
    пользователя — чужой machine profile в экспорте раскрыл бы структуру
    чужой библиотеки.
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

    target_ids = list(dict.fromkeys(data.target_printer_profile_ids))
    if target_ids:
        profile_result = await db.execute(
            select(PrinterProfile.id).where(
                PrinterProfile.id.in_(target_ids),
                PrinterProfile.owner_user_id == current_user.id,
                PrinterProfile.active.is_(True),
            )
        )
        valid_ids = set(profile_result.scalars().all())
        if valid_ids != set(target_ids):
            raise_error(404, ERR_PRINTER_PROFILE_NOT_FOUND)

    # Diff the set instead of reassigning the whole collection: reassigning
    # would orphan-delete and re-insert unchanged rows in the same flush, and
    # Postgres fires ix_usp_targets_saved_profile_unique when the INSERT of an
    # unchanged (saved_preset, profile) pair races its DELETE.
    desired = set(target_ids)
    existing = {target.printer_profile_id: target for target in saved_preset.targets}
    for profile_id, target in existing.items():
        if profile_id not in desired:
            saved_preset.targets.remove(target)
    for profile_id in target_ids:
        if profile_id not in existing:
            saved_preset.targets.append(
                UserSavedPresetTarget(printer_profile_id=profile_id)
            )
    if not target_ids:
        saved_preset.scope = "unscoped"
    elif len(target_ids) == 1:
        saved_preset.scope = "targeted"
    else:
        saved_preset.scope = "compatible"

    await db.commit()
    await db.refresh(saved_preset)
    return await _saved_preset_response(db, saved_preset)


@router.patch("/{preset_id}/version", response_model=UserSavedPresetResponse)
async def update_saved_preset_version(
    preset_id: int,
    data: UserSavedPresetVersionAction,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserSavedPresetResponse:
    """Select a version, or keep the selected one and acknowledge an update."""
    result = await db.execute(
        select(UserSavedPreset)
        .options(selectinload(UserSavedPreset.preset))
        .where(
            UserSavedPreset.user_id == current_user.id,
            UserSavedPreset.preset_id == preset_id,
        )
    )
    saved_preset = result.scalar_one_or_none()
    if saved_preset is None:
        raise_error(404, ERR_SAVED_PRESET_NOT_FOUND)

    version = await preset_version_service.get_version(db, preset_id, data.version_id)
    if version is None:
        raise_error(
            404,
            ERR_PRESET_VERSION_NOT_FOUND,
            params={"version_id": data.version_id},
        )

    preset = saved_preset.preset
    from app.services.preset_access import can_manage_preset

    filament = None
    if preset.filament_id is not None:
        from app.models.filament import Filament

        filament = await db.get(Filament, preset.filament_id)
    can_manage = await can_manage_preset(db, current_user, preset, filament)
    if not can_manage and not preset_version_service.is_public_version(version, preset):
        raise_error(403, ERR_PRESET_VERSION_FORBIDDEN)

    latest = await preset_version_service.get_latest_version(db, preset_id)
    if data.action == "select":
        saved_preset.selected_version_id = version.id
        # Selecting any version is also an explicit decision about everything
        # currently published, even when the selected version is older.
        saved_preset.seen_version_id = latest.id if latest else version.id
    else:
        # keep_current acknowledges only the named current latest version. This
        # prevents a stale UI request from hiding a newer release that appeared
        # concurrently.
        if latest is None or version.id != latest.id:
            raise_error(
                404,
                ERR_PRESET_VERSION_NOT_FOUND,
                params={"version_id": data.version_id},
            )
        saved_preset.seen_version_id = version.id

    await db.commit()
    await db.refresh(saved_preset)
    return await _saved_preset_response(db, saved_preset)
