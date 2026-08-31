"""Both local readers share topology, not desired assignments or LAN secrets."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import device_api_key_verifier, device_inventory_digest
from app.models.material_system import MaterialSystem, PhysicalPrinterConnector
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.material_contract import PrinterBridgeSnapshotRequest
from app.schemas.preset_slot_sync import HHGateItem, HHSnapshotRequest
from app.services.material_contract_service import (
    ensure_material_topology,
    ingest_printer_bridge_snapshot,
)
from app.services.preset_slot_sync_service import handle_hh_snapshot
from app.services.spool_tag_service import link_spool_tag


async def setup_printer(db: AsyncSession, user: User):
    printer = UserPrinterDevice(
        user_id=user.id,
        name="Dual connection",
        supports_hh=True,
        api_key=device_api_key_verifier("dual-transport-test-key"),
    )
    spool = UserSpool(
        user_id=user.id,
        state=UserSpoolState.shelf,
        source="manual",
        initial_weight_g=1000,
        used_weight_g=0,
    )
    db.add_all([printer, spool])
    await db.flush()
    await ensure_material_topology(db, printer)
    await db.commit()
    system = await db.scalar(
        select(MaterialSystem).where(MaterialSystem.physical_printer_id == printer.id)
    )
    return printer, system, spool


def test_inventory_identity_survives_key_verifier_migration():
    key = "local-test-device-key"
    expected = hashlib.sha256(key.encode()).hexdigest()
    assert device_inventory_digest(key) == expected
    assert device_inventory_digest(device_api_key_verifier(key)) == expected
    assert device_inventory_digest(None) is None
    assert device_inventory_digest("fhk1:invalid") is None


def edge_snapshot(system_id, ts, sequence=1, digest=None, spool_id=None, count=4):
    return PrinterBridgeSnapshotRequest(
        material_system_id=system_id,
        provider="happy_hare",
        transport="edge_agent",
        source_instance_id="edge-dual-transport",
        observed_at=ts,
        sequence=sequence,
        inventory_key_digest=digest,
        slot_topology_complete=True,
        slots=[
            {
                "provider_index": index,
                "kind": "gate",
                "present": index < 2,
                "spool_identity_known": True,
                "spool_id": spool_id if index == 0 else None,
            }
            for index in range(count)
        ],
    )


@pytest.mark.asyncio
async def test_no_orca_reads_all_gates_and_only_proven_owned_spool_ids(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    printer, system, spool = await setup_printer(db_session, auth_user)
    ts = datetime.now(timezone.utc) - timedelta(seconds=30)
    digest = hashlib.sha256(b"dual-transport-test-key").hexdigest()
    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        edge_snapshot(system.id, ts, digest=digest, spool_id=spool.id),
    )
    response = await auth_client.get(f"/api/v1/physical-printers/{printer.id}")
    assert response.status_code == 200, response.text
    data = response.json()
    slots = data["material_systems"][0]["slots"]
    assert len(slots) == 4 and all(slot["active"] for slot in slots)
    assert data["material_systems"][0]["declared_slot_count"] == 4
    assert all(slot["assignment"] is None for slot in slots)
    assert slots[0]["observation"]["spool_id"] == spool.id
    assert slots[1]["observation"]["spool_identity_known"] is True
    assert slots[1]["observation"]["spool_id"] is None
    assert slots[1]["observation"]["present"] is True
    assert slots[2]["observation"]["present"] is False

    for sequence, reported, proof in ((2, spool.id, "0" * 64), (3, spool.id + 1000, digest)):
        await ingest_printer_bridge_snapshot(
            db_session,
            auth_user.id,
            printer.id,
            edge_snapshot(system.id, ts + timedelta(seconds=sequence), sequence, proof, reported),
        )
        data = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
        observed = data["material_systems"][0]["slots"][0]["observation"]
        assert observed["spool_id"] is None and observed["spool_identity_known"] is False


@pytest.mark.asyncio
async def test_orca_and_edge_share_slots_and_delayed_source_cannot_shrink_topology(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    printer, system, spool = await setup_printer(db_session, auth_user)
    ts = datetime.now(timezone.utc) - timedelta(seconds=60)
    digest = hashlib.sha256(b"dual-transport-test-key").hexdigest()
    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        edge_snapshot(system.id, ts, digest=digest, spool_id=spool.id),
    )
    await handle_hh_snapshot(
        db_session,
        auth_user,
        HHSnapshotRequest(
            physical_printer_id=printer.id,
            gate_count=4,
            snapshot_ts=ts + timedelta(seconds=20),
            gates=[HHGateItem(gate=index, status=0) for index in range(4)],
            spool_ids=[None] * 4,
            inventory_key_digest=digest,
        ),
    )
    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        edge_snapshot(system.id, ts + timedelta(seconds=10), 2, digest, spool.id, count=2),
    )
    data = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    assert len(data["material_systems"]) == 1
    slots = data["material_systems"][0]["slots"]
    assert len(slots) == 4 and all(slot["active"] for slot in slots)
    assert data["material_systems"][0]["declared_slot_count"] == 4
    assert slots[0]["observation"]["source"] == "happy_hare_moonraker"
    assert slots[0]["observation"]["present"] is False
    assert all(slot["assignment"] is None for slot in slots)
    edge = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.physical_printer_id == printer.id,
            PhysicalPrinterConnector.transport == "edge_agent",
        )
    )
    assert "write" not in edge.capabilities


@pytest.mark.asyncio
async def test_edge_discovered_gate_assignment_reaches_native_spoolman(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    printer, system, spool = await setup_printer(db_session, auth_user)
    printer_id, spool_id = printer.id, spool.id
    ts = datetime.now(timezone.utc) - timedelta(seconds=5)
    await ingest_printer_bridge_snapshot(
        db_session, auth_user.id, printer_id, edge_snapshot(system.id, ts)
    )
    data = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    slot = data["material_systems"][0]["slots"][3]
    response = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slot['id']}",
        json={
            "expected_revision": slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": spool_id,
        },
    )
    assert response.status_code == 200, response.text
    contact = await auth_client.get(
        "/api/v1/spool_compat/dual-transport-test-key/v1/spool",
        headers={"X-Printer-Name": "dual-native-client"},
    )
    assert contact.status_code == 200
    native = await auth_client.get(
        f"/api/v1/spool_compat/dual-transport-test-key/v1/spool/{spool_id}",
        headers={"X-Printer-Name": "dual-native-client"},
    )
    assert native.status_code == 200, native.text
    assert native.json()["extra"]["mmu_gate_map"] == "3"
    assert native.json()["extra"]["printer_name"] == '"dual-native-client"'
    # A disappearing gate must not strand a desired assignment out of view.
    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer_id,
        edge_snapshot(system.id, datetime.now(timezone.utc), sequence=2, count=1),
    )
    data = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    retained = next(s for s in data["material_systems"][0]["slots"] if s["provider_index"] == 3)
    assert retained["active"] and retained["assignment"]["spool_id"] == spool_id


@pytest.mark.asyncio
async def test_any_bridge_provider_resolves_tags_without_changing_desired_assignment(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer, system, tagged_spool = await setup_printer(db_session, auth_user)
    conflicting_spool = UserSpool(
        user_id=auth_user.id,
        state=UserSpoolState.shelf,
        source="manual",
        initial_weight_g=1000,
        used_weight_g=0,
    )
    db_session.add(conflicting_spool)
    await db_session.flush()
    linked = await link_spool_tag(
        db_session,
        user_id=auth_user.id,
        spool_id=tagged_spool.id,
        uid="04A1B2C3",
        technology="nfc",
        tag_format="ntag-215",
        source="user",
    )
    assert linked is not None
    await db_session.commit()

    digest = hashlib.sha256(b"dual-transport-test-key").hexdigest()

    def tagged_snapshot(sequence: int, uid: str, spool_id: int | None = None):
        return PrinterBridgeSnapshotRequest(
            material_system_id=system.id,
            provider="happy_hare",
            transport="edge_agent",
            source_instance_id="edge-dual-transport",
            observed_at=datetime.now(timezone.utc) + timedelta(seconds=sequence),
            sequence=sequence,
            capabilities=["read", "presence", "tag_read"],
            inventory_key_digest=digest,
            slots=[
                {
                    "provider_index": 0,
                    "kind": "gate",
                    "present": True,
                    "spool_identity_known": spool_id is not None,
                    "spool_id": spool_id,
                    "tag_uid": uid,
                    "tag_technology": "nfc",
                    "tag_format": "ntag-215",
                }
            ],
        )

    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        tagged_snapshot(1, "04A1B2C3"),
    )
    matched = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    matched_slot = matched["material_systems"][0]["slots"][0]
    assert matched_slot["assignment"] is None
    assert matched_slot["observation"]["spool_id"] == tagged_spool.id
    assert matched_slot["observation"]["spool_identity_known"] is True
    assert matched_slot["observation"]["tag_uid"] == "04A1B2C3"
    assert matched_slot["observation"]["tag_match_status"] == "matched"
    edge_connector = next(
        connector
        for connector in matched["connectors"]
        if connector["transport"] == "edge_agent"
    )
    assert "tag_read" in edge_connector["capabilities"]

    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        tagged_snapshot(2, "04A1B2C3", conflicting_spool.id),
    )
    conflicted = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    conflict_slot = conflicted["material_systems"][0]["slots"][0]
    assert conflict_slot["assignment"] is None
    assert conflict_slot["observation"]["spool_id"] is None
    assert conflict_slot["observation"]["spool_identity_known"] is False
    assert conflict_slot["observation"]["tag_match_status"] == "conflict"

    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        tagged_snapshot(3, "DEADBEEF"),
    )
    unknown = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    unknown_slot = unknown["material_systems"][0]["slots"][0]
    assert unknown_slot["assignment"] is None
    assert unknown_slot["observation"]["spool_id"] is None
    assert unknown_slot["observation"]["tag_match_status"] == "unlinked"
