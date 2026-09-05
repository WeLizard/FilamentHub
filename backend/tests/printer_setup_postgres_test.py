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

from app.api.v1.endpoints import spool_compat
from app.core.security import device_api_key_verifier
from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.printer_bridge_credential import PrinterBridgeCredential
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.schemas.material_contract import (
    MaterialSlotAssignmentUpdate,
    MaterialSystemUpdate,
    PrinterBridgeSnapshotRequest,
)
from app.schemas.printer_bridge import PrinterBridgeHeartbeatRequest
from app.services import material_assignment_service as assignments
from app.services import material_contract_service as topology
from app.services import printer_bridge_service as bridges
from app.services import spool_service as spools
from app.services.printer_bridge_service import PrinterBridgeContext
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


async def test_nonowner_snapshot_waits_for_owner_heartbeat_before_locking_topology(monkeypatch):
    engine = create_async_engine(
        POSTGRES_URL,
        connect_args={"server_settings": {"lock_timeout": "4000"}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    owner_source = f"setup-pg-owner-{suffix}"
    incoming_source = f"setup-pg-incoming-{suffix}"
    printer_api_key = f"topology-pg-key-{suffix}"
    try:
        async with sessions() as db:
            user = User(
                email=f"topology-pg-{suffix}@example.com",
                username=f"topology_pg_{suffix}",
                password_hash="unused",
                active=True,
                email_verified=True,
                **accepted_legal(),
            )
            db.add(user)
            await db.flush()
            printer = UserPrinterDevice(
                user_id=user.id,
                name=f"Topology concurrency {suffix}",
                supports_hh=True,
                api_key=device_api_key_verifier(printer_api_key),
            )
            db.add(printer)
            await db.flush()
            system = MaterialSystem(
                user_id=user.id,
                physical_printer_id=printer.id,
                name="Concurrent feed",
                provider="happy_hare",
                kind="mmu",
            )
            db.add(system)
            await db.flush()
            slot = MaterialSlot(
                user_id=user.id,
                material_system_id=system.id,
                provider_index=0,
                kind="gate",
            )
            owner = PhysicalPrinterConnector(
                user_id=user.id,
                physical_printer_id=printer.id,
                material_system_id=system.id,
                provider="happy_hare",
                transport="edge_agent",
                source_instance_id=owner_source,
                capabilities=["read"],
                active=True,
                topology_authority=True,
                last_topology_at=datetime.now(timezone.utc),
            )
            incoming = PhysicalPrinterConnector(
                user_id=user.id,
                physical_printer_id=printer.id,
                material_system_id=system.id,
                provider="happy_hare",
                transport="orca_plugin_lan",
                source_instance_id=incoming_source,
                capabilities=["read"],
                active=True,
            )
            legacy = PhysicalPrinterConnector(
                user_id=user.id,
                physical_printer_id=printer.id,
                material_system_id=system.id,
                provider="happy_hare",
                transport="spoolman_compat",
                capabilities=["read"],
                active=True,
            )
            spool = UserSpool(user_id=user.id, initial_weight_g=1000, used_weight_g=0)
            db.add_all([slot, owner, incoming, legacy, spool])
            await db.flush()
            credential = PrinterBridgeCredential(
                connector_id=owner.id,
                token_hash=uuid4().hex + uuid4().hex,
                paired_at=datetime.now(timezone.utc),
                source_instance_id=owner_source,
            )
            db.add(credential)
            await db.commit()
            user_id = user.id
            printer_id = printer.id
            system_id = system.id
            owner_id = owner.id
            incoming_id = incoming.id
            spool_id = spool.id

        owner_connector_locked = asyncio.Event()
        release_heartbeat = asyncio.Event()
        snapshot_connector_lock_started = asyncio.Event()
        snapshot_slots_started = asyncio.Event()
        original_refresh = bridges.refresh_material_system_capabilities
        original_connector_lock = topology._lock_snapshot_connectors
        original_slot_lock = topology._lock_system_slots

        async def held_refresh(db, material_system_id):
            await db.flush()
            owner_connector_locked.set()
            await asyncio.wait_for(release_heartbeat.wait(), 5)
            await original_refresh(db, material_system_id)

        async def observed_connector_lock(*args, **kwargs):
            snapshot_connector_lock_started.set()
            return await original_connector_lock(*args, **kwargs)

        async def observed_slot_lock(*args, **kwargs):
            snapshot_slots_started.set()
            return await original_slot_lock(*args, **kwargs)

        monkeypatch.setattr(bridges, "refresh_material_system_capabilities", held_refresh)
        monkeypatch.setattr(topology, "_lock_snapshot_connectors", observed_connector_lock)
        monkeypatch.setattr(topology, "_lock_system_slots", observed_slot_lock)

        async def heartbeat():
            async with sessions() as db:
                connector = await db.get(PhysicalPrinterConnector, owner_id)
                credential = await db.scalar(
                    select(PrinterBridgeCredential).where(
                        PrinterBridgeCredential.connector_id == owner_id
                    )
                )
                assert connector is not None and credential is not None
                return await bridges.record_printer_bridge_heartbeat(
                    db,
                    PrinterBridgeContext(credential=credential, connector=connector),
                    PrinterBridgeHeartbeatRequest(
                        material_system_id=system_id,
                        provider="happy_hare",
                        transport="edge_agent",
                        source_instance_id=owner_source,
                        observed_at=datetime.now(timezone.utc),
                        capabilities=["read"],
                    ),
                )

        async def snapshot():
            async with sessions() as db:
                return await topology.ingest_printer_bridge_snapshot(
                    db,
                    user_id,
                    printer_id,
                    PrinterBridgeSnapshotRequest(
                        material_system_id=system_id,
                        provider="happy_hare",
                        transport="orca_plugin_lan",
                        source_instance_id=incoming_source,
                        observed_at=datetime.now(timezone.utc),
                        capabilities=["read"],
                        slots=[{"provider_index": 0, "kind": "gate"}],
                        slot_topology_complete=True,
                    ),
                )

        heartbeat_task = asyncio.create_task(heartbeat())
        await asyncio.wait_for(owner_connector_locked.wait(), 5)
        snapshot_task = asyncio.create_task(snapshot())
        await asyncio.wait_for(snapshot_connector_lock_started.wait(), 5)
        reached_slots_while_owner_locked = False
        try:
            await asyncio.wait_for(snapshot_slots_started.wait(), 0.25)
            reached_slots_while_owner_locked = True
        except TimeoutError:
            pass
        finally:
            release_heartbeat.set()

        heartbeat_result, snapshot_result = await asyncio.wait_for(
            asyncio.gather(heartbeat_task, snapshot_task),
            10,
        )
        assert not reached_slots_while_owner_locked
        assert heartbeat_result.accepted is True
        assert snapshot_result.accepted is True
        async with sessions() as db:
            connectors = list(
                (
                    await db.scalars(
                        select(PhysicalPrinterConnector).where(
                            PhysicalPrinterConnector.id.in_([owner_id, incoming_id])
                        )
                    )
                ).all()
            )
            authority_ids = {item.id for item in connectors if item.topology_authority}
            assert authority_ids == {owner_id}
            persisted_slot = await db.scalar(
                select(MaterialSlot).where(MaterialSlot.material_system_id == system_id)
            )
            assert persisted_slot is not None
            assert (persisted_slot.provider_index, persisted_slot.kind, persisted_slot.active) == (
                0,
                "gate",
                True,
            )

        assignment_slot_locked = asyncio.Event()
        release_assignment = asyncio.Event()
        snapshot_connector_lock_started.clear()
        snapshot_slots_started.clear()
        original_material_slot_lock = spools.lock_material_slots_for_spools

        async def held_material_slot_lock(*args, **kwargs):
            result = await original_material_slot_lock(*args, **kwargs)
            assignment_slot_locked.set()
            await asyncio.wait_for(release_assignment.wait(), 5)
            return result

        monkeypatch.setattr(spools, "lock_material_slots_for_spools", held_material_slot_lock)

        async def assign_through_spoolman_compat():
            async with sessions() as db:
                user, device = await spool_compat._resolve_user_and_device(db, printer_api_key)
                spool = await db.get(UserSpool, spool_id)
                assert user is not None and device is not None and spool is not None
                result = await spools.assign_spool_to_gate(
                    db,
                    user_id=user.id,
                    spool=spool,
                    device=device,
                    gate_index=0,
                    source=PresetGateStateSource.hh_snapshot,
                )
                await db.commit()
                return result

        assignment_task = asyncio.create_task(assign_through_spoolman_compat())
        await asyncio.wait_for(assignment_slot_locked.wait(), 5)
        snapshot_task = asyncio.create_task(snapshot())
        try:
            await asyncio.wait_for(snapshot_connector_lock_started.wait(), 5)
            await asyncio.wait_for(snapshot_slots_started.wait(), 5)
        finally:
            release_assignment.set()
        _assignment_result, snapshot_result = await asyncio.wait_for(
            asyncio.gather(assignment_task, snapshot_task),
            10,
        )
        assert snapshot_result.accepted is True
        async with sessions() as db:
            gate = await db.scalar(
                select(PresetGateState).where(
                    PresetGateState.device_id == printer_id,
                    PresetGateState.gate_index == 0,
                )
            )
            assert gate is not None and gate.spool_id == spool_id
    finally:
        await engine.dispose()
