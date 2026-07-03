"""Subscription / Pro entitlement logic.

Single decision point for "does this user have Pro (calculator) access".

Design (reverse trial, payment-ready):
- Every user has a ``Subscription`` row (auto-created as ``trialing``).
- A global kill-switch ``paywall_enforced`` (app_settings) gates enforcement.
  While it is False (current launch state) everyone has access — the reverse
  trial is effectively unlimited. Flip it on later to start enforcing.
- ``trial_days`` (app_settings) sets trial length for newly created subscriptions
  (None = no expiry / permanent trial).
- Payments are not wired yet; a future webhook just sets ``status=active`` +
  ``current_period_end`` on the subscription and everything else keeps working.

Global settings are cached in-process so synchronous serialization
(``UserResponse.model_validate``) can read them without an async DB call. The
cache is refreshed on startup and whenever an admin changes a setting.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from app.models.app_setting import AppSetting
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

SETTING_PAYWALL_ENFORCED = "paywall_enforced"
SETTING_TRIAL_DAYS = "trial_days"

# In-process cache of global settings (see module docstring).
_settings_cache: dict[str, object] = {"paywall_enforced": False, "trial_days": None}


# --------------------------------------------------------------------------- #
# Global settings (app_settings table + in-process cache)
# --------------------------------------------------------------------------- #
async def _read_setting(db: AsyncSession, key: str) -> str | None:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    return row.value if row else None


async def _write_setting(db: AsyncSession, key: str, value: str | None) -> None:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await db.commit()


async def refresh_settings_cache(db: AsyncSession) -> None:
    """Load global settings from the DB into the in-process cache."""
    enforced = await _read_setting(db, SETTING_PAYWALL_ENFORCED)
    trial = await _read_setting(db, SETTING_TRIAL_DAYS)
    _settings_cache["paywall_enforced"] = (enforced == "true")
    _settings_cache["trial_days"] = int(trial) if (trial not in (None, "")) else None


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
    """Return the user's subscription, creating a trialing one if missing."""
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


def _loaded_subscription(user: User) -> Subscription | None:
    """Return user.subscription only if already loaded (never triggers async lazy load)."""
    if "subscription" in sa_inspect(user).unloaded:
        return None
    return user.subscription


def pro_active(user: User) -> bool:
    """Effective Pro (calculator) access. Uses cached global settings + loaded subscription.

    admin → always; paywall not enforced → everyone (reverse trial); otherwise a valid
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
    if sub.status == SubscriptionStatus.ACTIVE:
        return sub.current_period_end is None or sub.current_period_end > now
    if sub.status == SubscriptionStatus.TRIALING:
        return sub.trial_ends_at is None or sub.trial_ends_at > now
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
    }
