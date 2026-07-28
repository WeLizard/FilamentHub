"""Usage counters kept in Redis, never in the database.

Writing a row per estimate would tie a hot path to a database write and grow a
table nobody reads, so each estimate bumps O(1) day-stamped keys that expire on
their own. Distinct users are counted with a HyperLogLog: it stores a sketch,
not the ids, so the counters hold nothing about who calculated what. Recording
never raises — a broken counter must not break a calculation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

CALC_TOTAL_PREFIX = "usage:calc:total:"
CALC_METHOD_PREFIX = "usage:calc:method:"
CALC_USERS_PREFIX = "usage:calc:users:"
RETENTION_DAYS = 100

_client = None


def _redis():
    """One pooled client for the process — a fresh pool per estimate would cost
    more than the counters themselves."""
    global _client
    if _client is None:
        import redis.asyncio as aioredis

        _client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def _day_keys(prefix: str, days: int, *, suffix: str = "") -> list[str]:
    today = datetime.utcnow().date()
    return [
        f"{prefix}{today - timedelta(days=offset)}{suffix}"
        for offset in range(days)
    ]


async def record_calculator_estimate(user_id: int, pricing_method: str) -> None:
    day = datetime.utcnow().date()
    try:
        pipe = _redis().pipeline()
        total_key = f"{CALC_TOTAL_PREFIX}{day}"
        method_key = f"{CALC_METHOD_PREFIX}{day}:{pricing_method}"
        users_key = f"{CALC_USERS_PREFIX}{day}"
        ttl = RETENTION_DAYS * 86400

        pipe.incr(total_key)
        pipe.expire(total_key, ttl)
        pipe.incr(method_key)
        pipe.expire(method_key, ttl)
        pipe.pfadd(users_key, user_id)
        pipe.expire(users_key, ttl)
        await pipe.execute()
    except Exception:
        logger.debug("usage counter write failed", exc_info=True)


async def _sum_days(prefix: str, days: int, *, suffix: str = "") -> int:
    values = await _redis().mget(_day_keys(prefix, days, suffix=suffix))
    return sum(int(value) for value in values if value)


async def calculator_usage(methods: tuple[str, ...]) -> dict:
    """Estimate counts for the dashboard. Returns `available: False` when Redis
    cannot be reached, so the UI can say "no data" instead of showing zeros as
    if nobody used the calculator."""
    try:
        redis = _redis()
        return {
            "available": True,
            "estimates_24h": await _sum_days(CALC_TOTAL_PREFIX, 1),
            "estimates_7d": await _sum_days(CALC_TOTAL_PREFIX, 7),
            "estimates_30d": await _sum_days(CALC_TOTAL_PREFIX, 30),
            "users_24h": await redis.pfcount(*_day_keys(CALC_USERS_PREFIX, 1)),
            "users_7d": await redis.pfcount(*_day_keys(CALC_USERS_PREFIX, 7)),
            "users_30d": await redis.pfcount(*_day_keys(CALC_USERS_PREFIX, 30)),
            "methods_30d": {
                method: await _sum_days(CALC_METHOD_PREFIX, 30, suffix=f":{method}")
                for method in methods
            },
        }
    except Exception:
        logger.debug("usage counter read failed", exc_info=True)
        return {"available": False}
