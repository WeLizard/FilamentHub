"""Costly achievement boundaries: no self-credit, no duplicate award."""

from sqlalchemy import func, select

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.models.user_saved_preset import UserSavedPreset
from app.services.achievement_service import (
    FIRST_PROFILE,
    PRESET_USED_BY_ANOTHER,
    achievement_overview,
)


async def test_usefulness_achievements_ignore_self_and_are_idempotent(
    db_session,
    auth_user,
):
    other = User(
        email="achievement-reader@example.com",
        username="achievement-reader",
        active=True,
        email_verified=True,
    )
    brand = Brand(name="Achievement Brand", slug="achievement-brand", active=True)
    db_session.add_all([other, brand])
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Useful PLA",
        slug="useful-pla",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()
    preset = Preset(
        filament_id=filament.id,
        user_id=auth_user.id,
        name="Useful PLA profile",
        extruder_temp=210,
        bed_temp=60,
        active=True,
        is_official=False,
        is_weighted=False,
        moderation_status=PresetModerationStatus.APPROVED,
    )
    db_session.add(preset)
    await db_session.flush()
    db_session.add_all(
        [
            UserSavedPreset(user_id=auth_user.id, preset_id=preset.id),
            PresetUsageEvent(
                user_id=auth_user.id,
                preset_id=preset.id,
                event_type=PresetUsageEventType.printer_report,
            ),
            PresetUsageEvent(
                user_id=other.id,
                preset_id=preset.id,
                event_type=PresetUsageEventType.print_estimate,
            ),
        ]
    )
    await db_session.commit()

    self_only = await achievement_overview(db_session, user_id=auth_user.id)
    assert {item.code for item in self_only.achievements} == {FIRST_PROFILE}
    assert self_only.saved_by_other_users == 0
    assert self_only.confirmed_uses_by_other_users == 0

    db_session.add(UserSavedPreset(user_id=other.id, preset_id=preset.id))
    await db_session.commit()

    saved_only = await achievement_overview(db_session, user_id=auth_user.id)
    assert {item.code for item in saved_only.achievements} == {FIRST_PROFILE}
    assert saved_only.saved_by_other_users == 1
    assert saved_only.confirmed_uses_by_other_users == 0

    db_session.add(
        PresetUsageEvent(
            user_id=other.id,
            preset_id=preset.id,
            event_type=PresetUsageEventType.printer_report,
        )
    )
    await db_session.commit()

    useful = await achievement_overview(db_session, user_id=auth_user.id)
    repeated = await achievement_overview(db_session, user_id=auth_user.id)
    expected = {FIRST_PROFILE, PRESET_USED_BY_ANOTHER}
    assert {item.code for item in useful.achievements} == expected
    assert {item.code for item in repeated.achievements} == expected
    assert useful.saved_by_other_users == 1
    assert useful.confirmed_uses_by_other_users == 1
    assert await db_session.scalar(select(func.count(UserAchievement.id))) == 2
