"""Bounded, best-effort UI hints; the database remains the source of truth.

One Redis Pub/Sub connection per worker fans out to authenticated WebSockets
only while user screens are visible. No database session, printer credentials,
or durable usage events enter this best-effort channel.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.material_system import PhysicalPrinterConnector
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice

logger = logging.getLogger(__name__)

STREAM_SECONDS = 300
KEEPALIVE_SECONDS = 25
TICKET_SECONDS = 15
AUTH_RECHECK_SECONDS = 15
AUTH_LEASE_SECONDS = 30
AUTH_CHECK_TIMEOUT = 2
CONTACT_PROTOCOL = "fh-contact-v1"
MAX_USER_STREAMS = 4
MAX_WORKER_STREAMS = 512
MAX_PENDING_EVENTS = 32
_PENDING = "printer_contact_pending"
_COMMITTED = "printer_contact_committed"
_NAMESPACE = "fh:printer-contact:v1:" + hashlib.sha256(
    str(settings.DATABASE_URL).encode()
).hexdigest()[:16]

# Expiring leases bound tabs across workers; abandoned requests expire without
# a sweeper or a Redis command on every keepalive.
_ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then return 0 end
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[4])
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""


class StreamUnavailable(Exception):
    """The caller must retry with backoff, not fall back to status polling."""


class StreamLimitReached(StreamUnavailable):
    pass


@dataclass(eq=False)
class ContactSubscription:
    user_id: int
    token_id: str
    lease_id: str = field(default_factory=lambda: uuid4().hex)
    queue: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=MAX_PENDING_EVENTS)
    )
    closed: bool = False
    auth_valid_until: float = 0
    auth_ready: asyncio.Event = field(default_factory=asyncio.Event)

    def stop(self) -> None:
        self.closed = True
        self.auth_ready.set()
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(None)

    def can_deliver(self) -> bool:
        if self.closed or time.monotonic() >= self.auth_valid_until:
            self.stop()
            return False
        return True

    def offer(self, payload: dict) -> None:
        if self.closed:
            return
        try:
            self.queue.put_nowait(payload)
        except asyncio.QueueFull:
            # A slow screen must reconnect and read a snapshot, not grow memory
            # indefinitely or silently lose the update that restores its badge.
            self.stop()


class PrinterContactBroker:
    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis
        self._pubsub: Any = None
        self._reader: asyncio.Task | None = None
        self._auth_guard: asyncio.Task | None = None
        self._auth_wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._users: dict[int, set[ContactSubscription]] = defaultdict(set)
        self._ready: dict[str, asyncio.Event] = {}
        self._last_warning = 0.0

    @property
    def redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(
                settings.REDIS_URL, decode_responses=True, max_connections=16,
                socket_connect_timeout=0.5, socket_timeout=1,
                client_name="fh-printer-contact",
            )
        return self._redis

    @staticmethod
    def channel(user_id: int | None) -> str:
        return f"{_NAMESPACE}:{user_id if user_id is not None else 'auth'}"

    @staticmethod
    def lease_key(user_id: int) -> str:
        return f"{_NAMESPACE}:leases:{user_id}"

    def _warn(self) -> None:
        # A Redis outage must not produce a log line for every printer heartbeat.
        if time.monotonic() - self._last_warning > 30:
            self._last_warning = time.monotonic()
            logger.warning("Printer contact event transport unavailable", exc_info=True)

    async def publish(self, messages: list[tuple[int | None, dict]]) -> None:
        if not messages:
            return
        try:
            async with asyncio.timeout(0.5):
                async with self.redis.pipeline(transaction=False) as pipe:
                    for user_id, payload in messages:
                        if payload["type"] == "revoke":
                            pipe.set(f"{_NAMESPACE}:deny-token:{payload['token_id']}", 1, ex=TICKET_SECONDS + 1)
                        elif payload["type"] == "disconnect":
                            pipe.set(f"{_NAMESPACE}:deny-user:{user_id}", 1, ex=TICKET_SECONDS + 1)
                        pipe.publish(self.channel(user_id), json.dumps(payload, separators=(",", ":")))
                    await pipe.execute()
        except (RedisError, OSError, TimeoutError, ValueError):
            self._warn()

    async def issue_ticket(self, user_id: int, token_id: str, expires_at: float) -> str:
        try:
            async with asyncio.timeout(1):
                key = f"{_NAMESPACE}:ticket-rate:{user_id}"
                count = await self.redis.eval(
                    "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
                    1, key, TICKET_SECONDS,
                )
                if count > 12:
                    raise StreamLimitReached
                ticket = secrets.token_urlsafe(32)
                key = f"{_NAMESPACE}:ticket:{hashlib.sha256(ticket.encode()).hexdigest()}"
                await self.redis.set(key, json.dumps({
                    "user_id": user_id, "token_id": token_id, "expires_at": expires_at,
                }), ex=TICKET_SECONDS)
                return ticket
        except (RedisError, OSError, TimeoutError, ValueError) as exc:
            self._warn()
            raise StreamUnavailable from exc

    async def consume_ticket(self, ticket: str) -> dict | None:
        if not 32 <= len(ticket) <= 64:
            return None
        try:
            async with asyncio.timeout(1):
                key = f"{_NAMESPACE}:ticket:{hashlib.sha256(ticket.encode()).hexdigest()}"
                value = await self.redis.getdel(key)
                if not value:
                    return None
                session = json.loads(value)
                if await self._denied(session["user_id"], session["token_id"]):
                    return None
                return session
        except (RedisError, OSError, TimeoutError, ValueError) as exc:
            self._warn()
            raise StreamUnavailable from exc

    async def _denied(self, user_id: int, token_id: str) -> bool:
        return bool(await self.redis.exists(
            f"{_NAMESPACE}:deny-token:{token_id}",
            f"{_NAMESPACE}:deny-user:{user_id}",
        ))

    async def _refresh_authorizations(self, subscriptions: list[ContactSubscription]) -> None:
        if not subscriptions:
            return
        # Never extend a lease from the completion time of a stale/slow query.
        checked_at = time.monotonic()
        try:
            async with asyncio.timeout(AUTH_CHECK_TIMEOUT):
                active_users, revoked_tokens = await _load_authorizations(subscriptions)
        except Exception:
            self._warn()
            for subscription in subscriptions:
                subscription.stop()
            return
        for subscription in subscriptions:
            if subscription.closed:
                continue
            if subscription.user_id not in active_users or subscription.token_id in revoked_tokens:
                subscription.stop()
                continue
            subscription.auth_valid_until = checked_at + AUTH_LEASE_SECONDS
            subscription.auth_ready.set()

    async def _guard_authorizations(self) -> None:
        next_check = time.monotonic() + AUTH_RECHECK_SECONDS
        try:
            while True:
                delay = max(0, next_check - time.monotonic())
                try:
                    await asyncio.wait_for(self._auth_wake.wait(), timeout=delay)
                except TimeoutError:
                    pass
                self._auth_wake.clear()
                # Coalesce simultaneous handshakes into the same bounded batch.
                await asyncio.sleep(0.025)
                now = time.monotonic()
                periodic = now >= next_check
                if periodic:
                    # A worker-wide tick prevents staggered admissions from
                    # becoming one repeated database batch per socket. New
                    # handshakes never postpone this periodic authorization.
                    next_check = now + AUTH_RECHECK_SECONDS
                batch = [item for group in self._users.values() for item in group
                         if not item.closed and (periodic or not item.auth_ready.is_set())]
                await self._refresh_authorizations(batch)
        finally:
            # Cancellation/death of the guard must not leave valid-looking
            # sockets behind. The send path also enforces the monotonic lease.
            for group in self._users.values():
                for subscription in group:
                    subscription.stop()

    async def _read(self, pubsub: Any) -> None:
        try:
            while True:
                message = await pubsub.get_message(timeout=KEEPALIVE_SECONDS)
                if message is None:
                    continue
                channel = message["channel"]
                if message["type"] == "subscribe":
                    ready = self._ready.get(channel)
                    if ready:
                        if ready.is_set():
                            # redis-py resubscribed after a connection loss.
                            return
                        ready.set()
                    continue
                if message["type"] != "message":
                    continue
                payload = json.loads(message["data"])
                if channel == self.channel(None):
                    for subscriptions in self._users.values():
                        for subscription in subscriptions:
                            if subscription.token_id == payload.get("token_id"):
                                subscription.stop()
                    continue
                user_id = int(channel.rsplit(":", 1)[1])
                for subscription in self._users.get(user_id, ()):
                    if payload.get("type") == "disconnect":
                        subscription.stop()
                    else:
                        subscription.offer(payload)
        except (RedisError, OSError, ValueError, KeyError):
            self._warn()
        finally:
            # Redis reconnect can lose Pub/Sub messages. End streams so the
            # browser reauthenticates and takes a fresh database snapshot.
            for subscriptions in self._users.values():
                for subscription in subscriptions:
                    subscription.stop()

    @asynccontextmanager
    async def subscribe(self, user_id: int, token_id: str):
        subscription = ContactSubscription(user_id, token_id)
        acquired = False
        try:
            async with asyncio.timeout(3):
                async with self._lock:
                    if sum(map(len, self._users.values())) >= MAX_WORKER_STREAMS:
                        raise StreamLimitReached
                    now = time.time()
                    acquired = bool(await self.redis.eval(
                        _ACQUIRE, 1, self.lease_key(user_id), now,
                        MAX_USER_STREAMS, now + STREAM_SECONDS + 15,
                        subscription.lease_id, STREAM_SECONDS + 30,
                    ))
                    if not acquired:
                        raise StreamLimitReached
                    if ((self._reader is not None and self._reader.done())
                            or (self._auth_guard is not None and self._auth_guard.done())):
                        await self._close_reader()
                    if self._pubsub is None:
                        self._pubsub = self.redis.pubsub()
                        auth_channel = self.channel(None)
                        self._ready[auth_channel] = asyncio.Event()
                        await self._pubsub.subscribe(auth_channel)
                        self._reader = asyncio.create_task(self._read(self._pubsub))
                        self._auth_guard = asyncio.create_task(self._guard_authorizations())
                    first = self.channel(user_id) not in self._ready
                    self._users[user_id].add(subscription)
                    channel = self.channel(user_id)
                    if first:
                        self._ready[channel] = asyncio.Event()
                        await self._pubsub.subscribe(channel)
                    ready = self._ready[channel]
                # Subscribe ACK must precede the initial snapshot; otherwise a
                # contact could fall between the snapshot and the subscription.
                await ready.wait()
                # Logout can race ticket consumption and subscription. Check
                # again after ACK, when later revocations reach the live queue.
                if subscription.closed or await self._denied(user_id, token_id):
                    raise StreamUnavailable
                # Redis revocation is only a fast path. A lost writer publish
                # cannot admit an old ticket or authorize a socket for 300s.
                self._auth_wake.set()
                await subscription.auth_ready.wait()
                if not subscription.can_deliver():
                    raise StreamUnavailable
            yield subscription
        except (RedisError, OSError, TimeoutError, ValueError) as exc:
            self._warn()
            raise StreamUnavailable from exc
        finally:
            async with self._lock:
                subscribers = self._users.get(user_id)
                if subscribers is not None:
                    subscribers.discard(subscription)
                    if not subscribers:
                        self._users.pop(user_id, None)
                        self._ready.pop(self.channel(user_id), None)
                        if self._pubsub is not None:
                            with suppress(RedisError, OSError):
                                await self._pubsub.unsubscribe(self.channel(user_id))
                if not self._users:
                    await self._close_reader()
            if acquired:
                with suppress(RedisError, OSError):
                    await self.redis.zrem(self.lease_key(user_id), subscription.lease_id)

    async def _close_reader(self) -> None:
        if self._auth_guard is not None:
            self._auth_guard.cancel()
            with suppress(asyncio.CancelledError):
                await self._auth_guard
            self._auth_guard = None
        self._auth_wake.clear()
        if self._reader is not None:
            self._reader.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader
            self._reader = None
        if self._pubsub is not None:
            await self._pubsub.aclose()
            self._pubsub = None
        self._ready.clear()

    async def close(self) -> None:
        async with self._lock:
            await self._close_reader()
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


broker = PrinterContactBroker()


async def _load_authorizations(subscriptions: list[ContactSubscription]) -> tuple[set[int], set[str]]:
    # Lazy import avoids the ORM hook registration cycle in db.session.
    from app.db.session import AsyncSessionLocal

    # At most two indexed queries per worker batch, never a session per socket
    # or a query for every contact. No connection is held between checks.
    async with AsyncSessionLocal() as db:
        active_users = set((await db.scalars(select(User.id).where(
            User.id.in_({item.user_id for item in subscriptions}), User.active.is_(True),
        ))).all())
        revoked_tokens = set((await db.scalars(select(RevokedToken.jti).where(
            RevokedToken.jti.in_({item.token_id for item in subscriptions}),
        ))).all())
    return active_users, revoked_tokens


def _collect_contacts(session: Session, _flush_context: Any) -> None:
    transaction = session.get_nested_transaction() or session.get_transaction()
    pending = session.info.setdefault(_PENDING, {}).setdefault(transaction, {})
    for row in session.new | session.dirty:
        if isinstance(row, RevokedToken) and row in session.new:
            pending[(None, "auth", row.jti)] = {"type": "revoke", "token_id": row.jti}
        elif isinstance(row, User) and inspect(row).attrs.active.history.has_changes():
            if not row.active and row.id is not None:
                pending[(row.id, "auth", row.id)] = {"type": "disconnect"}
        elif isinstance(row, (UserPrinterDevice, PhysicalPrinterConnector)):
            state = inspect(row)
            connector = isinstance(row, PhysicalPrinterConnector)
            fields = ("last_seen_at", "active") if connector else ("last_seen_at", "reports_feed")
            if not any(state.attrs[name].history.has_changes() for name in fields):
                continue
            value = row.last_seen_at
            timestamp = None
            if value is not None:
                timestamp = (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).isoformat()
            pending[(row.user_id, "connector" if connector else "printer", row.id)] = {
                "type": "contact",
                "printer_id": row.physical_printer_id if connector else row.id,
                "connector_id": row.id if connector else None,
                "last_seen_at": timestamp,
                "active": row.active if connector else True,
                "reports_feed": None if connector else row.reports_feed,
            }


def _commit_contacts(session: Session) -> None:
    transaction = session.get_nested_transaction() or session.get_transaction()
    messages = session.info.get(_PENDING, {}).pop(transaction, {})
    if transaction is not None and transaction.nested:
        parent = transaction.parent
        session.info.setdefault(_PENDING, {}).setdefault(parent, {}).update(messages)
    else:
        session.info.setdefault(_COMMITTED, {}).update(messages)


def _rollback_contacts(session: Session, previous_transaction: Any) -> None:
    session.info.get(_PENDING, {}).pop(previous_transaction, None)


def install_contact_events() -> None:
    if not event.contains(Session, "after_flush", _collect_contacts):
        event.listen(Session, "after_flush", _collect_contacts)
        event.listen(Session, "after_commit", _commit_contacts)
        event.listen(Session, "after_soft_rollback", _rollback_contacts)


async def publish_committed_contacts(session: Any) -> None:
    messages = session.info.pop(_COMMITTED, {})
    await broker.publish([(key[0], payload) for key, payload in messages.items()])
