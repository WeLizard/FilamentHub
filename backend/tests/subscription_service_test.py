"""Regression tests for Calculator Pro entitlement and opt-in trials."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User
from app.services import subscription_service


@pytest.fixture(autouse=True)
def restore_subscription_settings_cache():
    """Keep the process-wide entitlement cache isolated between tests."""
    original = dict(subscription_service._settings_cache)
    yield
    subscription_service._settings_cache.clear()
    subscription_service._settings_cache.update(original)


async def _create_user(db: AsyncSession, suffix: str) -> User:
    user = User(
        email=f"calculator_{suffix}@test.local",
        username=f"calculator_{suffix}",
        password_hash="$2b$12$test",
        active=True,
    )
    db.add(user)
    await db.commit()
    return await _load_user(db, user.id)


async def _load_user(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(
        select(User)
        .execution_options(populate_existing=True)
        .options(selectinload(User.subscription))
        .where(User.id == user_id)
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_missing_settings_default_to_opt_in_fourteen_day_trial(
    db_session: AsyncSession,
) -> None:
    await subscription_service.refresh_settings_cache(db_session)

    assert subscription_service.paywall_enforced() is True
    assert subscription_service.trial_days() == 14


@pytest.mark.asyncio
async def test_new_user_is_locked_until_trial_is_started(
    db_session: AsyncSession,
) -> None:
    await subscription_service.refresh_settings_cache(db_session)
    user = await _create_user(db_session, "locked")

    assert user.subscription is None
    assert subscription_service.pro_active(user) is False


@pytest.mark.asyncio
async def test_start_trial_is_opt_in_and_idempotent(
    db_session: AsyncSession,
) -> None:
    await subscription_service.refresh_settings_cache(db_session)
    user = await _create_user(db_session, "start")
    before = datetime.now(timezone.utc)

    subscription = await subscription_service.start_trial(db_session, user)
    first_end = subscription.trial_ends_at

    assert subscription.status == SubscriptionStatus.TRIALING
    assert first_end is not None
    first_end_utc = first_end.replace(tzinfo=timezone.utc) if first_end.tzinfo is None else first_end
    assert before + timedelta(days=13, hours=23) < first_end_utc
    assert first_end_utc < before + timedelta(days=14, minutes=1)

    user = await _load_user(db_session, user.id)
    assert subscription_service.pro_active(user) is True

    same_subscription = await subscription_service.start_trial(db_session, user)
    assert same_subscription.id == subscription.id
    assert same_subscription.trial_ends_at == first_end


@pytest.mark.asyncio
async def test_expired_trial_cannot_be_restarted(
    db_session: AsyncSession,
) -> None:
    await subscription_service.refresh_settings_cache(db_session)
    user = await _create_user(db_session, "expired")
    db_session.add(
        Subscription(
            user_id=user.id,
            status=SubscriptionStatus.EXPIRED,
            trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db_session.commit()
    user = await _load_user(db_session, user.id)

    with pytest.raises(subscription_service.TrialAlreadyUsedError):
        await subscription_service.start_trial(db_session, user)


@pytest.mark.asyncio
async def test_explicit_open_access_setting_still_unlocks_calculator(
    db_session: AsyncSession,
) -> None:
    await subscription_service.set_paywall_enforced(db_session, False)
    user = await _create_user(db_session, "open")

    assert subscription_service.paywall_enforced() is False
    assert subscription_service.pro_active(user) is True


@pytest.mark.asyncio
async def test_start_trial_endpoint_refreshes_effective_entitlement(
    auth_client,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    await subscription_service.refresh_settings_cache(db_session)

    before_response = await auth_client.get("/api/v1/auth/me")
    assert before_response.status_code == 200
    assert before_response.json()["has_calculator_access"] is False
    assert before_response.json()["subscription"] is None

    first_response = await auth_client.post("/api/v1/calculator/start-trial")
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["has_calculator_access"] is True
    assert first_payload["subscription"]["status"] == "trialing"
    first_end = first_payload["subscription"]["trial_ends_at"]
    assert first_end is not None

    second_response = await auth_client.post("/api/v1/calculator/start-trial")
    assert second_response.status_code == 200
    assert second_response.json()["subscription"]["trial_ends_at"] == first_end

    stored = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == auth_user.id)
    )
    assert stored is not None


@pytest.mark.asyncio
async def test_open_access_mode_does_not_consume_trial(
    auth_client,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    await subscription_service.set_paywall_enforced(db_session, False)

    response = await auth_client.post("/api/v1/calculator/start-trial")

    assert response.status_code == 200
    assert response.json()["has_calculator_access"] is True
    assert response.json()["subscription"] is None
    stored = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == auth_user.id)
    )
    assert stored is None
