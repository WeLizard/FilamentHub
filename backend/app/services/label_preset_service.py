"""Concurrency-safe persistence for private label-layout presets."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_LABEL_PRESET_CONFLICT, raise_error
from app.models.user import User
from app.models.user_label_preset import UserLabelPreset
from app.schemas.label import LabelPresetResponse, LabelPresetSave

DEFAULT_LABEL_PRESET_NAME = "default"


def _response(preset: UserLabelPreset) -> LabelPresetResponse:
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
