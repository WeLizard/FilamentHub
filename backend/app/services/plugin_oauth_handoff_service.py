"""Short-lived, server-backed OAuth handoff for desktop plugins."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Literal

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

FLOW_TTL_SECONDS = 10 * 60
FLOW_TOMBSTONE_SECONDS = 5 * 60
POLL_INTERVAL_SECONDS = 2

_FLOW_KEY_PREFIX = "fh:plugin-oauth:flow:"
_LOCK_KEY_PREFIX = "fh:plugin-oauth:lock:"
_redis_client: Redis | None = None


class PluginOAuthHandoffError(Exception):
    """Base error for a plugin OAuth handoff."""


class PluginOAuthHandoffUnavailable(PluginOAuthHandoffError):
    """The shared ephemeral store is unavailable."""


class PluginOAuthHandoffNotFound(PluginOAuthHandoffError):
    """The flow identifier or supplied secret does not match."""


class PluginOAuthHandoffExpired(PluginOAuthHandoffError):
    """The flow reached its logical expiry."""


class PluginOAuthHandoffConflict(PluginOAuthHandoffError):
    """The flow is already terminal or is being changed concurrently."""


@dataclass(frozen=True)
class PluginOAuthFlow:
    flow_id: str
    poll_secret: str
    expires_at: int


@dataclass(frozen=True)
class PluginOAuthPoll:
    status: Literal["pending", "authorized", "failed", "consumed"]
    expires_in: int
    user_id: int | None = None
    auth_version: int | None = None
    error: str | None = None


def _redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_client


def _flow_key(flow_id: str) -> str:
    return f"{_FLOW_KEY_PREFIX}{flow_id}"


def _lock_key(flow_id: str) -> str:
    return f"{_LOCK_KEY_PREFIX}{flow_id}"


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _now() -> int:
    return int(time.time())


def _remaining(record: dict[str, object]) -> int:
    return max(0, int(record["expires_at"]) - _now())


def _decode_record(raw: str | bytes | None) -> dict[str, object]:
    if raw is None:
        raise PluginOAuthHandoffNotFound
    try:
        record = json.loads(raw)
        if not isinstance(record, dict):
            raise ValueError
        return record
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Invalid plugin OAuth handoff state in Redis", exc_info=True)
        raise PluginOAuthHandoffUnavailable from exc


def _validate_secret(record: dict[str, object], field: str, secret: str) -> None:
    expected = record.get(field)
    if not isinstance(expected, str) or not secrets.compare_digest(expected, _digest(secret)):
        raise PluginOAuthHandoffNotFound


def _ensure_current(record: dict[str, object]) -> None:
    if _remaining(record) <= 0:
        raise PluginOAuthHandoffExpired


async def _read(flow_id: str) -> dict[str, object]:
    try:
        return _decode_record(await _redis().get(_flow_key(flow_id)))
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning("Plugin OAuth handoff store read failed", exc_info=True)
        raise PluginOAuthHandoffUnavailable from exc


async def _write(flow_id: str, record: dict[str, object]) -> None:
    purge_at = int(record["expires_at"]) + FLOW_TOMBSTONE_SECONDS
    try:
        await _redis().set(
            _flow_key(flow_id),
            json.dumps(record, separators=(",", ":")),
            exat=purge_at,
        )
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning("Plugin OAuth handoff store write failed", exc_info=True)
        raise PluginOAuthHandoffUnavailable from exc


async def _acquire(flow_id: str) -> str:
    lock_token = secrets.token_urlsafe(12)
    try:
        acquired = await _redis().set(
            _lock_key(flow_id),
            lock_token,
            ex=5,
            nx=True,
        )
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning("Plugin OAuth handoff lock failed", exc_info=True)
        raise PluginOAuthHandoffUnavailable from exc
    if not acquired:
        raise PluginOAuthHandoffConflict
    return lock_token


async def _release(flow_id: str, lock_token: str) -> None:
    try:
        await _redis().eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            _lock_key(flow_id),
            lock_token,
        )
    except (RedisError, OSError, TimeoutError):
        logger.warning("Plugin OAuth handoff lock release failed", exc_info=True)


async def create_flow(provider: str) -> PluginOAuthFlow:
    """Create a high-entropy browser flow ID and a separate polling secret."""
    for _ in range(3):
        flow_id = secrets.token_urlsafe(24)
        poll_secret = secrets.token_urlsafe(32)
        expires_at = _now() + FLOW_TTL_SECONDS
        record: dict[str, object] = {
            "provider": provider,
            "poll_secret_hash": _digest(poll_secret),
            "status": "pending",
            "expires_at": expires_at,
        }
        try:
            created = await _redis().set(
                _flow_key(flow_id),
                json.dumps(record, separators=(",", ":")),
                ex=FLOW_TTL_SECONDS + FLOW_TOMBSTONE_SECONDS,
                nx=True,
            )
        except (RedisError, OSError, TimeoutError) as exc:
            logger.warning("Plugin OAuth handoff creation failed", exc_info=True)
            raise PluginOAuthHandoffUnavailable from exc
        if created:
            return PluginOAuthFlow(flow_id, poll_secret, expires_at)
    raise PluginOAuthHandoffUnavailable


async def bind_oauth_state(
    flow_id: str,
    *,
    provider: str,
    oauth_state: str,
) -> int:
    """Bind one browser OAuth state to the pending handoff."""
    lock_token = await _acquire(flow_id)
    try:
        record = await _read(flow_id)
        _ensure_current(record)
        if record.get("provider") != provider or record.get("status") != "pending":
            raise PluginOAuthHandoffConflict
        record["oauth_state_hash"] = _digest(oauth_state)
        await _write(flow_id, record)
        return _remaining(record)
    finally:
        await _release(flow_id, lock_token)


async def authorize_flow(
    flow_id: str,
    *,
    oauth_state: str,
    user_id: int,
    auth_version: int,
) -> int:
    """Record the authenticated account without storing any account token."""
    lock_token = await _acquire(flow_id)
    try:
        record = await _read(flow_id)
        _ensure_current(record)
        if record.get("status") != "pending":
            raise PluginOAuthHandoffConflict
        expected_state = record.get("oauth_state_hash")
        if not isinstance(expected_state, str) or not secrets.compare_digest(
            expected_state, _digest(oauth_state)
        ):
            raise PluginOAuthHandoffNotFound
        record.update(
            status="authorized",
            user_id=user_id,
            auth_version=auth_version,
        )
        await _write(flow_id, record)
        return _remaining(record)
    finally:
        await _release(flow_id, lock_token)


async def fail_flow(
    flow_id: str,
    *,
    oauth_state: str,
    error: str,
) -> int:
    """Expose a bounded terminal browser-side failure to the polling plugin."""
    lock_token = await _acquire(flow_id)
    try:
        record = await _read(flow_id)
        _ensure_current(record)
        if record.get("status") != "pending":
            raise PluginOAuthHandoffConflict
        expected_state = record.get("oauth_state_hash")
        if not isinstance(expected_state, str) or not secrets.compare_digest(
            expected_state, _digest(oauth_state)
        ):
            raise PluginOAuthHandoffNotFound
        record.update(status="failed", error=error[:64])
        await _write(flow_id, record)
        return _remaining(record)
    finally:
        await _release(flow_id, lock_token)


async def poll_flow(flow_id: str, *, poll_secret: str) -> PluginOAuthPoll:
    """Read pending state or atomically claim an authorized account once."""
    record = await _read(flow_id)
    _validate_secret(record, "poll_secret_hash", poll_secret)
    _ensure_current(record)
    status = str(record.get("status") or "")
    if status == "pending":
        return PluginOAuthPoll(status="pending", expires_in=_remaining(record))
    if status == "failed":
        return PluginOAuthPoll(
            status="failed",
            expires_in=_remaining(record),
            error=str(record.get("error") or "oauth_failed"),
        )
    if status == "consumed":
        return PluginOAuthPoll(status="consumed", expires_in=_remaining(record))
    if status != "authorized":
        raise PluginOAuthHandoffUnavailable

    lock_token = await _acquire(flow_id)
    try:
        record = await _read(flow_id)
        _validate_secret(record, "poll_secret_hash", poll_secret)
        _ensure_current(record)
        if record.get("status") != "authorized":
            return PluginOAuthPoll(
                status="consumed" if record.get("status") == "consumed" else "pending",
                expires_in=_remaining(record),
            )
        try:
            user_id = int(record["user_id"])
            auth_version = int(record["auth_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PluginOAuthHandoffUnavailable from exc
        record["status"] = "consumed"
        await _write(flow_id, record)
        return PluginOAuthPoll(
            status="authorized",
            expires_in=_remaining(record),
            user_id=user_id,
            auth_version=auth_version,
        )
    finally:
        await _release(flow_id, lock_token)
