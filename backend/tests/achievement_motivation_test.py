"""Costly achievement boundaries: factual evidence, secrecy, and no self-credit."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.brand import Brand
from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.crm import (
    CrmCustomer,
    CrmOrder,
    CrmOrderStatus,
    CrmQuote,
    CrmQuoteEvent,
    CrmQuoteEventType,
    CrmQuoteStatus,
    CrmQuoteVersion,
)
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import (
    MaterialSlot,
    MaterialSystem,
    PhysicalPrinterConnector,
)
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.print_job import PrintJob, PrintJobEvent, PrintJobMaterial, PrintJobStatus
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool
from app.models.wiki_article import WikiArticle, WikiArticleStatus, WikiGuideProgress
from app.models.wiki_category import WikiCategory
from app.models.wiki_space import WikiSpace
from app.services.achievement_service import (
    AUTOMATIC_SPOOL_ASSIGNMENT,
    BAMBU_CONNECTED,
    FIRST_HUNDRED,
    FIRST_ORDER_COMPLETED,
    FIRST_PROFILE,
    FIRST_QUOTE_ACCEPTED,
    FIRST_QUOTE_SENT,
    FIRST_SAVED_CALCULATION,
    FIRST_WIKI_ARTICLE,
    FULL_BUSINESS_CYCLE,
    FULL_MATERIAL_SYSTEM,
    GCODE_CALCULATION,
    HAPPY_HARE_CONNECTED,
    MANUFACTURER_LEARNING_PATH,
    MATERIAL_SYSTEM_CONNECTED,
    MATERIAL_TO_PRINT,
    OCTOPRINT_CONNECTED,
    PRESET_CONFIRMED_BY_AUTHOR,
    PRESET_PUBLISHER_5,
    PRESET_USED_BY_ANOTHER,
    PRESETS_USED_BY_3,
    PRESETS_USED_BY_10,
    PRINTER_INTEGRATION_CONNECTED,
    PRINTER_LEARNING_PATH,
    RETURNING_CUSTOMER,
    SPOOL_COLLECTOR_1,
    SPOOL_COLLECTOR_20,
    SPOOL_COLLECTOR_100,
    SPOOL_DEPLETED_BY_PRINT,
    achievement_overview,
)


async def test_learning_paths_count_semantic_steps_and_accept_article_aliases(
    db_session,
    auth_user,
):
    printer_progress = [
        "user:catalog",
        "article:catalog-material",
        "article:orca-preset-guide",
        "user:shelf",
        "article:my-filaments-guide",
        "user:printer",
    ]
    db_session.add_all(
        [
            WikiGuideProgress(user_id=auth_user.id, guide_id=guide_id)
            for guide_id in printer_progress
        ]
    )
    await db_session.commit()

    incomplete = await achievement_overview(db_session, user_id=auth_user.id)
    incomplete_codes = {item.code for item in incomplete.achievements}
    assert PRINTER_LEARNING_PATH not in incomplete_codes
    printer_next = next(
        item
        for item in incomplete.next_achievements
        if item.code == PRINTER_LEARNING_PATH
    )
    assert (printer_next.current, printer_next.target) == (5, 6)

    remaining_progress = [
        "article:production-calculation-guide",
        "article:brand-representation-guide",
        "brand:profile",
        "article:brand-materials-guide",
        "brand:presets",
        "article:brand-qr-guide",
        "brand:insights",
    ]
    db_session.add_all(
        [
            WikiGuideProgress(user_id=auth_user.id, guide_id=guide_id)
            for guide_id in remaining_progress
        ]
    )
    await db_session.commit()

    completed = await achievement_overview(db_session, user_id=auth_user.id)
    repeated = await achievement_overview(db_session, user_id=auth_user.id)
    completed_codes = {item.code for item in completed.achievements}
    assert {PRINTER_LEARNING_PATH, MANUFACTURER_LEARNING_PATH} <= completed_codes
    assert completed.newly_earned == [
        PRINTER_LEARNING_PATH,
        MANUFACTURER_LEARNING_PATH,
    ]
    assert repeated.newly_earned == []
    route_awards = list(
        await db_session.scalars(
            select(UserAchievement).where(
                UserAchievement.user_id == auth_user.id,
                UserAchievement.code.in_(
                    (PRINTER_LEARNING_PATH, MANUFACTURER_LEARNING_PATH)
                ),
            )
        )
    )
    assert len(route_awards) == 2
    assert {item.evidence_type for item in route_awards} == {
        "wiki_guide_progress"
    }


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
        PRESET_CONFIRMED_BY_AUTHOR,
    }
    assert self_only.saved_by_other_users == 0
    assert self_only.confirmed_uses_by_other_users == 0

    db_session.add(UserSavedPreset(user_id=other.id, preset_id=preset.id))
    await db_session.commit()

    saved_only = await achievement_overview(db_session, user_id=auth_user.id)
    assert {item.code for item in saved_only.achievements} == {
        FIRST_HUNDRED,
        FIRST_PROFILE,
        PRESET_CONFIRMED_BY_AUTHOR,
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
    expected = {
        FIRST_HUNDRED,
        FIRST_PROFILE,
        PRESET_CONFIRMED_BY_AUTHOR,
        PRESET_USED_BY_ANOTHER,
    }
    assert {item.code for item in useful.achievements} == expected
    assert {item.code for item in repeated.achievements} == expected
    assert useful.saved_by_other_users == 1
    assert useful.confirmed_uses_by_other_users == 1
    assert await db_session.scalar(select(func.count(UserAchievement.id))) == 4


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
    material_system = MaterialSystem(
        user_id=auth_user.id,
        physical_printer_id=printer.id,
        name="Happy Hare",
        kind="mmu",
        provider="happy_hare",
        active=True,
    )
    db_session.add(material_system)
    await db_session.flush()
    db_session.add_all(
        [
            MaterialSlot(
                user_id=auth_user.id,
                material_system_id=material_system.id,
                provider_index=index,
                active=True,
            )
            for index in range(2)
        ]
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
        PRESETS_USED_BY_3,
        PRESETS_USED_BY_10,
        SPOOL_COLLECTOR_1,
        SPOOL_COLLECTOR_20,
        SPOOL_COLLECTOR_100,
        MATERIAL_SYSTEM_CONNECTED,
        HAPPY_HARE_CONNECTED,
        FIRST_WIKI_ARTICLE,
    }
    assert {item.code for item in overview.achievements} == expected
    assert set(overview.newly_earned) == expected
    next_codes = {item.code for item in overview.next_achievements}
    assert "first_catalog_contribution" in next_codes
    assert SPOOL_COLLECTOR_100 not in next_codes
    assert HAPPY_HARE_CONNECTED not in next_codes
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
    hidden_codes = {
        BAMBU_CONNECTED,
        HAPPY_HARE_CONNECTED,
        FULL_MATERIAL_SYSTEM,
        OCTOPRINT_CONNECTED,
        SPOOL_COLLECTOR_100,
        SPOOL_DEPLETED_BY_PRINT,
    }
    assert hidden_codes.isdisjoint(item["code"] for item in read_only.json()["next_achievements"])
    assert await db_session.scalar(select(func.count(UserAchievement.id))) == 0

    evaluated = await auth_client.post("/api/v1/achievements/me/evaluate")
    assert evaluated.status_code == 200
    assert evaluated.json()["newly_earned"] == [FIRST_HUNDRED]

    repeated = await auth_client.post("/api/v1/achievements/me/evaluate")
    assert repeated.status_code == 200
    assert repeated.json()["newly_earned"] == []


async def test_connected_material_workflow_awards_only_confirmed_hardware_facts(
    db_session,
    auth_user,
):
    printer = UserPrinterDevice(user_id=auth_user.id, name="Achievement workshop")
    spools = [UserSpool(user_id=auth_user.id, initial_weight_g=1000) for _ in range(4)]
    db_session.add_all([printer, *spools])
    await db_session.flush()

    system = MaterialSystem(
        user_id=auth_user.id,
        physical_printer_id=printer.id,
        name="Connected MMU",
        kind="mmu",
        provider="manual",
        active=True,
    )
    db_session.add(system)
    await db_session.flush()
    slots = [
        MaterialSlot(
            user_id=auth_user.id,
            material_system_id=system.id,
            provider_index=index,
            active=True,
        )
        for index in range(4)
    ]
    db_session.add_all(slots)
    await db_session.flush()

    observed_at = datetime.now(timezone.utc)
    db_session.add(
        PhysicalPrinterConnector(
            user_id=auth_user.id,
            physical_printer_id=printer.id,
            material_system_id=system.id,
            provider="moonraker",
            transport="orca_plugin",
            active=True,
            last_seen_at=observed_at,
        )
    )
    db_session.add_all(
        [
            PhysicalPrinterConnector(
                user_id=auth_user.id,
                physical_printer_id=printer.id,
                material_system_id=system.id,
                provider="octoprint",
                transport="native_bridge",
                active=True,
                last_seen_at=observed_at,
            ),
            PhysicalPrinterConnector(
                user_id=auth_user.id,
                physical_printer_id=printer.id,
                material_system_id=system.id,
                provider="bambu",
                transport="orca_plugin",
                active=True,
                last_seen_at=observed_at,
            ),
        ]
    )
    db_session.add_all(
        [
            MaterialSlotAssignment(
                user_id=auth_user.id,
                material_slot_id=slot.id,
                spool_id=spool.id,
                source="provider_report",
                source_ts=observed_at,
                active=True,
            )
            for slot, spool in zip(slots, spools, strict=True)
        ]
    )
    db_session.add(
        PresetUsageEvent(
            user_id=auth_user.id,
            spool_id=spools[0].id,
            event_type=PresetUsageEventType.printer_report,
            remaining_weight_g=0,
        )
    )
    await db_session.commit()

    overview = await achievement_overview(db_session, user_id=auth_user.id)
    earned = {item.code: item for item in overview.achievements}
    assert {
        MATERIAL_SYSTEM_CONNECTED,
        PRINTER_INTEGRATION_CONNECTED,
        OCTOPRINT_CONNECTED,
        BAMBU_CONNECTED,
        AUTOMATIC_SPOOL_ASSIGNMENT,
        FULL_MATERIAL_SYSTEM,
        SPOOL_DEPLETED_BY_PRINT,
    }.issubset(earned)
    assert earned[FULL_MATERIAL_SYSTEM].hidden is True
    assert earned[SPOOL_DEPLETED_BY_PRINT].hidden is True


async def test_production_achievements_follow_saved_and_linked_business_facts(
    db_session,
    auth_user,
):
    calculation = CalculatorHistoryEntry(
        user_id=auth_user.id,
        title="Saved estimate",
        pricing_method="cost_plus",
        request_data={"quantity": 1},
        result_data={"total": 1200},
    )
    customer = CrmCustomer(user_id=auth_user.id, name="Returning customer")
    quote = CrmQuote(
        user_id=auth_user.id,
        number="Q-ACH-1",
        title="Achievement quote",
        status=CrmQuoteStatus.SENT,
        currency="RUB",
    )
    db_session.add_all([calculation, customer, quote])
    await db_session.commit()

    first = await achievement_overview(db_session, user_id=auth_user.id)
    first_codes = {item.code for item in first.achievements}
    assert FIRST_SAVED_CALCULATION in first_codes
    assert GCODE_CALCULATION not in first_codes
    assert FIRST_QUOTE_SENT not in first_codes

    parsed_calculation = CalculatorHistoryEntry(
        user_id=auth_user.id,
        title="Parsed G-code estimate",
        pricing_method="cost_plus",
        request_data={"quantity": 1},
        result_data={"total": 1400},
        parsed_gcode={"print_time_seconds": 3600, "filament_used_g": 42},
    )
    quote.status = CrmQuoteStatus.ACCEPTED
    now = datetime.now(timezone.utc)
    quote.sent_at = now
    quote.accepted_at = now
    db_session.add_all(
        [
            parsed_calculation,
            CrmQuoteEvent(
                quote_id=quote.id,
                actor_user_id=auth_user.id,
                event_type=CrmQuoteEventType.STATUS_CHANGED,
                from_status=CrmQuoteStatus.DRAFT.value,
                to_status=CrmQuoteStatus.SENT.value,
            ),
            CrmQuoteEvent(
                quote_id=quote.id,
                actor_user_id=auth_user.id,
                event_type=CrmQuoteEventType.STATUS_CHANGED,
                from_status=CrmQuoteStatus.SENT.value,
                to_status=CrmQuoteStatus.ACCEPTED.value,
            ),
            CrmQuoteVersion(
                quote_id=quote.id,
                version_number=1,
                source_history_id=calculation.id,
                seller_snapshot={},
                customer_snapshot={},
                calculation_snapshot={"history_id": calculation.id},
                subtotal=1200,
                tax_total=0,
                grand_total=1200,
            ),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            CrmOrder(
                user_id=auth_user.id,
                quote_id=quote.id,
                customer_id=customer.id,
                number="O-ACH-1",
                title="Linked order",
                status=CrmOrderStatus.COMPLETED,
                currency="RUB",
                total=1200,
                material_requirements=[],
                completed_at=now,
            ),
            CrmOrder(
                user_id=auth_user.id,
                customer_id=customer.id,
                number="O-ACH-2",
                title="Returning order",
                status=CrmOrderStatus.COMPLETED,
                currency="RUB",
                total=900,
                material_requirements=[],
                completed_at=now,
            ),
        ]
    )
    await db_session.commit()

    completed = await achievement_overview(db_session, user_id=auth_user.id)
    completed_codes = {item.code for item in completed.achievements}
    assert {
        FIRST_SAVED_CALCULATION,
        GCODE_CALCULATION,
        FIRST_QUOTE_SENT,
        FIRST_QUOTE_ACCEPTED,
        FIRST_ORDER_COMPLETED,
        RETURNING_CUSTOMER,
        FULL_BUSINESS_CYCLE,
    }.issubset(completed_codes)


async def test_material_to_print_requires_one_provider_confirmed_consumption_chain(
    db_session,
    auth_user,
):
    calculation = CalculatorHistoryEntry(
        user_id=auth_user.id,
        title="Production calculation",
        pricing_method="cost_plus",
        request_data={"quantity": 1},
        result_data={"total": 600},
        parsed_gcode={"print_time_seconds": 1800},
    )
    printer = UserPrinterDevice(user_id=auth_user.id, name="Production printer")
    spool = UserSpool(user_id=auth_user.id, initial_weight_g=1000, used_weight_g=50)
    db_session.add_all([calculation, printer, spool])
    await db_session.flush()
    now = datetime.now(timezone.utc)
    job = PrintJob(
        user_id=auth_user.id,
        physical_printer_id=printer.id,
        calculator_history_id=calculation.id,
        title="Linked production job",
        status=PrintJobStatus.completed,
        source="manual",
        source_ref="achievement-material-to-print",
        source_payload_hash="a" * 64,
        finished_at=now,
    )
    db_session.add(job)
    await db_session.flush()
    db_session.add_all(
        [
            PrintJobMaterial(
                print_job_id=job.id,
                spool_id=spool.id,
                planned_weight_g=50,
                spool_snapshot={"spool_name": "Achievement spool"},
            ),
            PrintJobEvent(
                print_job_id=job.id,
                user_id=auth_user.id,
                status=PrintJobStatus.completed,
                source="user",
                event_key="user:completed",
                payload_hash="b" * 64,
                occurred_at=now,
            ),
            PresetUsageEvent(
                user_id=auth_user.id,
                device_id=printer.id,
                spool_id=spool.id,
                print_job_id=job.id,
                event_type=PresetUsageEventType.printer_report,
                delta_weight_g=50,
                remaining_weight_g=950,
            ),
        ]
    )
    await db_session.commit()

    manual_only = await achievement_overview(db_session, user_id=auth_user.id)
    assert MATERIAL_TO_PRINT not in {item.code for item in manual_only.achievements}

    db_session.add(
        PrintJobEvent(
            print_job_id=job.id,
            user_id=auth_user.id,
            status=PrintJobStatus.completed,
            source="octoprint",
            event_key="octoprint:completed",
            payload_hash="c" * 64,
            occurred_at=now,
        )
    )
    await db_session.commit()

    provider_confirmed = await achievement_overview(db_session, user_id=auth_user.id)
    assert MATERIAL_TO_PRINT in {item.code for item in provider_confirmed.achievements}
