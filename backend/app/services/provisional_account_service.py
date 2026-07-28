"""Remove accounts a provider sign-in created that were never completed."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.user import User

logger = logging.getLogger(__name__)

PROVISIONAL_ACCOUNT_TTL_DAYS = 30
_SWEEP_BATCH = 100
PROVISIONAL_ACCOUNT_SWEEP_INTERVAL_SECONDS = 60 * 60


async def sweep_abandoned_provisional_accounts(db: AsyncSession) -> int:
    """Delete sign-ins nobody came back to finish."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=PROVISIONAL_ACCOUNT_TTL_DAYS)
    removed = 0

    while True:
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
            break

        for user in abandoned:
            await db.delete(user)
        await db.commit()
        removed += len(abandoned)

        if len(abandoned) < _SWEEP_BATCH:
            break

    if removed:
        logger.info("Removed %s unfinished provider sign-ins", removed)
    return removed


async def run_provisional_account_sweeper(
    session_factory: async_sessionmaker[AsyncSession],
    interval_seconds: float = PROVISIONAL_ACCOUNT_SWEEP_INTERVAL_SECONDS,
) -> None:
    """Periodically enforce the retention limit for unfinished provider sign-ins."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with session_factory() as db:
                await sweep_abandoned_provisional_accounts(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Failed to sweep unfinished provider sign-ins", exc_info=True)
