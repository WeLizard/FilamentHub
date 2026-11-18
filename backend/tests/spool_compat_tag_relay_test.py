"""Spoolman 0.27 tag scan relay: readers, scan answers and live event routing."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import spool_compat
from app.api.v1.endpoints.spool_compat_ws import SpoolWebSocketManager, pool_receives
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.services import tag_scan_relay
from tests.spool_compat_test import _seed_spool_context

BASE = "/api/v1/spool_compat"


@pytest.fixture(autouse=True)
def _fresh_relay(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, dict, tuple[str, ...]]]:
    """Give each test its own relay memory and capture what would be broadcast."""
    monkeypatch.setattr(tag_scan_relay, "_local_readers", {})
    monkeypatch.setattr(tag_scan_relay, "_local_debounce", {})
    sent: list[tuple[int, dict, tuple[str, ...]]] = []

    async def broadcast(user_id: int, event: dict, pool: tuple[str, ...] = ("spool",)) -> None:
        sent.append((user_id, event, pool))

    monkeypatch.setattr(spool_compat.spool_ws_manager, "broadcast", broadcast)
    return sent


@pytest.mark.asyncio
async def test_scan_answers_the_device_and_tells_listeners_once(
    client: AsyncClient,
    db_session: AsyncSession,
    _fresh_relay: list,
) -> None:
    user, spool, device = await _seed_spool_context(db_session)
    key = device.api_key
    # The capability probe clients use before switching to native tags.
    assert (await client.get(f"{BASE}/{key}/api/v1/tag/reader")).json() == []
    assert (await client.get(f"{BASE}/{key}/v1/info")).json()["version"] == "0.27.1"

    scan = {"uid": "04:a2:b3:c4", "reader_id": "voron-gate0", "name": "Voron gate 0"}
    unknown = await client.post(f"{BASE}/{key}/v1/tag/scan", json=scan)
    repeat = await client.post(f"{BASE}/{key}/v1/tag/scan", json=scan)
    await client.post(f"{BASE}/{key}/v1/spool/{spool.id}/tag", json={"uid": "04A2B3C4"})
    _fresh_relay.clear()
    linked = await client.post(f"{BASE}/{key}/v1/tag/scan", json=scan)

    # Both match keys are always present, so "no match" is an answer, not an omission.
    assert unknown.json() == {
        "uid": "04A2B3C4", "reader_id": "voron-gate0", "name": "Voron gate 0",
        "matched_spool_id": None, "matched_filament_id": None, "created": False,
    }
    # A tag resting on a reader is answered every time ...
    assert repeat.json() == unknown.json()
    assert linked.json()["matched_spool_id"] == spool.id
    assert linked.json()["matched_filament_id"] is None
    # ... and a scan that resolves differently is announced at once, not debounced.
    assert [(event["type"], event["resource"], pool) for _user, event, pool in _fresh_relay] == [
        ("scanned", "tag_scan", ("tag_scan", "voron-gate0")),
    ]
    assert _fresh_relay[0][0] == user.id
    assert _fresh_relay[0][1]["payload"]["matched_spool_id"] == spool.id

    readers = (await client.get(f"{BASE}/{key}/v1/tag/reader")).json()
    assert [(item["reader_id"], item["name"], item["last_uid"]) for item in readers] == [
        ("voron-gate0", "Voron gate 0", "04A2B3C4"),
    ]
    # Half a byte is not a UID; such a scan is refused instead of being matched loosely.
    assert (await client.post(f"{BASE}/{key}/v1/tag/scan", json={"uid": "04A2B"})).status_code == 422


@pytest.mark.asyncio
async def test_readers_and_scans_belong_to_the_account_of_the_key(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _user, _spool, device = await _seed_spool_context(db_session)
    stranger = User(email="other@example.com", username="other_user", password_hash="x", active=True)
    other_device = UserPrinterDevice(
        user=stranger, name="Other printer", device_fingerprint="other-fp", api_key="other_device_api_key",
    )
    db_session.add_all([stranger, other_device])
    await db_session.commit()

    await client.post(f"{BASE}/{device.api_key}/v1/tag/scan", json={"uid": "0102", "reader_id": "mine"})

    assert (await client.get(f"{BASE}/other_device_api_key/v1/tag/reader")).json() == []
    assert (await client.get(f"{BASE}/not-a-key/v1/tag/reader")).status_code == 401
    assert (await client.get(f"{BASE}/v1/tag/reader")).status_code == 401
    by_header = await client.get(f"{BASE}/api/v1/tag/reader", headers={"X-API-Key": device.api_key})
    assert [item["reader_id"] for item in by_header.json()] == ["mine"]


@pytest.mark.asyncio
async def test_reader_registry_forgets_old_readers_and_keeps_the_last_name() -> None:
    now = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
    await tag_scan_relay.remember_reader(1, "bench", "Bench scale", "0102", now - timedelta(hours=30))
    await tag_scan_relay.remember_reader(1, "gate0", "Gate 0", "0A0B", now - timedelta(minutes=5))
    # A trimmed-down agent that stops sending its name must not blank the picker.
    await tag_scan_relay.remember_reader(1, "gate0", None, None, now)

    readers = await tag_scan_relay.list_readers(1, now)

    assert readers == [
        {"reader_id": "gate0", "name": "Gate 0", "last_seen": now.isoformat(), "last_uid": "0A0B"},
    ]


def test_pools_route_changes_to_followers_and_keep_scans_out_of_the_root_stream() -> None:
    # Happy Hare's live updates listen on the root socket for every change.
    assert pool_receives((), ("spool", "7"))
    assert pool_receives((), ("filament", "3"))
    assert pool_receives(("spool",), ("spool", "7"))
    assert not pool_receives(("spool",), ("filament", "3"))
    # A scan is not a change to any data: only scan sockets hear it.
    assert not pool_receives((), ("tag_scan", "gate0"))
    assert not pool_receives(("spool",), ("tag_scan", "gate0"))
    assert pool_receives(("tag_scan",), ("tag_scan", "gate0"))
    assert pool_receives(("tag_scan", "gate0"), ("tag_scan", "gate0"))
    assert not pool_receives(("tag_scan", "gate1"), ("tag_scan", "gate0"))


class _Socket:
    def __init__(self) -> None:
        from starlette.websockets import WebSocketState

        self.client_state = self.application_state = WebSocketState.CONNECTED
        self.received: list[dict] = []

    async def send_json(self, event: dict) -> None:
        self.received.append(event)


@pytest.mark.asyncio
async def test_manager_delivers_each_event_only_to_the_sockets_that_follow_it() -> None:
    manager = SpoolWebSocketManager()
    spools, everything, scans, stranger = _Socket(), _Socket(), _Socket(), _Socket()
    for user_id, socket, pool in (
        (1, spools, ("spool",)), (1, everything, ()), (1, scans, ("tag_scan",)), (2, stranger, ()),
    ):
        manager._connections.setdefault(user_id, {})[socket] = pool  # type: ignore[index]

    await manager._deliver(1, {"resource": "spool"}, ("spool", "7"))
    await manager._deliver(1, {"resource": "filament"}, ("filament", "3"))
    await manager._deliver(1, {"resource": "tag_scan"}, ("tag_scan", "gate0"))

    assert [event["resource"] for event in spools.received] == ["spool"]
    assert [event["resource"] for event in everything.received] == ["spool", "filament"]
    assert [event["resource"] for event in scans.received] == ["tag_scan"]
    assert stranger.received == []


@pytest.mark.asyncio
async def test_a_spool_edited_on_the_site_reaches_a_connected_printer(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
    _fresh_relay: list,
) -> None:
    brand = Brand(name="Relay Brand", slug="relay-brand", verified=True, active=True)
    filament = Filament(
        brand=brand, name="Relay PLA", slug="relay-pla", material_type="PLA", color_name="Black",
        color_hex="#111111", diameter=1.75, density=1.24, spool_weight=1000.0, active=True,
    )
    spool = UserSpool(user_id=auth_user.id, filament=filament, initial_weight_g=1000.0, source="manual")
    device = UserPrinterDevice(
        user_id=auth_user.id, name="Voron", device_fingerprint="relay-fp", api_key="relay_device_api_key",
    )
    db_session.add_all([brand, filament, spool, device])
    await db_session.commit()
    spool_id = spool.id

    # Nobody is listening: the edit costs no projection and announces nothing.
    quiet = await auth_client.patch(f"/api/v1/spools/{spool_id}", json={"comment": "shelf A"})
    assert quiet.status_code == 200 and _fresh_relay == []

    device.ws_connected_at = datetime.now(timezone.utc)
    await db_session.commit()
    edited = await auth_client.patch(f"/api/v1/spools/{spool_id}", json={"comment": "shelf B"})
    removed = await auth_client.delete(f"/api/v1/spools/{spool_id}")

    assert edited.status_code == 200 and removed.status_code == 204
    assert [(event["resource"], event["type"], event["payload"]["id"], pool)
            for _user, event, pool in _fresh_relay] == [
        ("spool", "updated", spool_id, ("spool", str(spool_id))),
        ("spool", "deleted", spool_id, ("spool", str(spool_id))),
    ]
    # The printer receives the same spool shape the Spoolman-compatible API serves.
    assert _fresh_relay[0][1]["payload"]["comment"] == "shelf B"
    assert _fresh_relay[0][0] == auth_user.id
