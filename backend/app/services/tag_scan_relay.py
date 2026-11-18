"""Ephemeral state of the tag scan relay: known readers and broadcast debouncing.

A scan is not a change to any data. What the relay keeps is short-lived by
design: which readers reported a scan recently, so a client can offer a
picker, and which scans were just broadcast, so a tag resting on a reader does
not flood every listener. Both are scoped to the account that owns the device
key and kept in Redis so every worker answers the same; a worker without
Redis falls back to its own memory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

# A reader stays pickable for a day after its last scan.
READER_TTL = timedelta(hours=24)
MAX_READERS = 64
# Readers re-detect a tag for as long as it sits on them.
DEBOUNCE_SECONDS = 3
MAX_LOCAL_DEBOUNCE = 1024

_redis: Redis | None = None
_local_readers: dict[int, dict[str, dict]] = {}
_local_debounce: dict[str, float] = {}


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=4,
            socket_connect_timeout=0.5,
            socket_timeout=1,
            client_name="fh-tag-scan-relay",
        )
    return _redis


def _readers_key(user_id: int) -> str:
    return f"fh:tag-readers:v1:{user_id}"


def _merged(previous: dict, name: str | None, uid: str | None, now: datetime) -> dict:
    # A reader that stops sending its name or reports for another reason keeps
    # what it last gave, so a trimmed-down agent cannot blank someone's picker.
    return {
        "name": name if name is not None else previous.get("name"),
        "last_seen": now.isoformat(),
        "last_uid": uid if uid is not None else previous.get("last_uid"),
    }


def _fresh(entries: dict[str, dict], now: datetime) -> list[tuple[str, dict]]:
    """Return unexpired readers, least to most recently seen."""
    kept = []
    for reader_id, entry in entries.items():
        try:
            last_seen = datetime.fromisoformat(entry["last_seen"])
        except (KeyError, TypeError, ValueError):
            continue
        if now - last_seen <= READER_TTL:
            kept.append((reader_id, entry))
    return sorted(kept, key=lambda item: item[1]["last_seen"])


async def remember_reader(
    user_id: int,
    reader_id: str,
    name: str | None,
    uid: str | None,
    now: datetime | None = None,
) -> None:
    """Record that one of the account's readers reported a scan just now."""
    now = now or datetime.now(timezone.utc)
    try:
        client = _client()
        key = _readers_key(user_id)
        raw = await client.hget(key, reader_id)
        previous = json.loads(raw) if raw else {}
        await client.hset(key, reader_id, json.dumps(_merged(previous, name, uid, now)))
        await client.expire(key, int(READER_TTL.total_seconds()))
        if await client.hlen(key) > MAX_READERS:
            entries = {field: json.loads(value) for field, value in (await client.hgetall(key)).items()}
            fresh = _fresh(entries, now)
            stale = set(entries) - {field for field, _entry in fresh[-MAX_READERS:]}
            if stale:
                await client.hdel(key, *stale)
        return
    except (RedisError, OSError, ValueError, TypeError):
        logger.debug("Tag reader registry is local to this worker", exc_info=True)
    readers = _local_readers.setdefault(user_id, {})
    readers[reader_id] = _merged(readers.get(reader_id, {}), name, uid, now)
    for stale_id in set(readers) - {field for field, _entry in _fresh(readers, now)[-MAX_READERS:]}:
        del readers[stale_id]


async def list_readers(user_id: int, now: datetime | None = None) -> list[dict]:
    """Readers of this account seen recently, least to most recently seen."""
    now = now or datetime.now(timezone.utc)
    try:
        raw = await _client().hgetall(_readers_key(user_id))
        entries = {field: json.loads(value) for field, value in raw.items()}
    except (RedisError, OSError, ValueError, TypeError):
        entries = _local_readers.get(user_id, {})
    return [
        {
            "reader_id": reader_id,
            **({"name": entry["name"]} if entry.get("name") else {}),
            "last_seen": entry["last_seen"],
            **({"last_uid": entry["last_uid"]} if entry.get("last_uid") else {}),
        }
        for reader_id, entry in _fresh(entries, now)
    ]


async def claim_broadcast(
    user_id: int,
    uid: str,
    reader_id: str,
    match: tuple[str, int] | None,
) -> bool:
    """Whether this scan should be broadcast, recording it when it should.

    Only the fan-out is debounced: the reporting device is answered every
    time. What the scan resolved to is part of the key, so a tag scanned
    before it was linked and again right after is announced both times.
    """
    digest = hashlib.sha256(
        json.dumps([user_id, uid, reader_id, match]).encode("utf-8")
    ).hexdigest()[:40]
    try:
        return bool(
            await _client().set(f"fh:tag-scan:v1:{digest}", "1", nx=True, ex=DEBOUNCE_SECONDS)
        )
    except (RedisError, OSError, ValueError, TypeError):
        logger.debug("Tag scan debouncing is local to this worker", exc_info=True)
    moment = time.monotonic()
    for key in [key for key, seen in _local_debounce.items() if moment - seen >= DEBOUNCE_SECONDS]:
        del _local_debounce[key]
    if digest in _local_debounce:
        return False
    while len(_local_debounce) >= MAX_LOCAL_DEBOUNCE:
        _local_debounce.pop(next(iter(_local_debounce)))
    _local_debounce[digest] = moment
    return True
