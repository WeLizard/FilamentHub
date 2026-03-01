"""WebSocket manager for Spoolman-compatible spool events."""

from __future__ import annotations

import logging

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class SpoolWebSocketManager:
    """Per-user manager for Spoolman-compatible spool websocket clients.

    Tracks connections by user_id so broadcasts are scoped to the owning user.
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}

    def connect(self, user_id: int, websocket: WebSocket) -> None:
        """Register a connected websocket for a specific user."""
        self._connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """Unregister a websocket for a specific user."""
        user_sockets = self._connections.get(user_id)
        if user_sockets:
            user_sockets.discard(websocket)
            if not user_sockets:
                del self._connections[user_id]

    async def broadcast(self, user_id: int, event: dict) -> None:
        """Send event only to websocket clients belonging to the given user."""
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
