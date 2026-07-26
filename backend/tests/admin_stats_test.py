"""Admin dashboard stats service: correct shape + counts, Redis-optional."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.user import User, UserRole
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

    assert set(stats) == {"users", "brands", "presets", "content", "hardware", "notifications"}
    # On SQLite the service falls back to exact counts.
    assert stats["users"]["total"] >= 2
    assert stats["users"]["admins"] >= 1
    assert stats["brands"]["total"] >= 1
    assert stats["brands"]["verified"] >= 1
    assert "unread" in stats["notifications"]
    assert "gate_slots_assigned" in stats["hardware"]
