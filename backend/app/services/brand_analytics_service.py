"""Release one fixed, privacy-gated inventory-registration metric per month."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_monthly_analytics_release import BrandMonthlyAnalyticsRelease
from app.models.filament import Filament
from app.models.user_spool import UserSpool
from app.schemas.brand import BrandMonthlySpools

MINIMUM_MONTHLY_OWNERS = 10


async def monthly_registered_spools(
    db: AsyncSession, *, brand_id: int, global_scope: bool
) -> BrandMonthlySpools:
    """Count retained spool rows registered in the last closed UTC month.

    This is a first-request snapshot of surviving registrations, not historical
    inventory or a reconstructed registration event log. Suppression is persisted
    too: later deletions, reassignments or backdated rows cannot change a release.
    """
    now = datetime.now(timezone.utc)
    end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = (end - timedelta(days=1)).replace(day=1)
    month = start.date()
    if not global_scope:
        return BrandMonthlySpools(month=month.strftime("%Y-%m"), status="unavailable_scope")

    key = {"brand_id": brand_id, "month": month}
    release = await db.get(BrandMonthlyAnalyticsRelease, key)
    if release is None:
        spool_count, owner_count = (
            await db.execute(
                select(
                    func.count(UserSpool.id),
                    func.count(func.distinct(UserSpool.user_id)),
                )
                .join(Filament, Filament.id == UserSpool.filament_id)
                .where(
                    Filament.brand_id == brand_id,
                    UserSpool.created_at >= start,
                    UserSpool.created_at < end,
                )
            )
        ).one()
        dialect = db.get_bind().dialect.name
        insert = {"postgresql": postgresql_insert, "sqlite": sqlite_insert}[dialect]
        await db.execute(
            insert(BrandMonthlyAnalyticsRelease)
            .values(
                **key,
                captured_at=now,
                spool_count=int(spool_count) if owner_count >= MINIMUM_MONTHLY_OWNERS else None,
            )
            .on_conflict_do_nothing(index_elements=["brand_id", "month"])
        )
        # Never expose a computed value before its durable release has committed.
        # A concurrent request may have won; read that value instead of our count.
        await db.commit()
        release = await db.get(BrandMonthlyAnalyticsRelease, key)
        if release is None:
            raise RuntimeError("Monthly brand analytics release was not persisted")

    captured_at = release.captured_at
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    return BrandMonthlySpools(
        month=month.strftime("%Y-%m"),
        status="available" if release.spool_count is not None else "insufficient_cohort",
        value=release.spool_count,
        captured_at=captured_at,
    )
