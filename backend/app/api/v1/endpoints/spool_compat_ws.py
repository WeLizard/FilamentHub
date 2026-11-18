"""WebSocket manager for Spoolman-compatible spool events."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress

from fastapi import WebSocket
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.websockets import WebSocketState

from app.core.config import settings

logger = logging.getLogger(__name__)

_CHANNEL = "fh:spool-events:v1"

Pool = tuple[str, ...]
# Pools name what an event is about, most general part first:
# ("spool", "<id>"), ("filament", "<id>"), ("tag_scan", "<reader id>").
SPOOL_POOL: Pool = ("spool",)
ALL_CHANGES_POOL: Pool = ()
TAG_SCAN_POOL = "tag_scan"


def pool_receives(subscription: Pool, event_pool: Pool) -> bool:
    """Whether a socket subscribed to ``subscription`` hears an event of ``event_pool``.

    A subscription hears every event below it, so ``("spool",)`` follows all
    spools and ``()`` follows every change. Tag scans are the exception to the
    root stream: a scan is not a change to any data, and pushing a new kind of
    message at clients that asked for "all changes" would break them.
    """
    if not subscription and event_pool[:1] == (TAG_SCAN_POOL,):
        return False
    return event_pool[: len(subscription)] == subscription


class SpoolWebSocketManager:
    """Per-user manager for Spoolman-compatible websocket clients.

    Tracks connections by user_id so broadcasts are scoped to the owning user,
    and by pool so each socket receives only the events it subscribed to.
    """

    def __init__(self) -> None:
        self._connections: dict[int, dict[WebSocket, Pool]] = {}
        self._redis: Redis | None = None
        self._listener: asyncio.Task | None = None

    def _client(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=4,
                socket_connect_timeout=0.5,
                socket_timeout=1,
                client_name="fh-spool-events",
            )
        return self._redis

    async def _listen(self) -> None:
        """Deliver events published by any worker to this worker's sockets."""
        backoff = 1.0
        while True:
            try:
                pubsub = Redis.from_url(
                    settings.REDIS_URL, decode_responses=True, socket_connect_timeout=0.5
                ).pubsub()
                await pubsub.subscribe(_CHANNEL)
                backoff = 1.0
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        body = json.loads(message["data"])
                        # A worker still on the previous release publishes no pool.
                        pool = tuple(str(part) for part in body.get("pool", SPOOL_POOL))
                        await self._deliver(int(body["user_id"]), body["event"], pool)
                    except (ValueError, KeyError, TypeError):
                        logger.warning("Dropped malformed spool event", exc_info=True)
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError, ValueError):
                logger.warning("Spool event listener lost Redis", exc_info=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    def connect(self, user_id: int, websocket: WebSocket, pool: Pool = SPOOL_POOL) -> None:
        """Register a connected websocket for a specific user and pool."""
        self._connections.setdefault(user_id, {})[websocket] = pool
        if self._listener is None or self._listener.done():
            with suppress(RuntimeError):
                self._listener = asyncio.get_running_loop().create_task(self._listen())

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """Unregister a websocket for a specific user."""
        user_sockets = self._connections.get(user_id)
        if user_sockets:
            user_sockets.pop(websocket, None)
            if not user_sockets:
                del self._connections[user_id]

    async def broadcast(self, user_id: int, event: dict, pool: Pool = SPOOL_POOL) -> None:
        """Send event to the user's sockets of a matching pool on every worker.

        A socket lives in one worker's memory, so the event goes through Redis
        and each worker delivers to its own. Without Redis it is delivered to
        this worker's sockets only, as before.
        """
        try:
            receivers = await self._client().publish(
                _CHANNEL, json.dumps({"user_id": user_id, "event": event, "pool": list(pool)})
            )
            if receivers:
                return
        except (RedisError, OSError, ValueError, TypeError):
            logger.warning("Spool event fan-out unavailable, delivering locally", exc_info=True)
        await self._deliver(user_id, event, pool)

    async def _deliver(self, user_id: int, event: dict, pool: Pool = SPOOL_POOL) -> None:
        user_sockets = [
            websocket
            for websocket, subscription in list(self._connections.get(user_id, {}).items())
            if pool_receives(subscription, pool)
        ]
        stale: list[WebSocket] = []

        for websocket in user_sockets:
            if (
                websocket.client_state == WebSocketState.DISCONNECTED
                or websocket.application_state == WebSocketState.DISCONNECTED
            ):
                stale.append(websocket)
                continue

            try:
                await websocket.send_json(event)
            except Exception:
                logger.exception("Failed to send spool websocket event to user %s", user_id)
                stale.append(websocket)

        for websocket in stale:
            self.disconnect(user_id, websocket)


spool_ws_manager = SpoolWebSocketManager()
