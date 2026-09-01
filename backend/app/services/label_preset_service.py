"""Concurrency-safe persistence for personal and company label layouts."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_LABEL_PRESET_CONFLICT, raise_error
from app.models.organization import Organization
from app.models.organization_label_preset import OrganizationLabelPreset
from app.models.user import User
from app.models.user_label_preset import UserLabelPreset
from app.schemas.label import LabelPresetResponse, LabelPresetSave

DEFAULT_LABEL_PRESET_NAME = "default"


def _response(preset: UserLabelPreset | OrganizationLabelPreset) -> LabelPresetResponse:
    return LabelPresetResponse(
        id=preset.id,
        name=preset.name,
        revision=preset.revision,
        settings=preset.settings,
        updated_at=preset.updated_at,
    )


async def get_default_label_preset(db: AsyncSession, *, user_id: int) -> LabelPresetResponse | None:
    preset = await db.scalar(
        select(UserLabelPreset).where(
            UserLabelPreset.user_id == user_id,
            UserLabelPreset.name == DEFAULT_LABEL_PRESET_NAME,
        )
    )
    return _response(preset) if preset else None


async def save_default_label_preset(
    db: AsyncSession, *, user_id: int, payload: LabelPresetSave
) -> LabelPresetResponse:
    # One account lock serializes the first create and later updates without
    # turning a future list of named presets into a global lock.
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    preset = await db.scalar(
        select(UserLabelPreset)
        .where(
            UserLabelPreset.user_id == user_id,
            UserLabelPreset.name == DEFAULT_LABEL_PRESET_NAME,
        )
        .with_for_update()
    )
    settings = payload.settings.model_dump(mode="json")

    if preset is None:
        if payload.revision is not None:
            raise_error(409, ERR_LABEL_PRESET_CONFLICT)
        preset = UserLabelPreset(
            user_id=user_id,
            name=DEFAULT_LABEL_PRESET_NAME,
            settings=settings,
            revision=1,
        )
        db.add(preset)
    else:
        # A retry after an uncertain response is idempotent when the intended
        # settings already won, even if its revision is now stale.
        if preset.settings == settings:
            response = _response(preset)
            await db.commit()
            return response
        if payload.revision != preset.revision:
            raise_error(409, ERR_LABEL_PRESET_CONFLICT)
        preset.settings = settings
        preset.revision += 1

    await db.flush()
    await db.refresh(preset)
    response = _response(preset)
    await db.commit()
    return response


async def get_organization_default_label_preset(
    db: AsyncSession,
    *,
    organization_id: int,
    brand_id: int,
) -> LabelPresetResponse | None:
    preset = await db.scalar(
        select(OrganizationLabelPreset).where(
            OrganizationLabelPreset.organization_id == organization_id,
            OrganizationLabelPreset.brand_id == brand_id,
            OrganizationLabelPreset.name == DEFAULT_LABEL_PRESET_NAME,
        )
    )
    return _response(preset) if preset else None


async def save_organization_default_label_preset(
    db: AsyncSession,
    *,
    organization_id: int,
    brand_id: int,
    actor_id: int,
    payload: LabelPresetSave,
) -> LabelPresetResponse:
    # The company lock serializes first creation and updates to this small
    # professional setting without relying on a user's mutable active pointers.
    await db.execute(
        select(Organization.id).where(Organization.id == organization_id).with_for_update()
    )
    preset = await db.scalar(
        select(OrganizationLabelPreset)
        .where(
            OrganizationLabelPreset.organization_id == organization_id,
            OrganizationLabelPreset.brand_id == brand_id,
            OrganizationLabelPreset.name == DEFAULT_LABEL_PRESET_NAME,
        )
        .with_for_update()
    )
    settings = payload.settings.model_dump(mode="json")

    if preset is None:
        if payload.revision is not None:
            raise_error(409, ERR_LABEL_PRESET_CONFLICT)
        preset = OrganizationLabelPreset(
            organization_id=organization_id,
            brand_id=brand_id,
            name=DEFAULT_LABEL_PRESET_NAME,
            settings=settings,
            revision=1,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        db.add(preset)
    else:
        if preset.settings == settings:
            response = _response(preset)
            await db.commit()
            return response
        if payload.revision != preset.revision:
            raise_error(409, ERR_LABEL_PRESET_CONFLICT)
        preset.settings = settings
        preset.revision += 1
        preset.updated_by_id = actor_id

    await db.flush()
    await db.refresh(preset)
    response = _response(preset)
    await db.commit()
    return response
