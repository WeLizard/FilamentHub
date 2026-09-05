"""Required route issuance lock interleavings on migrated local PostgreSQL.

Fixtures are retained. No schema changes or cleanup are performed.
"""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.octoprint_bridge import OctoPrintBridgeConnection
from app.models.preset_usage_event import PresetUsageEvent
from app.models.printer_bridge_receipt import PrinterBridgeReceipt
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.schemas.material_contract import MaterialSlotAssignmentUpdate
from app.schemas.octoprint_bridge import OctoPrintBridgeUsageRequest
from app.services import material_assignment_service as assignments
from app.services import octoprint_bridge_service as bridge
from app.services.material_contract_service import build_printer_bridge_desired_snapshot
from tests.conftest import accepted_legal

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="requires FH_TEST_POSTGRES_URL pointing at migrated local dev",
    ),
]


@pytest.mark.parametrize("scenario", ["revoke", "assignment"])
async def test_snapshot_route_lock_interleavings(monkeypatch, scenario):
    engine = create_async_engine(
        POSTGRES_URL,
        connect_args={"server_settings": {"lock_timeout": "4000"}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    tasks = []
    try:
        async with sessions() as db:
            user = User(
                email=f"route-pg-{suffix}@example.com",
                username=f"route_pg_{suffix}",
                password_hash="unused",
                active=True,
                email_verified=True,
                **accepted_legal(),
            )
            db.add(user)
            await db.flush()
            printer = UserPrinterDevice(user_id=user.id, name=f"Route concurrency {suffix}")
            db.add(printer)
            await db.flush()
            system = MaterialSystem(
                user_id=user.id,
                physical_printer_id=printer.id,
                name="Route feed",
                provider="octoprint",
                kind="direct_feed",
            )
            db.add(system)
            await db.flush()
            slot = MaterialSlot(user_id=user.id, material_system_id=system.id, provider_index=0)
            connector = PhysicalPrinterConnector(
                user_id=user.id,
                physical_printer_id=printer.id,
                material_system_id=system.id,
                provider=bridge.OCTOPRINT_PROVIDER,
                transport=bridge.OCTOPRINT_TRANSPORT,
                active=True,
                capabilities=["read", "consumption"],
            )
            spools = [UserSpool(user_id=user.id, initial_weight_g=1000) for _ in range(2)]
            db.add_all([slot, connector, *spools])
            await db.flush()
            connection = OctoPrintBridgeConnection(
                connector_id=connector.id,
                instance_id=f"route-pg-{suffix}",
                token_hash=uuid4().hex * 2,
            )
            db.add(connection)
            await db.commit()
            user_id, printer_id, slot_id = user.id, printer.id, slot.id
            connector_id, connection_id = connector.id, connection.id
            spool_a_id, spool_b_id = [spool.id for spool in spools]
            source = connection.instance_id
            await assignments.update_material_slot_assignment(
                db,
                user,
                physical_printer_id=printer_id,
                material_slot_id=slot_id,
                payload=MaterialSlotAssignmentUpdate(
                    expected_revision=0, expected_spool_id=None, spool_id=spool_a_id
                ),
            )

        async def context(db):
            return bridge.OctoPrintBridgeContext(
                connection=await db.get(OctoPrintBridgeConnection, connection_id),
                connector=await db.get(PhysicalPrinterConnector, connector_id),
            )

        held, release = asyncio.Event(), asyncio.Event()
        if scenario == "revoke":
            original_lock = bridge._lock_usage_connection

            async def hold_connection(*args, **kwargs):
                result = await original_lock(*args, **kwargs)
                held.set()
                await asyncio.wait_for(release.wait(), 5)
                return result

            monkeypatch.setattr(bridge, "_lock_usage_connection", hold_connection)

            async def snapshot():
                async with sessions() as db:
                    return await bridge.build_snapshot(db, await context(db))

            revoke_started = asyncio.Event()
            revoke_pid = None

            async def revoke():
                nonlocal revoke_pid
                async with sessions() as db:
                    revoke_pid = await db.scalar(text("SELECT pg_backend_pid()"))
                    current = await context(db)
                    revoke_started.set()
                    await bridge.revoke_bridge_context(db, current)

            tasks.append(asyncio.create_task(snapshot()))
            await asyncio.wait_for(held.wait(), 5)
            tasks.append(asyncio.create_task(revoke()))
            await asyncio.wait_for(revoke_started.wait(), 5)
            async with sessions() as db:
                for _ in range(100):
                    wait = await db.scalar(
                        text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                        {"pid": revoke_pid},
                    )
                    await db.commit()
                    if wait == "Lock":
                        break
                    await asyncio.sleep(0.02)
                else:
                    pytest.fail("revocation never reached the held connection")
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), 10)
            assert results[0].slots[0].usage_route_proof
            async with sessions() as db:
                assert (
                    await db.get(OctoPrintBridgeConnection, connection_id)
                ).revoked_at is not None
                assert (await db.get(PhysicalPrinterConnector, connector_id)).active is False
        else:
            original_slot = assignments._require_material_slot

            async def hold_slot(*args, **kwargs):
                result = await original_slot(*args, **kwargs)
                held.set()
                await asyncio.wait_for(release.wait(), 5)
                return result

            monkeypatch.setattr(assignments, "_require_material_slot", hold_slot)

            async def replace():
                async with sessions() as db:
                    await assignments.update_material_slot_assignment(
                        db,
                        await db.get(User, user_id),
                        physical_printer_id=printer_id,
                        material_slot_id=slot_id,
                        payload=MaterialSlotAssignmentUpdate(
                            expected_revision=1,
                            expected_spool_id=spool_a_id,
                            spool_id=spool_b_id,
                        ),
                    )

            tasks.append(asyncio.create_task(replace()))
            await asyncio.wait_for(held.wait(), 5)
            async with sessions() as db:
                snapshot = await asyncio.wait_for(
                    build_printer_bridge_desired_snapshot(
                        db,
                        await db.get(PhysicalPrinterConnector, connector_id),
                        source_instance_id=source,
                    ),
                    3,
                )
            assert snapshot.slots[0].spool.id == spool_a_id
            release.set()
            await asyncio.wait_for(asyncio.gather(*tasks), 10)
            event = OctoPrintBridgeUsageRequest.model_validate(
                {
                    "event_id": f"delayed-{suffix}",
                    "job_id": suffix,
                    "outcome": "completed",
                    "items": [
                        {
                            "slot_index": 0,
                            "spool_id": spool_a_id,
                            "used_weight_g": 10,
                            "usage_route_proof": snapshot.slots[0].usage_route_proof,
                        }
                    ],
                }
            )
            async with sessions() as db:
                first = await bridge.record_usage_event(db, await context(db), event)
                replay = await bridge.record_usage_event(db, await context(db), event)
                assert first.consumed_weight_g == 10 and replay.deduplicated
                assert (await db.get(UserSpool, spool_a_id)).used_weight_g == 10
                assert (await db.get(UserSpool, spool_b_id)).used_weight_g == 0
                rows = list(
                    await db.scalars(
                        select(PresetUsageEvent).where(PresetUsageEvent.user_id == user_id)
                    )
                )
                assert len(rows) == 1
        async with sessions() as db:
            receipts = list(
                await db.scalars(
                    select(PrinterBridgeReceipt).where(
                        PrinterBridgeReceipt.connector_id == connector_id,
                        PrinterBridgeReceipt.receipt_kind == "usage_route",
                    )
                )
            )
            assert len(receipts) == 1
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()
