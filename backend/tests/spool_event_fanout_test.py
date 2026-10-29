"""A spool event reaches sockets held by another worker; without Redis it stays local."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.websockets import WebSocketState

from app.api.v1.endpoints.spool_compat_ws import SpoolWebSocketManager


def _socket() -> Mock:
    socket = Mock()
    socket.client_state = WebSocketState.CONNECTED
    socket.application_state = WebSocketState.CONNECTED
    socket.send_json = AsyncMock()
    return socket


@pytest.mark.asyncio
async def test_event_is_published_for_all_workers_not_delivered_twice_locally():
    manager = SpoolWebSocketManager()
    socket = _socket()
    manager._connections[5] = {socket}
    manager._redis = Mock(publish=AsyncMock(return_value=2))

    await manager.broadcast(5, {"type": "spool"})

    payload = json.loads(manager._redis.publish.await_args.args[1])
    assert payload == {"user_id": 5, "event": {"type": "spool"}}
    socket.send_json.assert_not_awaited()

    # What another worker published arrives through the listener path.
    await manager._deliver(payload["user_id"], payload["event"])
    socket.send_json.assert_awaited_once_with({"type": "spool"})


@pytest.mark.asyncio
@pytest.mark.parametrize("outage", ["down", "nobody-listening"])
async def test_event_still_reaches_this_workers_sockets_without_redis(outage):
    manager = SpoolWebSocketManager()
    socket = _socket()
    manager._connections[5] = {socket}
    publish = (
        AsyncMock(side_effect=RedisConnectionError("down"))
        if outage == "down"
        else AsyncMock(return_value=0)
    )
    manager._redis = Mock(publish=publish)

    await manager.broadcast(5, {"type": "spool"})

    socket.send_json.assert_awaited_once_with({"type": "spool"})
