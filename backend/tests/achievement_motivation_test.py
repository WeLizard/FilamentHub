"""Costly achievement boundaries: no self-credit, no duplicate award."""

from sqlalchemy import func, select

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.material_system import MaterialSystem
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.wiki_category import WikiCategory
from app.models.wiki_space import WikiSpace
from app.services.achievement_service import (
    FIRST_HUNDRED,
    FIRST_PROFILE,
    FIRST_WIKI_ARTICLE,
    HAPPY_HARE_CONNECTED,
    PRESET_PUBLISHER_5,
    PRESET_USED_BY_ANOTHER,
    PRESETS_USED_BY_10,
    SPOOL_COLLECTOR_20,
    SPOOL_COLLECTOR_100,
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
    assert {item.code for item in self_only.achievements} == {
        FIRST_HUNDRED,
        FIRST_PROFILE,
    }
    assert self_only.saved_by_other_users == 0
    assert self_only.confirmed_uses_by_other_users == 0

    db_session.add(UserSavedPreset(user_id=other.id, preset_id=preset.id))
    await db_session.commit()

    saved_only = await achievement_overview(db_session, user_id=auth_user.id)
    assert {item.code for item in saved_only.achievements} == {
        FIRST_HUNDRED,
        FIRST_PROFILE,
    }
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
    expected = {FIRST_HUNDRED, FIRST_PROFILE, PRESET_USED_BY_ANOTHER}
    assert {item.code for item in useful.achievements} == expected
    assert {item.code for item in repeated.achievements} == expected
    assert useful.saved_by_other_users == 1
    assert useful.confirmed_uses_by_other_users == 1
    assert await db_session.scalar(select(func.count(UserAchievement.id))) == 3


async def test_retroactive_registry_uses_durable_thresholds_and_hides_secret_progress(
    db_session,
    auth_user,
):
    brand = Brand(name="Achievement MVP", slug="achievement-mvp", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Achievement PLA",
        slug="achievement-pla",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()

    presets = [
        Preset(
            filament_id=filament.id,
            user_id=auth_user.id,
            name=f"Useful profile {index}",
            extruder_temp=205 + index,
            bed_temp=60,
            active=True,
            is_official=False,
            is_weighted=False,
            moderation_status=PresetModerationStatus.APPROVED,
        )
        for index in range(5)
    ]
    readers = [
        User(
            email=f"achievement-reader-{index}@example.com",
            username=f"achievement-reader-{index}",
            active=True,
            email_verified=True,
        )
        for index in range(10)
    ]
    db_session.add_all([*presets, *readers])
    await db_session.flush()
    db_session.add_all(
        [
            PresetUsageEvent(
                user_id=reader.id,
                preset_id=presets[0].id,
                event_type=PresetUsageEventType.printer_report,
            )
            for reader in readers
        ]
    )
    db_session.add_all(
        [
            UserSpool(
                user_id=auth_user.id,
                filament_id=filament.id,
                initial_weight_g=1000,
            )
            for _ in range(100)
        ]
    )
    printer = UserPrinterDevice(user_id=auth_user.id, name="Achievement Voron")
    db_session.add(printer)
    await db_session.flush()
    db_session.add(
        MaterialSystem(
            user_id=auth_user.id,
            physical_printer_id=printer.id,
            name="Happy Hare",
            kind="mmu",
            provider="happy_hare",
            active=True,
        )
    )
    category = WikiCategory(
        name="Achievement Wiki",
        slug="achievement-wiki",
        description="Achievement articles",
    )
    space = WikiSpace(
        key="achievement-community",
        allows_community_authors=True,
    )
    db_session.add_all([category, space])
    await db_session.flush()
    db_session.add(
        WikiArticle(
            category_id=category.id,
            space_id=space.id,
            created_by_id=auth_user.id,
            title="First useful article",
            slug="first-useful-article",
            content_key="first-useful-article",
            summary="A useful article",
            content="Useful content",
            status=WikiArticleStatus.PUBLISHED,
            published=True,
        )
    )
    await db_session.commit()

    overview = await achievement_overview(db_session, user_id=auth_user.id)
    expected = {
        FIRST_HUNDRED,
        FIRST_PROFILE,
        PRESET_PUBLISHER_5,
        PRESET_USED_BY_ANOTHER,
        PRESETS_USED_BY_10,
        SPOOL_COLLECTOR_20,
        SPOOL_COLLECTOR_100,
        HAPPY_HARE_CONNECTED,
        FIRST_WIKI_ARTICLE,
    }
    assert {item.code for item in overview.achievements} == expected
    assert set(overview.newly_earned) == expected
    assert [item.code for item in overview.next_achievements] == ["first_catalog_contribution"]
    assert overview.contributor_roles == [
        "preset_author",
        "hardware_integrator",
        "wiki_contributor",
        "collector",
    ]
    assert overview.confirmed_uses_by_other_users == 10

    repeated = await achievement_overview(db_session, user_id=auth_user.id)
    assert repeated.newly_earned == []
    assert await db_session.scalar(select(func.count(UserAchievement.id))) == len(expected)


async def test_achievement_get_is_read_only_and_evaluate_reports_only_new_awards(
    auth_client,
    db_session,
):
    read_only = await auth_client.get("/api/v1/achievements/me")
    assert read_only.status_code == 200
    assert read_only.json()["achievements"] == []
    assert await db_session.scalar(select(func.count(UserAchievement.id))) == 0

    evaluated = await auth_client.post("/api/v1/achievements/me/evaluate")
    assert evaluated.status_code == 200
    assert evaluated.json()["newly_earned"] == [FIRST_HUNDRED]

    repeated = await auth_client.post("/api/v1/achievements/me/evaluate")
    assert repeated.status_code == 200
    assert repeated.json()["newly_earned"] == []
