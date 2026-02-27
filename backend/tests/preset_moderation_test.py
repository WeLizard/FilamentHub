"""Tests for preset moderation service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.services.preset_moderation import moderate_preset


@pytest.mark.asyncio
async def test_moderation_can_return_pending_when_manual_review_enabled(
    db_session: AsyncSession,
):
    """Soft-risk signals should produce PENDING when manual review is enabled."""
    brand = Brand(name="Moderation Brand", slug="moderation-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name="Moderation PLA",
        slug="moderation-pla",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    existing = Preset(
        filament_id=filament.id,
        user_id=1,
        name="Duplicate Risk Preset",
        is_official=False,
        extruder_temp=240.0,
        bed_temp=60.0,
        print_speed=50.0,
        flow_rate=100.0,
        fan_speed=80,
        retraction_length=5.0,
        retraction_speed=45.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add(existing)
    await db_session.commit()

    candidate = Preset(
        filament_id=filament.id,
        user_id=1,
        name="Duplicate Risk Preset",
        is_official=False,
        extruder_temp=260.0,  # PLA soft_max=250 => soft warning
        bed_temp=60.0,
        print_speed=50.0,
        flow_rate=100.0,
        fan_speed=80,
        retraction_length=5.0,
        retraction_speed=45.0,
        active=True,
    )

    status, reason = await moderate_preset(
        candidate,
        filament,
        db_session,
        is_official=False,
        allow_manual_review=True,
    )

    assert status == PresetModerationStatus.PENDING
    assert isinstance(reason, dict)
    assert reason.get("code") == "ERR_PRESET_REQUIRES_MANUAL_REVIEW"


@pytest.mark.asyncio
async def test_moderation_auto_approves_when_manual_review_disabled(
    db_session: AsyncSession,
):
    """The same soft-risk profile should be approved when manual review is disabled."""
    brand = Brand(name="Auto Brand", slug="auto-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name="Auto PLA",
        slug="auto-pla",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    existing = Preset(
        filament_id=filament.id,
        user_id=2,
        name="Auto Duplicate Preset",
        is_official=False,
        extruder_temp=240.0,
        bed_temp=60.0,
        print_speed=50.0,
        flow_rate=100.0,
        fan_speed=80,
        retraction_length=5.0,
        retraction_speed=45.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add(existing)
    await db_session.commit()

    candidate = Preset(
        filament_id=filament.id,
        user_id=2,
        name="Auto Duplicate Preset",
        is_official=False,
        extruder_temp=260.0,
        bed_temp=60.0,
        print_speed=50.0,
        flow_rate=100.0,
        fan_speed=80,
        retraction_length=5.0,
        retraction_speed=45.0,
        active=True,
    )

    status, reason = await moderate_preset(
        candidate,
        filament,
        db_session,
        is_official=False,
        allow_manual_review=False,
    )

    assert status == PresetModerationStatus.APPROVED
    assert reason is None


@pytest.mark.asyncio
async def test_moderation_still_rejects_invalid_settings_with_manual_review_disabled(
    db_session: AsyncSession,
):
    """Hard validation must reject presets even when manual review is disabled."""
    brand = Brand(name="Reject Brand", slug="reject-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name="Reject PLA",
        slug="reject-pla",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    candidate = Preset(
        filament_id=filament.id,
        user_id=3,
        name="Invalid Preset",
        is_official=False,
        extruder_temp=600.0,  # hard max violation
        bed_temp=60.0,
        print_speed=50.0,
        active=True,
    )

    status, reason = await moderate_preset(
        candidate,
        filament,
        db_session,
        is_official=False,
        allow_manual_review=False,
    )

    assert status == PresetModerationStatus.REJECTED
    assert isinstance(reason, dict)
    assert reason.get("code") == "ERR_EXTRUDER_TEMP_TOO_HIGH"
