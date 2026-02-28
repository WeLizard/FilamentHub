"""WebSocket manager for Spoolman-compatible spool events."""

from __future__ import annotations

import logging

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class SpoolWebSocketManager:
    """Singleton manager for Spoolman-compatible spool websocket clients."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    def connect(self, websocket: WebSocket) -> None:
        """Register connected websocket client."""
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister websocket client."""
        self._connections.discard(websocket)

    async def broadcast(self, event: dict) -> None:
        """Send event to all active websocket clients."""
        stale_connections: list[WebSocket] = []

        for websocket in self._connections:
            if (
                websocket.client_state == WebSocketState.DISCONNECTED
                or websocket.application_state == WebSocketState.DISCONNECTED
            ):
                stale_connections.append(websocket)
                continue

            try:
                await websocket.send_json(event)
            except Exception:
                logger.exception("Failed to send spool websocket event")
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self._connections.discard(websocket)


spool_ws_manager = SpoolWebSocketManager()
