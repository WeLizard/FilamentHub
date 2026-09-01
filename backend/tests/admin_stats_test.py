"""Admin dashboard stats service: correct shape + counts, Redis-optional."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.material_system import MaterialSlot, MaterialSystem
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User, UserRole
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.services.admin_stats_service import get_admin_stats


@pytest.mark.asyncio
async def test_stats_shape_and_counts(db_session: AsyncSession, auth_user: User) -> None:
    admin = User(
        email="statadmin@example.com",
        username="statadmin",
        password_hash="$2b$12$test",
        active=True,
        role=UserRole.ADMIN,
    )
    brand = Brand(name="StatBrand", slug="stat-brand", verified=True)
    db_session.add_all([admin, brand])
    await db_session.commit()

    stats = await get_admin_stats(db_session)

    assert set(stats) == {
        "users",
        "brands",
        "presets",
        "content",
        "hardware",
        "calculator",
        "feed_systems",
        "notifications",
        "operations",
        "catalog_quality",
        "activation",
        "profile_countries",
    }
    # On SQLite the service falls back to exact counts.
    assert stats["users"]["total"] >= 2
    assert stats["users"]["admins"] >= 1
    assert stats["brands"]["total"] >= 1
    assert stats["brands"]["verified"] >= 1
    assert "unread" in stats["notifications"]
    assert "gate_slots_assigned" in stats["hardware"]
    assert stats["activation"]["definition"] == "first_spool"
    assert stats["profile_countries"]["basis"] == "current_profile"


@pytest.mark.asyncio
async def test_activation_and_regions_follow_current_profile_country(
    db_session: AsyncSession, auth_user: User
) -> None:
    auth_user.country = "TR"
    db_session.add(UserSpool(user_id=auth_user.id, initial_weight_g=1000))
    await db_session.commit()

    stats = await get_admin_stats(db_session, force_refresh=True)

    assert stats["activation"]["activated_total"] == 1
    assert stats["activation"]["activated_registered_30d"] == 1
    assert {row["country"]: row["count"] for row in stats["profile_countries"]["all"]}["TR"] == 1

    auth_user.country = "DE"
    await db_session.commit()
    refreshed = await get_admin_stats(db_session, force_refresh=True)
    countries = {row["country"]: row["count"] for row in refreshed["profile_countries"]["all"]}
    assert countries["DE"] == 1
    assert "TR" not in countries


@pytest.mark.asyncio
async def test_catalog_preset_coverage_uses_only_active_filaments(
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="Coverage Brand", slug="coverage-brand")
    db_session.add(brand)
    await db_session.flush()
    active_filament = Filament(
        brand_id=brand.id,
        name="Coverage Active PLA",
        slug="coverage-active-pla",
        material_type="PLA",
        active=True,
    )
    inactive_filament = Filament(
        brand_id=brand.id,
        name="Coverage Retired PLA",
        slug="coverage-retired-pla",
        material_type="PLA",
        active=False,
    )
    db_session.add_all([active_filament, inactive_filament])
    await db_session.flush()
    db_session.add_all(
        [
            Preset(
                filament_id=active_filament.id,
                name="Active catalog preset",
                extruder_temp=210,
                bed_temp=60,
                active=True,
                moderation_status=PresetModerationStatus.APPROVED,
            ),
            Preset(
                filament_id=inactive_filament.id,
                name="Retired catalog preset",
                extruder_temp=210,
                bed_temp=60,
                active=True,
                moderation_status=PresetModerationStatus.APPROVED,
            ),
        ]
    )
    await db_session.commit()

    stats = await get_admin_stats(db_session, force_refresh=True)

    assert stats["catalog_quality"]["active_filaments"] == 1
    assert stats["catalog_quality"]["with_public_preset"] == 1


@pytest.mark.asyncio
async def test_feed_systems_grouped_by_kind_and_provider(
    db_session: AsyncSession, auth_user: User
) -> None:
    device = UserPrinterDevice(
        user_id=auth_user.id,
        name="Stats Device",
        supports_hh=True,
        reports_feed=True,
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)

    mmu = MaterialSystem(
        user_id=auth_user.id,
        physical_printer_id=device.id,
        name="MMU",
        kind="mmu",
        provider="happy_hare",
    )
    db_session.add(mmu)
    await db_session.commit()
    await db_session.refresh(mmu)

    db_session.add(MaterialSlot(user_id=auth_user.id, material_system_id=mmu.id, provider_index=0))
    await db_session.commit()

    stats = await get_admin_stats(db_session, force_refresh=True)
    feed = stats["feed_systems"]

    assert feed["total"] == 1
    assert feed["active"] == 1
    assert feed["by_kind"]["mmu"] == 1
    assert feed["by_provider"]["happy_hare"] == 1
    assert feed["slots"] == 1
    assert feed["printers_with_system"] == 1
    assert feed["devices_happy_hare"] == 1
    assert feed["devices_reporting_feed"] == 1


@pytest.mark.asyncio
async def test_calculator_block_survives_missing_redis(db_session: AsyncSession) -> None:
    stats = await get_admin_stats(db_session, force_refresh=True)
    calculator = stats["calculator"]

    # Counters live in Redis; without it the dashboard must say so rather than
    # report zero estimates as if the calculator went unused.
    assert calculator["available"] is False
    assert calculator["saved_total"] == 0
    assert calculator["profiles"] == 0
