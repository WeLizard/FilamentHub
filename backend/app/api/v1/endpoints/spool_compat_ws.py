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


class SpoolWebSocketManager:
    """Per-user manager for Spoolman-compatible spool websocket clients.

    Tracks connections by user_id so broadcasts are scoped to the owning user.
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
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
                        await self._deliver(int(body["user_id"]), body["event"])
                    except (ValueError, KeyError, TypeError):
                        logger.warning("Dropped malformed spool event", exc_info=True)
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError, ValueError):
                logger.warning("Spool event listener lost Redis", exc_info=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    def connect(self, user_id: int, websocket: WebSocket) -> None:
        """Register a connected websocket for a specific user."""
        self._connections.setdefault(user_id, set()).add(websocket)
        if self._listener is None or self._listener.done():
            with suppress(RuntimeError):
                self._listener = asyncio.get_running_loop().create_task(self._listen())

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """Unregister a websocket for a specific user."""
        user_sockets = self._connections.get(user_id)
        if user_sockets:
            user_sockets.discard(websocket)
            if not user_sockets:
                del self._connections[user_id]

    async def broadcast(self, user_id: int, event: dict) -> None:
        """Send event to the user's sockets on every worker.

        A socket lives in one worker's memory, so the event goes through Redis
        and each worker delivers to its own. Without Redis it is delivered to
        this worker's sockets only, as before.
        """
        try:
            receivers = await self._client().publish(
                _CHANNEL, json.dumps({"user_id": user_id, "event": event})
            )
            if receivers:
                return
        except (RedisError, OSError, ValueError, TypeError):
            logger.warning("Spool event fan-out unavailable, delivering locally", exc_info=True)
        await self._deliver(user_id, event)

    async def _deliver(self, user_id: int, event: dict) -> None:
        user_sockets = list(self._connections.get(user_id, set()))
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
