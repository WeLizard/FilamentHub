"""Prevent false liveness on rollback and idle streams exhausting the DB pool."""

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.security import device_api_key_verifier
from app.main import app
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.services import printer_contact_events as contacts


@pytest.mark.asyncio
async def test_only_committed_contacts_escape_including_savepoints(db_session, auth_user, monkeypatch):
    publish = AsyncMock()
    user_id = auth_user.id
    monkeypatch.setattr(contacts.broker, "publish", publish)
    printer = UserPrinterDevice(user_id=auth_user.id, name="Contact fixture")
    db_session.add(printer)
    await db_session.commit()
    await contacts.publish_committed_contacts(db_session)
    publish.reset_mock()
    now = datetime.now(timezone.utc)

    printer.last_seen_at = now
    await db_session.flush()
    await contacts.publish_committed_contacts(db_session)
    assert publish.call_args.args[0] == []
    await db_session.rollback()
    await db_session.refresh(printer)
    await db_session.commit()
    await contacts.publish_committed_contacts(db_session)
    assert publish.call_args.args[0] == []

    printer.last_seen_at = now
    await db_session.flush()
    nested = await db_session.begin_nested()
    printer.last_seen_at = now + timedelta(seconds=5)
    await db_session.flush()
    await nested.rollback()
    await db_session.commit()
    await contacts.publish_committed_contacts(db_session)
    messages = publish.call_args.args[0]
    assert len(messages) == 1
    assert messages[0][0] == user_id
    assert messages[0][1]["last_seen_at"] == now.isoformat()
    assert set(messages[0][1]) == {
        "type", "printer_id", "connector_id", "last_seen_at", "active", "reports_feed",
    }

    await db_session.refresh(printer)
    async with db_session.begin_nested():
        printer.last_seen_at = now + timedelta(seconds=10)
        await db_session.flush()
    await contacts.publish_committed_contacts(db_session)
    assert publish.call_args.args[0] == []
    await db_session.rollback()
    await db_session.commit()
    await contacts.publish_committed_contacts(db_session)
    assert publish.call_args.args[0] == []


@pytest.mark.asyncio
async def test_ticket_authenticates_and_releases_database(auth_client, client, db_session, auth_user, monkeypatch):
    from app.api.v1.endpoints import physical_printers

    async def issue_ticket(user_id, token_id, expires_at):
        assert not db_session.in_transaction()
        assert user_id == auth_user.id
        assert len(token_id) == 64
        return "a" * 43

    issue = AsyncMock(side_effect=issue_ticket)
    monkeypatch.setattr(physical_printers.broker, "issue_ticket", issue)
    response = await auth_client.post("/api/v1/physical-printers/contact-ticket")
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert response.json() == {"ticket": "a" * 43}
    client.headers.pop("Authorization")
    denied = await client.post("/api/v1/physical-printers/contact-ticket")
    assert denied.status_code == 401
    assert issue.await_count == 1


def test_socket_checks_origin_and_single_use_ticket_before_subscribing(monkeypatch):
    from app.api.v1.endpoints import physical_printers

    tickets = {"a" * 43: {"user_id": 7, "token_id": "fingerprint", "expires_at": datetime.now(timezone.utc).timestamp() + 20}}
    visited = []

    async def consume(ticket):
        return tickets.pop(ticket, None)

    @asynccontextmanager
    async def subscribe(user_id, token_id):
        assert user_id == 7
        visited.append("open")
        subscription = contacts.ContactSubscription(user_id, token_id)
        subscription.auth_valid_until = float("inf")
        subscription.queue.put_nowait({
            "type": "contact", "printer_id": 42, "connector_id": None,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "active": True, "reports_feed": True,
        })
        subscription.queue.put_nowait(None)
        try:
            yield subscription
        finally:
            visited.append("closed")

    monkeypatch.setattr(physical_printers.broker, "consume_ticket", consume)
    monkeypatch.setattr(physical_printers.broker, "subscribe", subscribe)
    transport = TestClient(app)
    protocols = [contacts.CONTACT_PROTOCOL, "fh-ticket." + "a" * 43]
    with pytest.raises(WebSocketDisconnect), transport.websocket_connect(
        "/api/v1/physical-printers/contact-events", subprotocols=protocols, headers={"origin": "https://foreign.invalid"},
    ):
        pass
    assert visited == []
    with transport.websocket_connect("/api/v1/physical-printers/contact-events", subprotocols=protocols) as websocket:
        assert websocket.receive_json() == {"type": "ready"}
        payload = websocket.receive_json()
        assert payload["printer_id"] == 42
        assert "token" not in str(payload)
    assert visited == ["open", "closed"]
    with pytest.raises(WebSocketDisconnect), transport.websocket_connect(
        "/api/v1/physical-printers/contact-events", subprotocols=protocols,
    ):
        pass
    assert visited == ["open", "closed"]


def test_slow_screen_is_disconnected_instead_of_growing_memory():
    subscription = contacts.ContactSubscription(1, "fingerprint")
    for _ in range(contacts.MAX_PENDING_EVENTS + 1):
        subscription.offer({"type": "contact"})
    assert subscription.queue.qsize() == 1
    assert subscription.queue.get_nowait() is None


@pytest.mark.asyncio
async def test_revocation_between_ticket_and_subscribe_is_checked_after_ack():
    messages = asyncio.Queue()

    async def subscribe(channel):
        messages.put_nowait({"type": "subscribe", "channel": channel})

    pubsub = Mock(
        subscribe=AsyncMock(side_effect=subscribe),
        get_message=AsyncMock(),
        unsubscribe=AsyncMock(), aclose=AsyncMock(),
    )
    async def receive(**_kwargs):
        return await messages.get()

    pubsub.get_message.side_effect = receive
    redis = Mock(eval=AsyncMock(return_value=1), exists=AsyncMock(return_value=1),
                 zrem=AsyncMock(), pubsub=Mock(return_value=pubsub))
    local = contacts.PrinterContactBroker(redis)
    with pytest.raises(contacts.StreamUnavailable):
        async with local.subscribe(7, "revoked-after-ticket-consumption"):
            pytest.fail("A revoked ticket must not reach the socket handshake")
    assert redis.exists.await_count == 1
    assert not local._users
    assert local._reader is None
    redis.zrem.assert_awaited_once()
    pubsub.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_contact", [None, datetime(2020, 1, 1, tzinfo=timezone.utc)])
async def test_spoolman_ws_only_contact_publishes_without_http_get(
    db_session, auth_user, monkeypatch, previous_contact,
):
    from app.api.v1.endpoints import spool_compat

    key = "scoped-websocket-test-key"
    printer = UserPrinterDevice(
        user_id=auth_user.id, name="WebSocket-only contact", reports_feed=False,
        api_key=device_api_key_verifier(key), last_seen_at=previous_contact,
    )
    db_session.add(printer)
    await db_session.commit()
    # Exercise the independent session used by the real producer, not get_db.
    monkeypatch.setattr(spool_compat, "AsyncSessionLocal", async_sessionmaker(
        db_session.bind, expire_on_commit=False,
    ))
    publish = AsyncMock()
    monkeypatch.setattr(contacts.broker, "publish", publish)
    receive = AsyncMock(side_effect=[
        {"type": "websocket.connect"}, {"type": "websocket.disconnect", "code": 1000},
    ])
    send = AsyncMock()
    socket = WebSocket({"type": "websocket"}, receive, send)

    await spool_compat.spool_ws_scoped(socket, key)

    # Moonraker with spool_id=None may never make a subsequent HTTP request.
    # Its successful WS authentication must reach the existing UI event path.
    publish.assert_awaited_once()
    await db_session.refresh(printer)
    assert printer.last_seen_at is not None
    assert publish.call_args.args[0] == [(auth_user.id, {
        "type": "contact", "printer_id": printer.id, "connector_id": None,
        "last_seen_at": printer.last_seen_at.replace(tzinfo=timezone.utc).isoformat(),
        "active": True, "reports_feed": False,
    })]
    assert printer.reports_feed is False
    send.assert_awaited_once_with({"type": "websocket.accept", "subprotocol": None, "headers": []})


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["invalid-key", "commit-failure"])
async def test_spoolman_ws_failed_auth_or_commit_does_not_publish(
    db_session, auth_user, monkeypatch, failure,
):
    from app.api.v1.endpoints import spool_compat

    key = "scoped-websocket-failure-key"
    printer = UserPrinterDevice(
        user_id=auth_user.id, name="Unconfirmed WebSocket contact",
        api_key=device_api_key_verifier(key), last_seen_at=None,
    )
    db_session.add(printer)
    await db_session.commit()

    class FailingCommitSession(AsyncSession):
        async def commit(self):
            await self.flush()
            raise RuntimeError("Contact commit failed")

    monkeypatch.setattr(spool_compat, "AsyncSessionLocal", async_sessionmaker(
        db_session.bind, expire_on_commit=False,
        class_=FailingCommitSession if failure == "commit-failure" else AsyncSession,
    ))
    publish = AsyncMock()
    monkeypatch.setattr(contacts.broker, "publish", publish)
    socket = WebSocket({"type": "websocket"}, AsyncMock(return_value={"type": "websocket.connect"}), AsyncMock())
    if failure == "commit-failure":
        with pytest.raises(RuntimeError, match="Contact commit failed"):
            await spool_compat.spool_ws_scoped(socket, key)
    else:
        await spool_compat.spool_ws_scoped(socket, "wrong-key")
    publish.assert_not_awaited()
    await db_session.refresh(printer)
    assert printer.last_seen_at is None


def _subscription_redis():
    messages = asyncio.Queue()

    async def subscribe(channel):
        messages.put_nowait({"type": "subscribe", "channel": channel})

    async def receive(**_kwargs):
        return await messages.get()

    pubsub = Mock(subscribe=AsyncMock(side_effect=subscribe), get_message=receive,
                  unsubscribe=AsyncMock(), aclose=AsyncMock())
    return Mock(eval=AsyncMock(return_value=1), exists=AsyncMock(return_value=0),
                zrem=AsyncMock(), pubsub=Mock(return_value=pubsub))


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["revoke", "deactivate", "delete"])
async def test_durable_auth_closes_other_worker_after_lost_publish(db_session, auth_user, monkeypatch, change):
    from app.db import session as sessions

    owner_id = auth_user.id
    other_user = User(email="contact-control@example.com", username="contactcontrol", password_hash="!", active=True)
    db_session.add(other_user)
    await db_session.commit()
    monkeypatch.setattr(sessions, "AsyncSessionLocal", async_sessionmaker(db_session.bind, expire_on_commit=False))
    target = contacts.ContactSubscription(owner_id, "a" * 64)
    other_token = contacts.ContactSubscription(owner_id, "b" * 64)
    control = contacts.ContactSubscription(other_user.id, "c" * 64)
    reader = contacts.PrinterContactBroker()
    reader._users[owner_id].update({target, other_token})
    reader._users[other_user.id].add(control)
    await reader._refresh_authorizations([target, other_token, control])
    assert all(item.can_deliver() for item in (target, other_token, control))

    pipe = Mock(set=Mock(), publish=Mock(), execute=AsyncMock(side_effect=RedisConnectionError("writer failed")))
    context = AsyncMock()
    context.__aenter__.return_value = pipe
    writer = contacts.PrinterContactBroker(Mock(pipeline=Mock(return_value=context)))
    monkeypatch.setattr(contacts, "broker", writer)
    if change == "revoke":
        db_session.add(RevokedToken(jti=target.token_id, expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
    elif change == "deactivate":
        auth_user.active = False
    else:
        await db_session.delete(auth_user)
    await db_session.commit()
    await contacts.publish_committed_contacts(db_session)
    assert not target.closed  # Independent reader did not receive a Redis hint.
    if change != "delete":
        pipe.execute.assert_awaited_once()

    await reader._refresh_authorizations([target, other_token, control])
    assert not target.can_deliver()
    assert other_token.can_deliver() is (change == "revoke")
    assert control.can_deliver()
    # Exercise the healthy reader after the missed revoke; it must not revive
    # the target while a different user's ordinary contact still arrives.
    messages = asyncio.Queue()
    messages.put_nowait({"type": "message", "channel": reader.channel(owner_id), "data": '{"type":"contact"}'})
    messages.put_nowait({"type": "message", "channel": reader.channel(other_user.id), "data": '{"type":"contact"}'})

    async def receive(**_kwargs):
        return await messages.get()

    task = asyncio.create_task(reader._read(Mock(get_message=receive)))
    try:
        assert await asyncio.wait_for(control.queue.get(), 1) == {"type": "contact"}
        assert target.queue.get_nowait() is None
        assert not target.can_deliver()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "timeout"])
async def test_authorization_failure_closes_instead_of_extending_lease(monkeypatch, failure):
    async def unavailable(_subscriptions):
        if failure == "error":
            raise SQLAlchemyError("unavailable")
        await asyncio.Event().wait()

    monkeypatch.setattr(contacts, "_load_authorizations", unavailable)
    monkeypatch.setattr(contacts, "AUTH_CHECK_TIMEOUT", 0.01)
    subscription = contacts.ContactSubscription(7, "fingerprint", auth_valid_until=float("inf"))
    await contacts.PrinterContactBroker()._refresh_authorizations([subscription])
    assert subscription.closed
    assert subscription.auth_ready.is_set()
    assert not subscription.can_deliver()


def test_expired_or_revoked_lease_rejects_an_already_dequeued_contact(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(contacts, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    subscription = contacts.ContactSubscription(7, "fingerprint", auth_valid_until=101.0)
    subscription.offer({"type": "contact"})
    assert subscription.queue.get_nowait() == {"type": "contact"}
    clock[0] = 102.0
    assert not subscription.can_deliver()
    subscription.auth_valid_until = 200.0
    assert not subscription.can_deliver()  # An extended timestamp cannot undo stop().


@pytest.mark.asyncio
async def test_initial_auth_is_batched_and_guard_stops_with_last_subscriber(monkeypatch):
    load = AsyncMock(return_value=(set(range(1, 17)), set()))
    monkeypatch.setattr(contacts, "_load_authorizations", load)
    local = contacts.PrinterContactBroker(_subscription_redis())
    async with AsyncExitStack() as stack:
        subscriptions = await asyncio.gather(*(
            stack.enter_async_context(local.subscribe(index, str(index))) for index in range(1, 17)
        ))
        assert all(item.can_deliver() for item in subscriptions)
        load.assert_awaited_once()
        assert len(load.call_args.args[0]) == 16
        assert local._auth_guard is not None
    assert local._auth_guard is None
    assert local._reader is None
    assert not local._users


@pytest.mark.asyncio
async def test_subscriber_added_during_auth_batch_needs_its_own_result(monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def load(subscriptions):
        calls.append({item.token_id for item in subscriptions})
        if len(calls) == 1:
            started.set()
            await release.wait()
            return {7}, set()
        return {7}, {"revoked"}

    monkeypatch.setattr(contacts, "_load_authorizations", load)
    local = contacts.PrinterContactBroker(_subscription_redis())
    async with AsyncExitStack() as stack:
        first = asyncio.create_task(stack.enter_async_context(local.subscribe(7, "valid")))
        await asyncio.wait_for(started.wait(), 1)
        second = asyncio.create_task(stack.enter_async_context(local.subscribe(7, "revoked")))
        await asyncio.sleep(0)
        release.set()
        assert (await first).can_deliver()
        with pytest.raises(contacts.StreamUnavailable):
            await second
    assert calls == [{"valid"}, {"revoked"}]
    assert local._auth_guard is None


@pytest.mark.asyncio
async def test_staggered_subscribers_share_periodic_tick_without_admission_drift(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(contacts, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    local = contacts.PrinterContactBroker()
    for index, valid_until in enumerate((120.0, 123.0, 127.0), start=1):
        subscription = contacts.ContactSubscription(index, str(index), auth_valid_until=valid_until)
        subscription.auth_ready.set()
        local._users[index].add(subscription)
    waits, batches = [], []
    newcomer = contacts.ContactSubscription(4, "4")

    async def wait_for(wake, timeout):
        wake.close()
        waits.append(timeout)
        if len(waits) == 1:
            # A new admission wakes the guard between the global ticks.
            clock[0] = 105.0
            local._users[4].add(newcomer)
            return
        clock[0] += timeout
        raise TimeoutError

    async def refresh(subscriptions):
        batches.append({item.user_id for item in subscriptions})
        for subscription in subscriptions:
            subscription.auth_valid_until = clock[0] + contacts.AUTH_LEASE_SECONDS
            subscription.auth_ready.set()
        if len(batches) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(contacts, "asyncio", SimpleNamespace(wait_for=wait_for, sleep=AsyncMock()))
    monkeypatch.setattr(local, "_refresh_authorizations", refresh)
    with pytest.raises(asyncio.CancelledError):
        await local._guard_authorizations()
    assert waits == [15.0, 10.0, 15.0]
    assert batches == [{4}, {1, 2, 3, 4}, {1, 2, 3, 4}]


@pytest.mark.asyncio
async def test_guard_cancellation_closes_existing_subscriptions():
    local = contacts.PrinterContactBroker()
    subscription = contacts.ContactSubscription(7, "fingerprint", auth_valid_until=float("inf"))
    local._users[7].add(subscription)
    task = asyncio.create_task(local._guard_authorizations())
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert subscription.closed
