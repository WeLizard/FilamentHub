"""Admin demand slice for the Workshop waitlist."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.models.user_printer_device import UserPrinterDevice
from app.services.admin_stats_service import get_admin_stats


def _user(email: str, username: str, *, country: str | None, role: UserRole = UserRole.USER) -> User:
    return User(
        email=email,
        username=username,
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        country=country,
        role=role,
    )


@pytest.mark.asyncio
async def test_workshop_interest_splits_by_live_printers_and_country(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(timezone.utc)
    many = _user("interest_many@example.com", "interest_many", country="US")
    few = _user("interest_few@example.com", "interest_few", country="RU")
    admin = _user(
        "interest_admin@example.com",
        "interest_admin",
        country="DE",
        role=UserRole.ADMIN,
    )
    db_session.add_all([many, few, admin])
    await db_session.commit()

    for index in range(5):
        db_session.add(
            UserPrinterDevice(
                user_id=many.id,
                name=f"Printer {index}",
                confirmed_at=now,
            )
        )
    db_session.add(
        UserPrinterDevice(user_id=few.id, name="Printer", confirmed_at=now)
    )
    db_session.add_all(
        [
            Subscription(
                user_id=many.id,
                status=SubscriptionStatus.INTERESTED,
                interested_at=now,
            ),
            Subscription(
                user_id=few.id,
                status=SubscriptionStatus.INTERESTED,
                interested_at=now,
            ),
            Subscription(
                user_id=admin.id,
                status=SubscriptionStatus.INTERESTED,
                interested_at=now,
            ),
        ]
    )
    await db_session.commit()

    stats = await get_admin_stats(db_session, force_refresh=True)

    interest = stats["hardware"]["workshop_interest"]
    assert interest["total"] == 2
    assert interest["over_threshold"] == 1
    assert interest["threshold"] == 4
    assert interest["recent_30d"] == 2
    assert {row["country"]: row["count"] for row in interest["countries"]} == {
        "RU": 1,
        "US": 1,
    }
