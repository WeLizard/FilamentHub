"""Local-dev-only contact stream rehearsal using the existing application/Redis.

Run inside backend-dev: pipe this file to `docker exec -i ... python -`.
Synthetic accounts/printers are reused and deliberately retained. No printer
protocol is contacted. Output contains measurements, never login tokens.
"""

import argparse
import asyncio
import json
import statistics
import time
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select, text
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, token_fingerprint
from app.db.session import AsyncSessionLocal
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)
from app.services.printer_contact_events import CONTACT_PROTOCOL, broker, publish_committed_contacts

WS_URL = "ws://127.0.0.1:8000/api/v1/physical-printers/contact-events"


async def ticket_for(client, headers):
    response = await client.post("/api/v1/physical-printers/contact-ticket", headers=headers)
    response.raise_for_status()
    return response.json()["ticket"]


def socket_for(ticket, origin=None):
    return connect(WS_URL, subprotocols=[CONTACT_PROTOCOL, f"fh-ticket.{ticket}"],
                   origin=origin, proxy=None, compression=None, ping_interval=None,
                   close_timeout=2, max_size=64 * 1024, max_queue=32)


def summary(values):
    values = sorted(values)
    return {"count": len(values), "median_ms": round(statistics.median(values), 2),
            "p95_ms": round(values[min(len(values) - 1, int(len(values) * .95))], 2)}


async def fixtures(count):
    async with AsyncSessionLocal() as db:
        users = []
        printers = []
        for index in range(count):
            email = f"contact-load-{index:04d}@fh.test"
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                user = User(email=email, username=f"contactload{index:04d}", password_hash="!",
                            active=True, email_verified=True, terms_version_accepted=CURRENT_TERMS_VERSION,
                            personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION)
                db.add(user)
                await db.flush()
            printer = (await db.execute(select(UserPrinterDevice).where(
                UserPrinterDevice.user_id == user.id, UserPrinterDevice.name == "Contact stream load fixture",
            ))).scalar_one_or_none()
            if printer is None:
                printer = UserPrinterDevice(user_id=user.id, name="Contact stream load fixture")
                db.add(printer)
                await db.flush()
            users.append(create_access_token({"sub": email}))
            printers.append(printer.id)
        await db.commit()
        return users, printers


async def check_access(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    denied = await client.post("/api/v1/physical-printers/contact-ticket")
    assert denied.status_code == 401
    for operation in ("redis_disconnect", "token_revoke"):
        async with AsyncExitStack() as stack:
            readers = []
            for index in range(4):
                ticket = await ticket_for(client, headers)
                if index == 0:
                    try:
                        async with socket_for(ticket, "https://foreign.invalid"):
                            raise AssertionError("Foreign origin admitted")
                    except InvalidStatus as exc:
                        assert exc.response.status_code == 403
                websocket = await stack.enter_async_context(socket_for(ticket))
                assert json.loads(await websocket.recv()) == {"type": "ready"}
                readers.append(websocket)
                if index == 0:
                    try:
                        async with socket_for(ticket):
                            raise AssertionError("Replayed ticket admitted")
                    except InvalidStatus as exc:
                        assert exc.response.status_code == 403
            try:
                async with socket_for(await ticket_for(client, headers)):
                    raise AssertionError("Fifth screen admitted")
            except InvalidStatus as exc:
                assert exc.response.status_code == 403
            if operation == "redis_disconnect":
                candidates = [item for item in await broker.redis.client_list()
                              if item.get("name") == "fh-printer-contact" and "P" in item.get("flags", "")]
                assert candidates
                for item in candidates:
                    await broker.redis.client_kill_filter(_id=item["id"])
            else:
                unused_ticket = await ticket_for(client, headers)
                async with AsyncSessionLocal() as db:
                    db.add(RevokedToken(jti=token_fingerprint(token), expires_at=datetime.fromtimestamp(
                        decode_access_token(token)["exp"], timezone.utc,
                    )))
                    await db.commit()
                    await publish_committed_contacts(db)
                try:
                    async with socket_for(unused_ticket):
                        raise AssertionError("Ticket survived token revocation")
                except InvalidStatus as exc:
                    assert exc.response.status_code == 403

            async def drain(reader):
                try:
                    async for _line in reader:
                        pass
                except ConnectionClosed:
                    pass

            async with asyncio.timeout(10):
                await asyncio.gather(*(drain(reader) for reader in readers))
        print(json.dumps({"check": operation, "four_streams_closed": True, "fifth_refused": True}), flush=True)
    denied = await client.post("/api/v1/physical-printers/contact-ticket", headers=headers)
    assert denied.status_code == 401
    print(json.dumps({"check": "auth", "anonymous_denied": True, "revoked_denied": True}), flush=True)


async def check_lost_auth_publish(client, token, printer_id):
    headers = {"Authorization": f"Bearer {token}"}
    control_token = create_access_token({"sub": decode_access_token(token)["sub"]})
    async with AsyncExitStack() as stack:
        target = await stack.enter_async_context(socket_for(await ticket_for(client, headers)))
        control = await stack.enter_async_context(socket_for(await ticket_for(
            client, {"Authorization": f"Bearer {control_token}"},
        )))
        assert json.loads(await target.recv()) == {"type": "ready"}
        assert json.loads(await control.recv()) == {"type": "ready"}
        unused_ticket = await ticket_for(client, headers)
        pipe = Mock(set=Mock(), publish=Mock(), execute=AsyncMock(
            side_effect=RedisConnectionError("Injected local benchmark writer failure"),
        ))
        context = AsyncMock()
        context.__aenter__.return_value = pipe
        failing_redis = Mock(pipeline=Mock(return_value=context))
        async with AsyncSessionLocal() as db:
            db.add(RevokedToken(jti=token_fingerprint(token), expires_at=datetime.fromtimestamp(
                decode_access_token(token)["exp"], timezone.utc,
            )))
            await db.commit()
            committed_at = time.perf_counter()
            # Fail only this separate writer process. The running backend's
            # Redis reader, PostgreSQL and other users remain healthy.
            with patch.object(broker, "_redis", failing_redis):
                await publish_committed_contacts(db)
            pipe.execute.assert_awaited_once()
            user_id = (await db.execute(select(User.id).where(
                User.email == decode_access_token(token)["sub"],
            ))).scalar_one()
        assert not await broker._denied(user_id, token_fingerprint(token))
        try:
            async with socket_for(unused_ticket):
                raise AssertionError("Old ticket admitted after lost revocation publish")
        except InvalidStatus as exc:
            assert exc.response.status_code == 403
        async with asyncio.timeout(20):
            await target.wait_closed()
        closed_after = time.perf_counter() - committed_at
        async with AsyncSessionLocal() as db:
            printer = await db.get(UserPrinterDevice, printer_id)
            printer.last_seen_at = datetime.now(timezone.utc)
            await db.commit()
            await publish_committed_contacts(db)
        async with asyncio.timeout(3):
            payload = json.loads(await control.recv())
        assert payload["type"] == "contact" and payload["printer_id"] == printer_id
        print(json.dumps({"check": "lost_auth_publish", "revoked_stream_closed_seconds": round(closed_after, 3),
                          "old_ticket_refused": True, "other_token_still_receives": True,
                          "redis_deny_hint_absent": True}), flush=True)


async def run(count, seconds, checks, auth_failure):
    if not settings.DEBUG or settings.POSTGRES_DB != "filamenthub_dev":
        raise SystemExit("Refusing to run outside the confirmed local development database")
    tokens, printer_ids = await fixtures(count)
    limits = httpx.Limits(max_connections=count + 32, max_keepalive_connections=32)
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", limits=limits,
                                timeout=httpx.Timeout(10, read=None)) as client:
        async def measure_api():
            durations = []
            for index in range(40):
                started = time.perf_counter()
                result = await client.get("/api/v1/physical-printers", headers={"Authorization": f"Bearer {tokens[index % count]}"})
                result.raise_for_status()
                durations.append((time.perf_counter() - started) * 1000)
            return summary(durations)

        async def resources():
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(text("SELECT state, count(*) FROM pg_stat_activity WHERE datname=current_database() GROUP BY state"))).all()
            redis = await broker.redis.info("clients")
            channels = await broker.redis.pubsub_channels(broker.channel(0).rsplit(":", 1)[0] + ":*")
            return {"db_connections": dict(rows), "redis_clients": redis["connected_clients"], "subscribed_channels": len(channels)}

        result = {"streams_requested": count, "baseline_api": await measure_api(), "baseline_resources": await resources()}
        opened = asyncio.Queue()
        observed = asyncio.Queue()
        failures = []
        ramp = asyncio.Semaphore(20)

        async def screen(index):
            announced = False
            try:
                async with ramp:
                    headers = {"Authorization": f"Bearer {tokens[index]}"}
                    ticket = await ticket_for(client, headers)
                    websocket = await socket_for(ticket)
                    assert json.loads(await websocket.recv()) == {"type": "ready"}
                    # Match the visible screen's initial authoritative fetch,
                    # not merely the cheaper cost of 500 idle socket handshakes.
                    snapshot = await client.get("/api/v1/physical-printers", headers=headers)
                    snapshot.raise_for_status()
                    assert any(printer["id"] == printer_ids[index] for printer in snapshot.json())
                    announced = True
                    opened.put_nowait(True)
                async for message in websocket:
                    payload = json.loads(message)
                    if payload["type"] == "contact":
                        assert payload["printer_id"] == printer_ids[index], "Cross-user event leak"
                        received = datetime.now(timezone.utc)
                        sent = datetime.fromisoformat(payload["last_seen_at"])
                        observed.put_nowait((index, (received - sent).total_seconds() * 1000))
            except Exception as exc:
                failures.append(type(exc).__name__)
                if not announced:
                    opened.put_nowait(False)
                raise
            finally:
                if 'websocket' in locals():
                    await websocket.close()

        tasks = [asyncio.create_task(screen(index)) for index in range(count)]
        try:
            async with asyncio.timeout(60):
                opened_count = sum([await opened.get() for _ in range(count)])
            result["streams_opened"] = opened_count
            result["initial_snapshots"] = opened_count
            result["refused"] = failures
            if opened_count != count:
                raise RuntimeError(f"Only {opened_count}/{count} streams opened: {failures[:10]}")
            result["loaded_resources"] = await resources()
            result["loaded_api"] = await measure_api()
            print(json.dumps({"phase": "streams_open", **result}), flush=True)
            await asyncio.sleep(seconds)
            # A different process commits real fixture contacts and publishes
            # through Redis. Every screen must get its own event, and no other.
            async with AsyncSessionLocal() as db:
                printers = (await db.execute(select(UserPrinterDevice).where(UserPrinterDevice.id.in_(printer_ids)))).scalars().all()
                timestamp = datetime.now(timezone.utc)
                for printer in printers:
                    printer.last_seen_at = timestamp
                await db.commit()
                await publish_committed_contacts(db)
            async with asyncio.timeout(15):
                measurements = [await observed.get() for _ in range(count)]
            assert len({index for index, _ in measurements}) == count
            result["contact_latency"] = summary([latency for _, latency in measurements])
            result["steady_resources"] = await resources()
            result["steady_api"] = await measure_api()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(1)
        result["closed_resources"] = await resources()
        remaining = 0
        async for key in broker.redis.scan_iter(match=broker.lease_key(0).rsplit(":", 1)[0] + ":*"):
            remaining += await broker.redis.zcard(key)
        result["remaining_leases_all_users"] = remaining
        print(json.dumps({"phase": "complete", **result}), flush=True)
        if checks:
            await check_access(client, tokens[0])
        if auth_failure:
            await check_lost_auth_publish(client, tokens[0], printer_ids[0])
    await broker.close()


parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, default=100)
parser.add_argument("--seconds", type=int, default=35)
checks_group = parser.add_mutually_exclusive_group()
checks_group.add_argument("--checks", action="store_true")
checks_group.add_argument("--auth-failure", action="store_true")
args = parser.parse_args()
if not 1 <= args.count <= 1000 or not 1 <= args.seconds <= 60:
    parser.error("Use 1..1000 streams and a 1..60 second observation window")
asyncio.run(run(args.count, args.seconds, args.checks, args.auth_failure))
