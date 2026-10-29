"""Contact is reported per channel; a lost lease is unknown, never live."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from httpx import AsyncClient

from app.services import contact_status_service as contact

NOW = datetime.now(timezone.utc)


class _FakeRedis:
    """Just the sorted-set commands the presence lease uses."""

    def __init__(self) -> None:
        self.sets: dict[str, dict[str, float]] = {}
        self._queued: list = []

    def pipeline(self, transaction: bool = False):
        return self

    async def __aenter__(self):
        self._queued = []
        return self

    async def __aexit__(self, *exc):
        return False

    def zremrangebyscore(self, key, low, high):
        self._queued.append(
            lambda: [
                self.sets.get(key, {}).pop(m, None)
                for m, v in list(self.sets.get(key, {}).items())
                if v <= float(high)
            ]
        )

    def zadd(self, key, mapping):
        self._queued.append(lambda: self.sets.setdefault(key, {}).update(mapping))

    def expire(self, key, seconds):
        self._queued.append(lambda: None)

    def zcount(self, key, low, high):
        bound = float(str(low).lstrip("("))
        self._queued.append(lambda: sum(1 for v in self.sets.get(key, {}).values() if v > bound))

    async def execute(self):
        return [job() for job in self._queued]

    async def zrem(self, key, member):
        self.sets.get(key, {}).pop(member, None)


@pytest.mark.parametrize(
    ("has_key", "lease", "connected", "disconnected", "expected"),
    [
        (False, True, None, None, "not_configured"),
        (True, None, NOW, None, "unknown"),  # Redis cannot answer
        (True, True, NOW, None, "live"),
        (True, False, NOW, None, "unknown"),  # opened, never closed: worker is gone
        (True, False, NOW, NOW + timedelta(seconds=5), "silent"),  # closed cleanly
        (True, False, None, None, "silent"),  # never opened a socket
        (True, False, NOW, NOW - timedelta(seconds=5), "unknown"),  # reopened after close
    ],
)
def test_native_state(has_key, lease, connected, disconnected, expected):
    assert (
        contact.native_state(
            has_key=has_key, lease=lease, connected_at=connected, disconnected_at=disconnected
        )
        == expected
    )


def test_connector_goes_silent_only_after_two_missed_heartbeats():
    assert contact.connector_state(None) == "unknown"
    assert contact.connector_state(NOW - timedelta(seconds=200), NOW) == "live"
    assert contact.connector_state(NOW - timedelta(seconds=300), NOW) == "silent"


@pytest.mark.asyncio
async def test_lease_lives_while_renewed_and_expires_without_the_holder(monkeypatch):
    server = _FakeRedis()
    monkeypatch.setattr(contact, "_client", lambda: server)
    lease = contact.NativeLease(7)
    await lease.start()
    assert await contact.native_leases([7, 8]) == {7: True, 8: False}
    await lease.stop()
    assert await contact.native_leases([7]) == {7: False}

    # A worker that died never releases: the entry just runs out.
    server.sets["fh:native-ws:v1:9"] = {"ghost": datetime.now().timestamp() - 1}
    assert await contact.native_leases([9]) == {9: False}


@pytest.mark.asyncio
async def test_presence_outage_is_unknown_not_silent(monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    broken = Mock()
    broken.pipeline.side_effect = RedisConnectionError("down")
    monkeypatch.setattr(contact, "_client", lambda: broken)
    assert await contact.native_leases([1]) is None


@pytest.mark.asyncio
async def test_printer_reports_each_channel_without_merging(
    auth_client: AsyncClient, monkeypatch
) -> None:
    created = await auth_client.post(
        "/api/v1/devices/create-with-key", json={"name": "Voron", "gate_count": 2}
    )
    printer_id = created.json()["device"]["id"]

    async def leases(ids):
        return {i: True for i in ids}

    monkeypatch.setattr("app.api.v1.endpoints.physical_printers.native_leases", leases)
    body = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    native = [c for c in body["contact_channels"] if c["kind"] == "native_spoolman"]
    assert [c["state"] for c in native] == ["live"]

    async def unreachable(ids):
        return None

    monkeypatch.setattr("app.api.v1.endpoints.physical_printers.native_leases", unreachable)
    body = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    assert [c["state"] for c in body["contact_channels"] if c["kind"] == "native_spoolman"] == [
        "unknown"
    ]


@pytest.mark.asyncio
async def test_unkeyed_websocket_is_refused_instead_of_looking_connected():
    from starlette.websockets import WebSocket

    from app.api.v1.endpoints import spool_compat

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "websocket.connect"}

    await spool_compat.spool_ws(WebSocket({"type": "websocket"}, receive, send))
    assert [m["type"] for m in sent] == ["websocket.accept", "websocket.close"]
    assert sent[-1]["code"] == 1008
