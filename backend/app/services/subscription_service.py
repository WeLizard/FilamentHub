"""Subscription / Pro entitlement logic.

New users start without a subscription and activate their one-time trial
explicitly. Existing subscriptions remain valid, including grandfathered
trials created before the opt-in flow.

Global settings are cached in-process so synchronous serialization
(``UserResponse.model_validate``) can read them without an async DB call. The
cache is refreshed on startup and whenever an admin changes a setting.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from app.models.app_setting import AppSetting
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

SETTING_PAYWALL_ENFORCED = "paywall_enforced"
SETTING_TRIAL_DAYS = "trial_days"
DEFAULT_PAYWALL_ENFORCED = True
DEFAULT_TRIAL_DAYS = 14

# In-process cache of global settings (see module docstring).
_settings_cache: dict[str, object] = {
    "paywall_enforced": DEFAULT_PAYWALL_ENFORCED,
    "trial_days": DEFAULT_TRIAL_DAYS,
}


class TrialAlreadyUsedError(Exception):
    """Raised when a user tries to restart a consumed trial."""


class PlanInterestUnavailableError(Exception):
    """The account already has access or a billing state that must not be replaced."""


INTEREST_SOURCE = "profile_workshop_tab"


def _as_utc(value: datetime) -> datetime:
    """Normalize DB datetimes for SQLite tests and PostgreSQL runtime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
# Global settings (app_settings table + in-process cache)
# --------------------------------------------------------------------------- #
async def _read_setting(db: AsyncSession, key: str) -> tuple[bool, str | None]:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    return (row is not None, row.value if row else None)


async def _write_setting(db: AsyncSession, key: str, value: str | None) -> None:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await db.commit()


async def refresh_settings_cache(db: AsyncSession) -> None:
    """Load global settings from the DB into the in-process cache."""
    enforced_exists, enforced = await _read_setting(db, SETTING_PAYWALL_ENFORCED)
    trial_exists, trial = await _read_setting(db, SETTING_TRIAL_DAYS)
    _settings_cache["paywall_enforced"] = (
        enforced == "true" if enforced_exists else DEFAULT_PAYWALL_ENFORCED
    )
    _settings_cache["trial_days"] = (
        int(trial)
        if trial_exists and trial not in (None, "")
        else None if trial_exists
        else DEFAULT_TRIAL_DAYS
    )


def paywall_enforced() -> bool:
    """Cached: is the calculator paywall currently enforced?"""
    return bool(_settings_cache["paywall_enforced"])


def trial_days() -> int | None:
    """Cached: trial length in days for new subscriptions (None = permanent)."""
    value = _settings_cache["trial_days"]
    return int(value) if isinstance(value, int) else None


async def set_paywall_enforced(db: AsyncSession, enabled: bool) -> None:
    await _write_setting(db, SETTING_PAYWALL_ENFORCED, "true" if enabled else "false")
    await refresh_settings_cache(db)


async def set_trial_days(db: AsyncSession, days: int | None) -> None:
    await _write_setting(db, SETTING_TRIAL_DAYS, str(days) if days is not None else None)
    await refresh_settings_cache(db)


# --------------------------------------------------------------------------- #
# Subscriptions
# --------------------------------------------------------------------------- #
def _trial_end_for_new() -> datetime | None:
    days = trial_days()
    if days is None:
        return None
    return datetime.now(timezone.utc) + timedelta(days=days)


async def get_or_create_subscription(db: AsyncSession, user: User) -> Subscription:
    """Return a subscription row for administrative entitlement changes.

    User-facing trial activation must use :func:`start_trial`; this helper is
    retained for admin grants and legacy callers.
    """
    sub = (
        await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    ).scalar_one_or_none()
    if sub is None:
        sub = Subscription(
            user_id=user.id,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=_trial_end_for_new(),
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
    return sub


def _locked_subscription(user_id: int) -> Select[tuple[Subscription]]:
    # Authentication may already have loaded this row before we acquired the lock.
    return (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def start_trial(db: AsyncSession, user: User) -> Subscription:
    """Start a user's one-time trial, or return the already active entitlement.

    Repeated clicks are idempotent and never extend the trial. A consumed trial
    cannot be restarted without an explicit administrative grant.
    """
    user_id = user.id
    query = _locked_subscription(user_id)
    sub = await db.scalar(query)

    if sub is None:
        sub = Subscription(
            user_id=user_id,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=_trial_end_for_new(),
        )
        db.add(sub)
        try:
            await db.commit()
            await db.refresh(sub)
            return sub
        except IntegrityError:
            # The unique user_id constraint resolves concurrent inserts.
            await db.rollback()
            sub = (await db.execute(query)).scalar_one()

    now = datetime.now(timezone.utc)
    if sub.is_comp or sub.status == SubscriptionStatus.ACTIVE:
        return sub
    if sub.status == SubscriptionStatus.TRIALING:
        if sub.trial_ends_at is None or _as_utc(sub.trial_ends_at) > now:
            return sub
        sub.status = SubscriptionStatus.EXPIRED
        await db.commit()

    if sub.status in {SubscriptionStatus.INTERESTED, SubscriptionStatus.WITHDRAWN}:
        if sub.trial_ends_at is not None:
            raise TrialAlreadyUsedError
        sub.status = SubscriptionStatus.TRIALING
        sub.trial_ends_at = _trial_end_for_new()
        await db.commit()
        await db.refresh(sub)
        return sub

    raise TrialAlreadyUsedError


async def join_workshop_interest(db: AsyncSession, user: User) -> Subscription:
    """Record waitlist interest on the account's single subscription row.

    The row stays the source of truth for the future paid period: ``interested``
    grants no access and can later become a trial or an active subscription.
    Repeated joins are idempotent and keep the original timestamp.
    """
    user_id = user.id
    query = _locked_subscription(user_id)
    sub = await db.scalar(query)
    now = datetime.now(timezone.utc)

    if sub is None:
        sub = Subscription(
            user_id=user_id,
            status=SubscriptionStatus.INTERESTED,
            interested_at=now,
            interest_source=INTEREST_SOURCE,
        )
        db.add(sub)
        try:
            await db.commit()
            await db.refresh(sub)
            return sub
        except IntegrityError:
            # Another request created the row while we were joining.
            await db.rollback()
            sub = (await db.execute(query)).scalar_one()
            now = datetime.now(timezone.utc)

    if sub.is_comp:
        raise PlanInterestUnavailableError
    if (
        sub.status == SubscriptionStatus.TRIALING
        and sub.trial_ends_at is not None
        and _as_utc(sub.trial_ends_at) <= now
    ):
        sub.status = SubscriptionStatus.EXPIRED
    if (
        sub.status == SubscriptionStatus.ACTIVE
        and sub.current_period_end is not None
        and _as_utc(sub.current_period_end) <= now
    ):
        sub.status = SubscriptionStatus.EXPIRED
    if sub.status in {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.PAST_DUE,
    }:
        raise PlanInterestUnavailableError
    if sub.status == SubscriptionStatus.INTERESTED:
        return sub

    if sub.status != SubscriptionStatus.WITHDRAWN and sub.trial_ends_at is None:
        # Preserve ineligibility when replacing a legacy status with no end
        # date, for example when an unlimited trial was revoked.
        sub.trial_ends_at = now
    sub.status = SubscriptionStatus.INTERESTED
    sub.interested_at = now
    sub.interest_source = INTEREST_SOURCE
    await db.commit()
    await db.refresh(sub)
    return sub


async def leave_workshop_interest(db: AsyncSession, user: User) -> bool:
    """Leave the waitlist without deleting the subscription/trial history."""
    sub = await db.scalar(_locked_subscription(user.id))

    if sub is None:
        return False
    if sub.status == SubscriptionStatus.INTERESTED:
        sub.status = SubscriptionStatus.WITHDRAWN
        await db.commit()
        return True
    if sub.status == SubscriptionStatus.WITHDRAWN:
        return False
    if sub.is_comp or sub.status in {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.PAST_DUE,
    }:
        raise PlanInterestUnavailableError
    return False


def _loaded_subscription(user: User) -> Subscription | None:
    """Return user.subscription only if already loaded (never triggers async lazy load)."""
    if "subscription" in sa_inspect(user).unloaded:
        return None
    return user.subscription


def pro_active(user: User) -> bool:
    """Effective Pro (calculator) access. Uses cached global settings + loaded subscription.

    admin → always; explicitly open paywall → everyone; otherwise a valid
    subscription (active / trialing-not-expired / complimentary).
    """
    if user.role == UserRole.ADMIN:
        return True
    if not paywall_enforced():
        return True
    sub = _loaded_subscription(user)
    if sub is None:
        return False
    now = datetime.now(timezone.utc)
    if sub.is_comp:
        return True
    if sub.status == SubscriptionStatus.ACTIVE:
        return sub.current_period_end is None or _as_utc(sub.current_period_end) > now
    if sub.status == SubscriptionStatus.TRIALING:
        return sub.trial_ends_at is None or _as_utc(sub.trial_ends_at) > now
    return False


def subscription_summary(user: User) -> dict | None:
    """Serializable subscription summary for API responses (None if not loaded)."""
    sub = _loaded_subscription(user)
    if sub is None:
        return None
    return {
        "status": sub.status.value,
        "trial_ends_at": sub.trial_ends_at,
        "current_period_end": sub.current_period_end,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "is_comp": sub.is_comp,
        "interested_at": sub.interested_at,
    }
