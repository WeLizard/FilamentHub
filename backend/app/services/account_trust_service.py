"""One definition of a trusted account, used by every rule that relies on it."""

from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.models.preset import Preset
from app.models.user import User

# Confirmation of the address started on this date. Accounts that existed before
# it were never asked, so they stay trusted; otherwise switching the rules on
# would have emptied the community averages and locked long-time users out of
# actions they already had.
TRUST_REQUIRED_FROM = datetime(2026, 8, 2, tzinfo=timezone.utc)


def account_is_trusted(user: User) -> bool:
    """Whether this account may act where the action reaches other people.

    A disposable mailbox expires in minutes while the confirmation link lives a
    day, so an account opened to abuse something stays unconfirmed — and this
    check holds without maintaining a list of throwaway domains.
    """
    if user.email_verified:
        return True
    created_at = user.created_at
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at < TRUST_REQUIRED_FROM


def trusted_contribution():
    """The same rule as a SQL condition, for presets feeding the community average."""
    return or_(
        Preset.is_official == True,  # noqa: E712 — SQL comparison, not a bool check
        Preset.user_id.is_(None),
        Preset.user_id.in_(
            select(User.id).where(
                or_(
                    User.email_verified == True,  # noqa: E712
                    User.created_at < TRUST_REQUIRED_FROM,
                )
            )
        ),
    )
