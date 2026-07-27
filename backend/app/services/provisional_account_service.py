"""Remove accounts a provider sign-in created that were never completed."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

PROVISIONAL_ACCOUNT_TTL_DAYS = 30
_SWEEP_BATCH = 100


async def sweep_abandoned_provisional_accounts(db: AsyncSession) -> int:
    """Delete sign-ins nobody came back to finish.

    Someone can start a provider sign-in, get distracted before accepting the
    documents and return the next day, so the record waits. Waiting forever is
    a different thing, and the account holds an address given for a login that
    never completed.

    Only accounts marked at creation are visible here: everything that predates
    the legal gate carries no mark and is out of reach by construction.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=PROVISIONAL_ACCOUNT_TTL_DAYS)
    abandoned = (
        await db.scalars(
            select(User)
            .where(
                User.provisional_since.is_not(None),
                User.provisional_since < cutoff,
            )
            .order_by(User.provisional_since)
            .limit(_SWEEP_BATCH)
        )
    ).all()
    if not abandoned:
        return 0

    for user in abandoned:
        await db.delete(user)
    await db.commit()
    logger.info("Removed %s unfinished provider sign-ins", len(abandoned))
    return len(abandoned)
