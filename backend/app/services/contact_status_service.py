"""Per-channel contact status of a printer.

A channel is one independent way FilamentHub hears from a device: the native
Spoolman link of Moonraker, or one connector (plugin, Edge, OctoPrint bridge).
Each channel reports its own state and time; there is deliberately no merged
"online" flag and no max() across channels - a fresh plugin heartbeat says
nothing about the Moonraker link and the other way round.

Native WebSocket liveness is a lease: the worker holding the socket renews a
Redis entry while the connection is open. A lost lease (worker restart, Redis
outage) is "unknown", never "live". Only the open/close transitions reach the
database.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

ContactState = Literal["not_configured", "live", "silent", "unknown"]

LEASE_SECONDS = 45
RENEW_SECONDS = 15
TOUCH_SECONDS = 600
# A connector heartbeat is expected every ~120 s; a state flips to silent only
# after two missed beats so one slow beat does not make the badge flicker.
CONNECTOR_HEARTBEAT_SECONDS = 120
CONNECTOR_LIVE_FACTOR = 2

NATIVE_MIRROR_TRANSPORTS = frozenset({"spoolman_compat", "legacy_adapter"})
_KEY = "fh:native-ws:v1:"
_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=8,
            socket_connect_timeout=0.5,
            socket_timeout=1,
            client_name="fh-native-presence",
        )
    return _redis


async def _renew(device_id: int, connection_id: str) -> None:
    now = time.time()
    async with _client().pipeline(transaction=False) as pipe:
        pipe.zremrangebyscore(f"{_KEY}{device_id}", "-inf", now)
        pipe.zadd(f"{_KEY}{device_id}", {connection_id: now + LEASE_SECONDS})
        pipe.expire(f"{_KEY}{device_id}", LEASE_SECONDS * 4)
        await pipe.execute()


async def _lease_loop(
    device_id: int,
    connection_id: str,
    touch: Callable[[], Awaitable[None]] | None,
) -> None:
    last_touch = time.monotonic()
    while True:
        await asyncio.sleep(RENEW_SECONDS)
        try:
            await _renew(device_id, connection_id)
        except (RedisError, OSError, ValueError):
            logger.warning("native presence renew failed", exc_info=True)
        # An idle healthy socket sends nothing, so its contact time is advanced
        # here - rarely, because every write is a row update per connected printer.
        if touch is not None and time.monotonic() - last_touch >= TOUCH_SECONDS:
            last_touch = time.monotonic()
            try:
                await touch()
            except Exception:
                logger.warning("native contact touch failed", exc_info=True)


class NativeLease:
    """Presence of one open native socket, renewed by the worker that holds it."""

    def __init__(self, device_id: int, touch: Callable[[], Awaitable[None]] | None = None) -> None:
        self.device_id = device_id
        self.connection_id = uuid4().hex
        self._touch = touch
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        try:
            await _renew(self.device_id, self.connection_id)
        except (RedisError, OSError, ValueError):
            logger.warning("native presence unavailable", exc_info=True)
        self._task = asyncio.create_task(
            _lease_loop(self.device_id, self.connection_id, self._touch)
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        try:
            await _client().zrem(f"{_KEY}{self.device_id}", self.connection_id)
        except (RedisError, OSError, ValueError):
            logger.warning("native presence release failed", exc_info=True)


async def native_leases(device_ids: list[int]) -> dict[int, bool] | None:
    """Device id -> has an unexpired lease; None when Redis cannot answer."""
    if not device_ids:
        return {}
    now = time.time()
    try:
        async with _client().pipeline(transaction=False) as pipe:
            for device_id in device_ids:
                pipe.zcount(f"{_KEY}{device_id}", f"({now}", "+inf")
            counts = await pipe.execute()
    except (RedisError, OSError, ValueError):
        logger.warning("native presence lookup failed", exc_info=True)
        return None
    return {device_id: count > 0 for device_id, count in zip(device_ids, counts, strict=True)}


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def native_state(
    *,
    has_key: bool,
    lease: bool | None,
    connected_at: datetime | None,
    disconnected_at: datetime | None,
) -> ContactState:
    if not has_key:
        return "not_configured"
    if lease is None:
        return "unknown"
    if lease:
        return "live"
    connected, disconnected = _aware(connected_at), _aware(disconnected_at)
    # Opened and never recorded as closed: the lease vanished with its worker.
    if connected is not None and (disconnected is None or disconnected < connected):
        return "unknown"
    return "silent"


def connector_state(last_seen_at: datetime | None, now: datetime | None = None) -> ContactState:
    seen = _aware(last_seen_at)
    if seen is None:
        return "unknown"
    age = ((now or datetime.now(timezone.utc)) - seen).total_seconds()
    return "live" if age < CONNECTOR_HEARTBEAT_SECONDS * CONNECTOR_LIVE_FACTOR else "silent"


def build_contact_channels(
    printer: Any,
    lease: bool | None,
    native_system_id: int | None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    channels: list[dict[str, Any]] = []
    has_key = printer.api_key is not None
    if has_key or printer.last_seen_at is not None:
        channels.append(
            {
                "kind": "native_spoolman",
                "source": "moonraker",
                "connector_id": None,
                "material_system_id": native_system_id,
                "last_contact_at": printer.last_seen_at,
                "state": native_state(
                    has_key=has_key,
                    lease=lease,
                    connected_at=printer.ws_connected_at,
                    disconnected_at=printer.ws_disconnected_at,
                ),
                "basis": "websocket_lease" if has_key else "request",
            }
        )
    for connector in sorted(printer.connectors, key=lambda item: item.id):
        # The native link's own contact time is mirrored onto this connector;
        # it is reported once, as the native channel.
        if not connector.active or connector.transport in NATIVE_MIRROR_TRANSPORTS:
            continue
        channels.append(
            {
                "kind": "connector",
                "source": f"{connector.provider}:{connector.transport}",
                "connector_id": connector.id,
                "material_system_id": connector.material_system_id,
                "last_contact_at": connector.last_seen_at,
                "state": connector_state(connector.last_seen_at, now),
                "basis": "heartbeat",
            }
        )
    return channels
