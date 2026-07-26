"""Admin dashboard statistics — computed cheaply, without scanning big tables.

Plain table totals prefer the Postgres row-count estimate (`pg_stat_user_tables`,
instant, no scan), but only trust it for genuinely large tables: below a
threshold an exact COUNT is cheap and always correct. This matters because the
estimate is 0 until autovacuum ANALYZEs a table — on a fresh or freshly-restored
database every "total" would otherwise read 0 while the filtered counts look
right. Filtered counts always run as real COUNTs. The whole result is cached in
Redis for a short TTL; the dashboard refresh button bypasses the cache. On SQLite
(tests) totals fall back to exact counts; Redis failures degrade to a live compute.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_review import FilamentReview
from app.models.notification import Notification
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_gate_state import PresetGateState
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.sync_device import SyncDevice
from app.models.user import User, UserRole
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.models.wiki_article import WikiArticle

logger = logging.getLogger(__name__)

STATS_CACHE_KEY = "admin:stats:v1"
STATS_CACHE_TTL = 120  # seconds — a dashboard does not need per-second accuracy
# Below this row count an exact COUNT is instant, so use it and stay correct;
# only above it is the (analyze-dependent) estimate worth trusting over a scan.
ESTIMATE_TRUST_THRESHOLD = 50_000

# Plain totals served from Postgres estimates (no WHERE clause needed).
_TOTAL_MODELS = [
    User, Brand, Preset, Filament, Printer, PrinterProfile, FilamentReview,
    UserPrinterDevice, UserSpool, PresetGateState, SyncDevice, WikiArticle,
]


def _is_postgres(db: AsyncSession) -> bool:
    try:
        return db.bind.dialect.name == "postgresql"
    except Exception:
        return False


async def _totals(db: AsyncSession) -> dict[type, int]:
    """Row-count per model. On Postgres, trust the instant estimate only for
    tables above the threshold; small or not-yet-analyzed tables (whose estimate
    can be a misleading 0) get an exact COUNT. Non-Postgres backends always count."""
    if _is_postgres(db):
        names = [m.__tablename__ for m in _TOTAL_MODELS]
        rows = (
            await db.execute(
                text(
                    "SELECT relname, n_live_tup FROM pg_stat_user_tables "
                    "WHERE relname = ANY(:names)"
                ),
                {"names": names},
            )
        ).all()
        estimate = {row[0]: int(row[1] or 0) for row in rows}
        totals: dict[type, int] = {}
        for model in _TOTAL_MODELS:
            est = estimate.get(model.__tablename__, 0)
            if est >= ESTIMATE_TRUST_THRESHOLD:
                totals[model] = est
            else:
                totals[model] = await db.scalar(select(func.count(model.id))) or 0
        return totals
    totals = {}
    for model in _TOTAL_MODELS:
        totals[model] = await db.scalar(select(func.count(model.id))) or 0
    return totals


async def _count(db: AsyncSession, model: type, *conditions) -> int:
    stmt = select(func.count(model.id))
    for condition in conditions:
        stmt = stmt.where(condition)
    return await db.scalar(stmt) or 0


async def _compute(db: AsyncSession) -> dict:
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total = await _totals(db)

    return {
        "users": {
            "total": total[User],
            "brands": await _count(db, User, User.brand_id.isnot(None)),
            "admins": await _count(db, User, User.role == UserRole.ADMIN),
            "registered_24h": await _count(db, User, User.created_at >= day_ago),
            "registered_7d": await _count(db, User, User.created_at >= week_ago),
            "registered_30d": await _count(db, User, User.created_at >= month_ago),
            "active_24h": await _count(db, User, User.last_login >= day_ago),
            "active_7d": await _count(db, User, User.last_login >= week_ago),
        },
        "brands": {
            "total": total[Brand],
            "verified": await _count(db, Brand, Brand.verified == True),  # noqa: E712
            "pending_verification": await _count(db, Brand, Brand.verified == False),  # noqa: E712
        },
        "presets": {
            "total": total[Preset],
            "pending_moderation": await _count(
                db, Preset, Preset.moderation_status == PresetModerationStatus.PENDING
            ),
            "approved": await _count(
                db, Preset, Preset.moderation_status == PresetModerationStatus.APPROVED
            ),
            "rejected": await _count(
                db, Preset, Preset.moderation_status == PresetModerationStatus.REJECTED
            ),
        },
        "content": {
            "filaments": total[Filament],
            "printers": total[Printer],
            "printer_profiles": total[PrinterProfile],
            "reviews_total": total[FilamentReview],
            "reviews_7d": await _count(db, FilamentReview, FilamentReview.created_at >= week_ago),
            "wiki_articles": total[WikiArticle],
        },
        "hardware": {
            "devices": total[UserPrinterDevice],
            "spools": total[UserSpool],
            "gate_slots": total[PresetGateState],
            "gate_slots_assigned": await _count(
                db, PresetGateState, PresetGateState.preset_id.isnot(None)
            ),
            "sync_devices": total[SyncDevice],
            "sync_devices_active_7d": await _count(
                db, SyncDevice, SyncDevice.last_sync_at >= week_ago
            ),
        },
        "notifications": {
            "unread": await _count(db, Notification, Notification.read == False),  # noqa: E712
        },
    }


async def get_admin_stats(db: AsyncSession, force_refresh: bool = False) -> dict:
    """Cached admin dashboard stats; recomputed at most once per TTL. With
    force_refresh the cache read is skipped and the fresh result is written back,
    so the dashboard refresh button always reflects the current database."""
    redis = None
    try:
        import redis.asyncio as aioredis

        redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        if not force_refresh:
            cached = await redis.get(STATS_CACHE_KEY)
            if cached:
                return json.loads(cached)
    except Exception:
        logger.debug("admin stats cache read unavailable", exc_info=True)

    stats = await _compute(db)

    if redis is not None:
        try:
            await redis.set(STATS_CACHE_KEY, json.dumps(stats), ex=STATS_CACHE_TTL)
        except Exception:
            logger.debug("admin stats cache write failed", exc_info=True)
        finally:
            try:
                await redis.aclose()
            except Exception:
                pass
    return stats
