"""Admin dashboard stats service: correct shape + counts, Redis-optional."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.material_system import MaterialSlot, MaterialSystem
from app.models.user import User, UserRole
from app.models.user_printer_device import UserPrinterDevice
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
        "users", "brands", "presets", "content", "hardware",
        "calculator", "feed_systems", "notifications",
    }
    # On SQLite the service falls back to exact counts.
    assert stats["users"]["total"] >= 2
    assert stats["users"]["admins"] >= 1
    assert stats["brands"]["total"] >= 1
    assert stats["brands"]["verified"] >= 1
    assert "unread" in stats["notifications"]
    assert "gate_slots_assigned" in stats["hardware"]


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

    db_session.add(
        MaterialSlot(user_id=auth_user.id, material_system_id=mmu.id, provider_index=0)
    )
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
