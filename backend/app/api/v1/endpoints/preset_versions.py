"""Preset version history endpoints.

Mounted under ``/presets/{preset_id}/versions``. Read access follows preset
visibility (owner/admin always, others only if the preset is public);
labelling and restore require owner/admin.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_current_active_user_optional
from app.core.errors import (
    ERR_PRESET_NOT_FOUND,
    ERR_PRESET_VERSION_FORBIDDEN,
    ERR_PRESET_VERSION_NOT_FOUND,
    raise_error,
)
from app.db.session import get_db
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_version import PresetVersion
from app.models.user import User
from app.schemas.preset_version import (
    PresetVersionDetail,
    PresetVersionDiffResponse,
    PresetVersionLabelUpdate,
    PresetVersionListItem,
    PresetVersionListResponse,
    PresetVersionRestoreResponse,
)
from app.services import preset_version_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/presets", tags=["preset-versions"])


def _is_preset_public(preset: Preset) -> bool:
    """A preset is publicly viewable if official or approved."""
    return bool(preset.is_official) or preset.moderation_status == PresetModerationStatus.APPROVED


async def _load_preset_for_view(
    db: AsyncSession, preset_id: int, user: User | None
) -> Preset:
    """Load a preset, enforcing read visibility. Raises 404/403."""
    preset = await db.get(Preset, preset_id)
    if preset is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_NOT_FOUND, params={"preset_id": preset_id})

    if _is_preset_public(preset):
        return preset
    if user is not None and (preset.user_id == user.id or user.is_admin):
        return preset
    raise_error(status.HTTP_403_FORBIDDEN, ERR_PRESET_VERSION_FORBIDDEN, params={"preset_id": preset_id})


async def _load_preset_for_mutate(
    db: AsyncSession, preset_id: int, user: User
) -> Preset:
    """Load a preset, enforcing owner/admin. Raises 404/403."""
    preset = await db.get(Preset, preset_id)
    if preset is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_NOT_FOUND, params={"preset_id": preset_id})
    if preset.user_id != user.id and not user.is_admin:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_PRESET_VERSION_FORBIDDEN, params={"preset_id": preset_id})
    return preset


def _to_list_item(v: PresetVersion) -> PresetVersionListItem:
    """Build a list item, flattening the author relationship."""
    author = None
    if v.created_by is not None:
        author = {"id": v.created_by.id, "username": getattr(v.created_by, "username", None)}
    return PresetVersionListItem(
        id=v.id,
        version_number=v.version_number,
        label=v.label,
        label_description=v.label_description,
        change_source=v.change_source,
        restored_from_version_id=v.restored_from_version_id,
        squash_count=v.squash_count,
        created_at=v.created_at,
        updated_at=v.updated_at,
        created_by=author,
    )


@router.get("/{preset_id}/versions", response_model=PresetVersionListResponse)
async def list_preset_versions(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_current_active_user_optional)],
    labeled_only: bool = Query(False),
    limit: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> PresetVersionListResponse:
    """List versions of a preset, newest first."""
    await _load_preset_for_view(db, preset_id, current_user)

    # Re-query with author eager-loaded for display.
    base = (
        select(PresetVersion)
        .where(PresetVersion.preset_id == preset_id)
        .options(selectinload(PresetVersion.created_by))
    )
    if labeled_only:
        base = base.where(PresetVersion.label != "")

    from sqlalchemy import func as sa_func

    total = (await db.execute(select(sa_func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(PresetVersion.version_number.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return PresetVersionListResponse(items=[_to_list_item(v) for v in rows], total=total)


@router.get("/{preset_id}/versions/{version_id}", response_model=PresetVersionDetail)
async def get_preset_version(
    preset_id: int,
    version_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_current_active_user_optional)],
) -> PresetVersionDetail:
    """Fetch a single version with its full snapshot."""
    await _load_preset_for_view(db, preset_id, current_user)

    result = await db.execute(
        select(PresetVersion)
        .where(PresetVersion.id == version_id, PresetVersion.preset_id == preset_id)
        .options(selectinload(PresetVersion.created_by))
    )
    v = result.scalar_one_or_none()
    if v is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_VERSION_NOT_FOUND, params={"version_id": version_id})

    item = _to_list_item(v)
    return PresetVersionDetail(
        **item.model_dump(),
        snapshot_orcaslicer_settings=v.snapshot_orcaslicer_settings,
        snapshot_structured=v.snapshot_structured,
    )


@router.get(
    "/{preset_id}/versions/{a_id}/diff/{b_id}",
    response_model=PresetVersionDiffResponse,
)
async def diff_preset_versions(
    preset_id: int,
    a_id: int,
    b_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_current_active_user_optional)],
) -> PresetVersionDiffResponse:
    """Human-readable diff from version a_id to version b_id."""
    await _load_preset_for_view(db, preset_id, current_user)

    version_a = await preset_version_service.get_version(db, preset_id, a_id)
    version_b = await preset_version_service.get_version(db, preset_id, b_id)
    if version_a is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_VERSION_NOT_FOUND, params={"version_id": a_id})
    if version_b is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_VERSION_NOT_FOUND, params={"version_id": b_id})

    diff = preset_version_service.compute_diff(version_a, version_b)
    return PresetVersionDiffResponse(**diff)


@router.patch("/{preset_id}/versions/{version_id}", response_model=PresetVersionListItem)
async def update_preset_version_label(
    preset_id: int,
    version_id: int,
    payload: PresetVersionLabelUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetVersionListItem:
    """Set or clear a version's label (owner/admin)."""
    await _load_preset_for_mutate(db, preset_id, current_user)

    if payload.label:
        from app.services.preset_moderation import validate_text_field

        is_valid, error_msg = await validate_text_field(payload.label, db, "label")
        if not is_valid:
            from fastapi import HTTPException

            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    version = await preset_version_service.get_version(db, preset_id, version_id)
    if version is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_VERSION_NOT_FOUND, params={"version_id": version_id})

    await preset_version_service.set_label(db, version, payload.label, payload.label_description)
    await db.commit()
    await db.refresh(version, attribute_names=["created_by"])
    return _to_list_item(version)


@router.post(
    "/{preset_id}/versions/{version_id}/restore",
    response_model=PresetVersionRestoreResponse,
)
async def restore_preset_version(
    preset_id: int,
    version_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetVersionRestoreResponse:
    """Restore a previous version (owner/admin). Creates a new version."""
    preset = await _load_preset_for_mutate(db, preset_id, current_user)

    version = await preset_version_service.get_version(db, preset_id, version_id)
    if version is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_VERSION_NOT_FOUND, params={"version_id": version_id})

    new_version = await preset_version_service.restore_version(
        db, preset, version, user_id=current_user.id
    )
    await db.commit()

    return PresetVersionRestoreResponse(
        restored_into_version_id=new_version.id,
        restored_into_version_number=new_version.version_number,
        restored_from_version_id=version_id,
    )
