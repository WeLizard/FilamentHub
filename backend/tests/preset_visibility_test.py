"""Weighted-preset safety: AUTO_GENERATED presets stay publicly visible but are
not stamped as human-APPROVED (Ф8)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import PUBLIC_PRESET_STATUSES, Preset, PresetModerationStatus
from app.services.preset_service import count_presets_for_filament


def test_public_statuses_include_approved_and_generated():
    assert PresetModerationStatus.APPROVED in PUBLIC_PRESET_STATUSES
    assert PresetModerationStatus.AUTO_GENERATED in PUBLIC_PRESET_STATUSES
    # Not-yet-reviewed and rejected presets are never public.
    assert PresetModerationStatus.PENDING not in PUBLIC_PRESET_STATUSES
    assert PresetModerationStatus.REJECTED not in PUBLIC_PRESET_STATUSES


@pytest.mark.asyncio
async def test_auto_generated_preset_is_publicly_visible(db_session: AsyncSession):
    brand = Brand(name="Vis Brand", slug="vis-brand")
    db_session.add(brand)
    await db_session.flush()

    filament = Filament(brand_id=brand.id, name="Vis PLA", slug="vis-pla", material_type="PLA")
    db_session.add(filament)
    await db_session.flush()

    db_session.add(
        Preset(
            name="Vis PLA Gen",
            filament_id=filament.id,
            extruder_temp=210,
            bed_temp=60,
            is_weighted=True,
            active=True,
            moderation_status=PresetModerationStatus.AUTO_GENERATED,
        )
    )
    db_session.add(
        Preset(
            name="Vis PLA Rejected",
            filament_id=filament.id,
            extruder_temp=210,
            bed_temp=60,
            active=True,
            moderation_status=PresetModerationStatus.REJECTED,
        )
    )
    await db_session.commit()

    # Only the auto-generated preset counts as publicly visible; rejected is excluded.
    assert await count_presets_for_filament(filament.id, db_session) == 1
