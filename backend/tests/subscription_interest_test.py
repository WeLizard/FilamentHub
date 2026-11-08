"""Workshop waitlist interest stored on the existing subscription lifecycle."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User
from app.services import subscription_service

INTEREST_URL = "/api/v1/subscription/interest"


async def _stored_subscription(db: AsyncSession, user_id: int) -> Subscription | None:
    return await db.scalar(select(Subscription).where(Subscription.user_id == user_id))


@pytest.mark.asyncio
async def test_join_records_interest_on_the_existing_subscription(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    response = await auth_client.post(INTEREST_URL)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "interested"
    assert payload["interested_at"] is not None

    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    assert stored.status == SubscriptionStatus.INTERESTED
    assert stored.interested_at is not None
    assert stored.interest_source == "profile_workshop_tab"


@pytest.mark.asyncio
async def test_join_is_idempotent(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    first = await auth_client.post(INTEREST_URL)
    assert first.status_code == 200
    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    first_interested_at = stored.interested_at

    second = await auth_client.post(INTEREST_URL)

    assert second.status_code == 200
    rows = (
        await db_session.scalars(
            select(Subscription).where(Subscription.user_id == auth_user.id)
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].interested_at == first_interested_at


@pytest.mark.asyncio
async def test_leave_marks_interest_withdrawn_and_preserves_history(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    await auth_client.post(INTEREST_URL)
    before = await _stored_subscription(db_session, auth_user.id)
    assert before is not None
    interested_at = before.interested_at

    response = await auth_client.delete(INTEREST_URL)

    assert response.status_code == 204
    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    assert stored.status == SubscriptionStatus.WITHDRAWN
    assert stored.interested_at == interested_at
    assert (await auth_client.delete(INTEREST_URL)).status_code == 204


@pytest.mark.asyncio
async def test_join_after_withdraw_reopens_interest(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    await auth_client.post(INTEREST_URL)
    await auth_client.delete(INTEREST_URL)

    response = await auth_client.post(INTEREST_URL)

    assert response.status_code == 200
    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    assert stored.status == SubscriptionStatus.INTERESTED


@pytest.mark.asyncio
async def test_leave_preserves_a_consumed_trial(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    db_session.add(
        Subscription(
            user_id=auth_user.id,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db_session.commit()
    await auth_client.post(INTEREST_URL)
    await auth_client.delete(INTEREST_URL)

    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    assert stored.status == SubscriptionStatus.WITHDRAWN
    assert stored.trial_ends_at is not None

    user = await db_session.scalar(
        select(User)
        .options(selectinload(User.subscription))
        .where(User.id == auth_user.id)
    )
    assert user is not None
    with pytest.raises(subscription_service.TrialAlreadyUsedError):
        await subscription_service.start_trial(db_session, user)


@pytest.mark.asyncio
async def test_leave_after_unused_interest_allows_the_trial(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    await subscription_service.refresh_settings_cache(db_session)
    await auth_client.post(INTEREST_URL)
    await auth_client.delete(INTEREST_URL)

    user = await db_session.scalar(
        select(User)
        .options(selectinload(User.subscription))
        .where(User.id == auth_user.id)
    )
    assert user is not None
    subscription = await subscription_service.start_trial(db_session, user)

    assert subscription.status == SubscriptionStatus.TRIALING
    assert subscription.trial_ends_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELED]
)
async def test_interest_preserves_trial_ineligibility_without_a_trial_end(
    auth_client, auth_user: User, db_session: AsyncSession, status: SubscriptionStatus
) -> None:
    db_session.add(Subscription(user_id=auth_user.id, status=status))
    await db_session.commit()

    with pytest.raises(subscription_service.TrialAlreadyUsedError):
        await subscription_service.start_trial(db_session, auth_user)

    assert (await auth_client.post(INTEREST_URL)).status_code == 200
    with pytest.raises(subscription_service.TrialAlreadyUsedError):
        await subscription_service.start_trial(db_session, auth_user)

    assert (await auth_client.delete(INTEREST_URL)).status_code == 204
    with pytest.raises(subscription_service.TrialAlreadyUsedError):
        await subscription_service.start_trial(db_session, auth_user)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "cached_status", "stored_status", "expected_error"),
    [
        (
            subscription_service.start_trial,
            SubscriptionStatus.INTERESTED,
            SubscriptionStatus.EXPIRED,
            subscription_service.TrialAlreadyUsedError,
        ),
        (
            subscription_service.join_workshop_interest,
            SubscriptionStatus.WITHDRAWN,
            SubscriptionStatus.ACTIVE,
            subscription_service.PlanInterestUnavailableError,
        ),
        (
            subscription_service.leave_workshop_interest,
            SubscriptionStatus.INTERESTED,
            SubscriptionStatus.ACTIVE,
            subscription_service.PlanInterestUnavailableError,
        ),
    ],
)
async def test_subscription_mutations_read_the_locked_row_after_auth_load(
    auth_user: User,
    db_session: AsyncSession,
    operation,
    cached_status: SubscriptionStatus,
    stored_status: SubscriptionStatus,
    expected_error,
) -> None:
    db_session.add(Subscription(user_id=auth_user.id, status=cached_status))
    await db_session.commit()
    await db_session.refresh(auth_user, attribute_names=["subscription"])
    # Simulate a concurrent write after auth has loaded the relationship.
    await db_session.execute(
        update(Subscription)
        .where(Subscription.user_id == auth_user.id)
        .values(status=stored_status)
        .execution_options(synchronize_session=False)
    )
    assert auth_user.subscription.status == cached_status

    with pytest.raises(expected_error):
        await operation(db_session, auth_user)


@pytest.mark.asyncio
async def test_active_subscription_cannot_be_replaced_by_interest(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    db_session.add(Subscription(user_id=auth_user.id, status=SubscriptionStatus.ACTIVE))
    await db_session.commit()

    response = await auth_client.post(INTEREST_URL)

    assert response.status_code == 409
    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    assert stored.status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_leave_does_not_touch_an_active_subscription(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    db_session.add(Subscription(user_id=auth_user.id, status=SubscriptionStatus.ACTIVE))
    await db_session.commit()

    response = await auth_client.delete(INTEREST_URL)

    assert response.status_code == 409
    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    assert stored.status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_expired_subscription_can_return_to_interest(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    db_session.add(Subscription(user_id=auth_user.id, status=SubscriptionStatus.EXPIRED))
    await db_session.commit()

    response = await auth_client.post(INTEREST_URL)

    assert response.status_code == 200
    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    assert stored.status == SubscriptionStatus.INTERESTED
    assert stored.interested_at is not None


@pytest.mark.asyncio
async def test_interest_does_not_grant_pro_access(
    auth_user: User, db_session: AsyncSession
) -> None:
    await subscription_service.refresh_settings_cache(db_session)
    db_session.add(
        Subscription(
            user_id=auth_user.id,
            status=SubscriptionStatus.INTERESTED,
            interested_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    user = await db_session.scalar(
        select(User)
        .options(selectinload(User.subscription))
        .where(User.id == auth_user.id)
    )

    assert user is not None
    assert subscription_service.pro_active(user) is False


@pytest.mark.asyncio
async def test_me_exposes_interest_status_and_timestamp(
    auth_client, db_session: AsyncSession
) -> None:
    await auth_client.post(INTEREST_URL)
    db_session.expire_all()

    response = await auth_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    subscription = response.json()["subscription"]
    assert subscription["status"] == "interested"
    assert subscription["interested_at"] is not None


@pytest.mark.asyncio
async def test_lapsed_trial_can_join_waitlist(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    db_session.add(
        Subscription(
            user_id=auth_user.id,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db_session.commit()

    response = await auth_client.post(INTEREST_URL)

    assert response.status_code == 200
    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    assert stored.status == SubscriptionStatus.INTERESTED


@pytest.mark.asyncio
async def test_lapsed_paid_period_can_join_waitlist(
    auth_client, auth_user: User, db_session: AsyncSession
) -> None:
    db_session.add(
        Subscription(
            user_id=auth_user.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_end=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db_session.commit()

    response = await auth_client.post(INTEREST_URL)

    assert response.status_code == 200
    stored = await _stored_subscription(db_session, auth_user.id)
    assert stored is not None
    assert stored.status == SubscriptionStatus.INTERESTED


@pytest.mark.asyncio
async def test_unused_interest_can_become_a_trial(
    auth_user: User, db_session: AsyncSession
) -> None:
    await subscription_service.refresh_settings_cache(db_session)
    interested_at = datetime.now(timezone.utc)
    db_session.add(
        Subscription(
            user_id=auth_user.id,
            status=SubscriptionStatus.INTERESTED,
            interested_at=interested_at,
        )
    )
    await db_session.commit()
    user = await db_session.scalar(
        select(User)
        .options(selectinload(User.subscription))
        .where(User.id == auth_user.id)
    )
    assert user is not None

    subscription = await subscription_service.start_trial(db_session, user)

    assert subscription.status == SubscriptionStatus.TRIALING
    assert subscription.trial_ends_at is not None
    assert subscription.interested_at is not None


@pytest.mark.asyncio
async def test_interest_does_not_resurrect_a_used_trial(
    auth_user: User, db_session: AsyncSession
) -> None:
    await subscription_service.refresh_settings_cache(db_session)
    db_session.add(
        Subscription(
            user_id=auth_user.id,
            status=SubscriptionStatus.INTERESTED,
            interested_at=datetime.now(timezone.utc),
            trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db_session.commit()
    user = await db_session.scalar(
        select(User)
        .options(selectinload(User.subscription))
        .where(User.id == auth_user.id)
    )
    assert user is not None

    with pytest.raises(subscription_service.TrialAlreadyUsedError):
        await subscription_service.start_trial(db_session, user)
