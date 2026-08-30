"""Real row-lock proofs for onboarding while a person assigns a spool.

Uses an explicitly supplied, migrated local test database. Created evidence is
retained; this test never creates/drops schema or cleans another task's data.
"""

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.material_system import MaterialSlot, MaterialSystem
from app.models.preset_gate_state import PresetGateStateSource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.schemas.material_contract import (
    MaterialSlotAssignmentUpdate,
    MaterialSystemUpdate,
    PrinterBridgeSnapshotRequest,
)
from app.services import material_assignment_service as assignments
from app.services import material_contract_service as topology
from tests.conftest import accepted_legal

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not POSTGRES_URL, reason="requires FH_TEST_POSTGRES_URL pointing at migrated local dev",
)]


@pytest.mark.parametrize("scenario", ["first_snapshot", "sparse_edit"])
async def test_assignment_and_topology_do_not_deadlock_or_reinterpret_spools(monkeypatch, scenario):
    engine = create_async_engine(POSTGRES_URL, connect_args={"server_settings": {"lock_timeout": "4000"}})
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    try:
        async with sessions() as db:
            user = User(email=f"setup-pg-{suffix}@example.com", username=f"setup_pg_{suffix}",
                        password_hash="unused", active=True, email_verified=True, **accepted_legal())
            db.add(user)
            await db.flush()
            printer = UserPrinterDevice(user_id=user.id, name=f"Setup concurrency {suffix}",
                                        supports_hh=scenario == "sparse_edit")
            db.add(printer)
            await db.flush()
            system = MaterialSystem(user_id=user.id, physical_printer_id=printer.id, name="Test feed",
                                    provider="happy_hare" if scenario == "sparse_edit" else "manual",
                                    kind="mmu" if scenario == "sparse_edit" else "direct_feed")
            db.add(system)
            await db.flush()
            indices = [0, 2] if scenario == "sparse_edit" else [0]
            slots = [MaterialSlot(user_id=user.id, material_system_id=system.id,
                                  provider_index=index, kind="slot") for index in indices]
            spool = UserSpool(user_id=user.id, initial_weight_g=1000, used_weight_g=123)
            db.add_all([*slots, spool])
            await db.commit()
            user_id, printer_id, system_id, spool_id = user.id, printer.id, system.id, spool.id
            target_id, first_id = slots[-1].id, slots[0].id
            expected = [{"material_slot_id": slot.id, "expected_revision": 0, "expected_spool_id": None}
                        for slot in slots]

        assignment_locked, topology_started, continue_assignment = asyncio.Event(), asyncio.Event(), asyncio.Event()
        original_slot = assignments._require_material_slot
        original_map = topology._lock_system_slots

        async def held_slot(*args, **kwargs):
            result = await original_slot(*args, **kwargs)
            assignment_locked.set()
            await asyncio.wait_for(continue_assignment.wait(), 5)
            return result

        async def locking_map(*args, **kwargs):
            topology_started.set()
            return await original_map(*args, **kwargs)

        monkeypatch.setattr(assignments, "_require_material_slot", held_slot)
        monkeypatch.setattr(topology, "_lock_system_slots", locking_map)

        async def assign():
            async with sessions() as db:
                user = await db.get(User, user_id)
                await assignments.update_material_slot_assignment(
                    db, user, physical_printer_id=printer_id, material_slot_id=target_id,
                    payload=MaterialSlotAssignmentUpdate(expected_revision=0, expected_spool_id=None, spool_id=spool_id),
                    source=PresetGateStateSource.web_manual,
                )

        async def change():
            async with sessions() as db:
                if scenario == "sparse_edit":
                    # Reproduce the point where ordered map locking owns slot0
                    # and is about to wait for the user's target slot2.
                    await db.execute(select(MaterialSlot.id).where(MaterialSlot.id == first_id).with_for_update())
                try:
                    if scenario == "first_snapshot":
                        await topology.ingest_printer_bridge_snapshot(db, user_id, printer_id, PrinterBridgeSnapshotRequest(
                            material_system_id=system_id, provider="happy_hare", transport="orca_plugin_lan",
                            source_instance_id=f"setup-pg-{suffix}", observed_at=datetime.now(timezone.utc),
                            slots=[{"provider_index": 0, "kind": "gate"}], slot_topology_complete=True,
                        ))
                    else:
                        await topology.update_material_system(db, user_id, printer_id, system_id, MaterialSystemUpdate(
                            slots=[{"provider_index": index, "kind": "slot"} for index in range(3)],
                            expected_slots=expected,
                        ))
                except HTTPException as error:
                    await db.rollback()
                    assert error.status_code == 409
                    assert ("ERR_MATERIAL_SLOT_IN_USE" if scenario == "first_snapshot"
                            else "ERR_MATERIAL_ASSIGNMENT_CONFLICT") in str(error.detail)
                else:
                    pytest.fail("a concurrent assignment must invalidate the topology change")

        assignment = asyncio.create_task(assign())
        await asyncio.wait_for(assignment_locked.wait(), 5)
        changing = asyncio.create_task(change())
        await asyncio.wait_for(topology_started.wait(), 5)
        continue_assignment.set()
        await asyncio.wait_for(asyncio.gather(assignment, changing), 10)
        async with sessions() as db:
            printer = await topology.require_physical_printer(db, user_id, printer_id)
            final = printer.material_systems[0]
            assert sorted(slot.provider_index for slot in final.slots) == indices
            actual = next(slot for slot in final.slots if slot.id == target_id)
            assert actual.assignment.spool_id == spool_id and actual.kind == "slot"
            assert (await db.get(UserSpool, spool_id)).used_weight_g == 123
    finally:
        await engine.dispose()
