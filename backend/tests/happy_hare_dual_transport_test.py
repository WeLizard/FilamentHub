"""Both local readers share topology, not desired assignments or LAN secrets."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import device_api_key_verifier, device_inventory_digest
from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.material_contract import PrinterBridgeSlotSnapshot, PrinterBridgeSnapshotRequest
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


def edge_snapshot(
    system_id,
    ts,
    sequence=1,
    digest=None,
    spool_id=None,
    count=4,
    capabilities=None,
):
    return PrinterBridgeSnapshotRequest(
        material_system_id=system_id,
        provider="happy_hare",
        transport="edge_agent",
        source_instance_id="edge-dual-transport",
        observed_at=ts,
        sequence=sequence,
        capabilities=capabilities,
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


async def pair_edge_ingress(
    auth_client: AsyncClient,
    *,
    printer_id: int,
    system_id: int,
) -> dict[str, str]:
    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
        params={"transport": "edge_agent"},
    )
    assert pairing.status_code == 200, pairing.text
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "happy_hare",
            "transport": "edge_agent",
            "source_instance_id": "edge-dual-http-ingress",
            "node_instance_id": "edge-dual-http-node",
            "plugin_version": "0.1.0-test",
            "capabilities": ["read", "presence"],
        },
    )
    assert paired.status_code == 200, paired.text
    return {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("first_ingress", ["edge", "orca"])
async def test_http_ingresses_keep_first_fresh_topology_owner_and_survive_failover(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
    first_ingress: str,
) -> None:
    printer, system, spool = await setup_printer(db_session, auth_user)
    edge_headers = await pair_edge_ingress(
        auth_client,
        printer_id=printer.id,
        system_id=system.id,
    )
    started_at = datetime.now(timezone.utc) - timedelta(seconds=3)

    async def post_edge(sequence: int, observed_at: datetime, material: str):
        response = await auth_client.post(
            "/api/v1/printer-bridge/snapshot",
            headers=edge_headers,
            json={
                "material_system_id": system.id,
                "provider": "happy_hare",
                "transport": "edge_agent",
                "source_instance_id": "edge-dual-http-ingress",
                "sequence": sequence,
                "observed_at": observed_at.isoformat(),
                "capabilities": ["read", "presence"],
                "slot_topology_complete": True,
                "slots": [
                    {
                        "provider_index": index,
                        "kind": "gate",
                        "present": index == 0,
                        "material": material if index == 0 else None,
                    }
                    for index in range(2)
                ],
            },
        )
        assert response.status_code == 200, response.text

    async def post_orca(observed_at: datetime, material: str):
        response = await auth_client.post(
            "/api/v1/orcaslicer/preset-slot-sync/hh/snapshot",
            json={
                "physical_printer_id": printer.id,
                "gate_count": 4,
                "snapshot_ts": observed_at.isoformat(),
                "gates": [
                    {
                        "gate": index,
                        "status": 1 if index == 0 else 0,
                        "material": material if index == 0 else "",
                    }
                    for index in range(4)
                ],
            },
        )
        assert response.status_code == 200, response.text

    if first_ingress == "edge":
        await post_edge(1, started_at, "EDGE_OWNER")
        owner_transport = "edge_agent"
        owner_source = "happy_hare_edge"
    else:
        await post_orca(started_at, "ORCA_OWNER")
        owner_transport = "orca_plugin_lan"
        owner_source = "happy_hare_moonraker"

    current = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    slot = next(
        item for item in current["material_systems"][0]["slots"] if item["provider_index"] == 0
    )
    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/material-slots/{slot['id']}",
        json={
            "expected_revision": slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": spool.id,
        },
    )
    assert assigned.status_code == 200, assigned.text

    if first_ingress == "edge":
        await post_orca(started_at + timedelta(seconds=1), "ORCA_NON_OWNER")
    else:
        await post_edge(1, started_at + timedelta(seconds=1), "EDGE_NON_OWNER")

    current = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    connectors = current["connectors"]
    authorities = [item for item in connectors if item["topology_authority"]]
    assert len(authorities) == 1
    assert authorities[0]["transport"] == owner_transport
    slots = current["material_systems"][0]["slots"]
    assert [item["provider_index"] for item in slots if item["active"]] == (
        [0, 1] if first_ingress == "edge" else [0, 1, 2, 3]
    )
    slot = next(item for item in slots if item["provider_index"] == 0)
    assert slot["assignment"]["spool_id"] == spool.id
    assert slot["observation"]["source"] == owner_source
    observations = {item["source"]: item for item in slot["observations"]}
    assert observations.keys() == {
        "happy_hare_edge",
        "happy_hare_moonraker",
    }
    non_owner_source = (
        "happy_hare_moonraker" if first_ingress == "edge" else "happy_hare_edge"
    )
    non_owner_material = "ORCA_NON_OWNER" if first_ingress == "edge" else "EDGE_NON_OWNER"
    assert observations[non_owner_source]["present"] is True
    assert observations[non_owner_source]["material"] == non_owner_material

    if first_ingress == "edge":
        revoked = await auth_client.delete(
            "/api/v1/printer-bridge/connection",
            headers=edge_headers,
        )
        assert revoked.status_code == 204, revoked.text
        await post_orca(started_at + timedelta(seconds=2), "ORCA_FAILOVER")
        next_owner_transport = "orca_plugin_lan"
        next_owner_source = "happy_hare_moonraker"
        next_owner_material = "ORCA_FAILOVER"
        expected_active_indices = [0, 1, 2, 3]
    else:
        orca_connector = await db_session.scalar(
            select(PhysicalPrinterConnector).where(
                PhysicalPrinterConnector.physical_printer_id == printer.id,
                PhysicalPrinterConnector.transport == "orca_plugin_lan",
            )
        )
        assert orca_connector is not None
        orca_connector.active = False
        await db_session.commit()
        await post_edge(2, started_at + timedelta(seconds=2), "EDGE_FAILOVER")
        next_owner_transport = "edge_agent"
        next_owner_source = "happy_hare_edge"
        next_owner_material = "EDGE_FAILOVER"
        expected_active_indices = [0, 1]

    failed_over = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    next_authorities = [
        item for item in failed_over["connectors"] if item["topology_authority"]
    ]
    assert len(next_authorities) == 1
    assert next_authorities[0]["transport"] == next_owner_transport
    assert [
        item["provider_index"]
        for item in failed_over["material_systems"][0]["slots"]
        if item["active"]
    ] == expected_active_indices
    retained = next(
        item
        for item in failed_over["material_systems"][0]["slots"]
        if item["provider_index"] == 0
    )
    assert retained["active"] is True
    assert retained["assignment"]["spool_id"] == spool.id
    assert retained["observation"]["source"] == next_owner_source
    assert retained["observation"]["material"] == next_owner_material


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
async def test_observation_fallback_uses_source_time_before_server_receipt(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    printer, system, _spool = await setup_printer(db_session, auth_user)
    db_session.add(
        MaterialSlot(
            user_id=auth_user.id,
            material_system_id=system.id,
            provider_index=0,
            kind="gate",
        )
    )
    await db_session.commit()
    now = datetime.now(timezone.utc)
    for transport, source, observed_at, material in (
        ("edge_agent", "edge-observation-clock", now - timedelta(seconds=30), "RECENT"),
        (
            "orca_plugin_lan",
            "orca-delayed-observation",
            now - timedelta(days=1),
            "DELAYED",
        ),
    ):
        result = await ingest_printer_bridge_snapshot(
            db_session,
            auth_user.id,
            printer.id,
            PrinterBridgeSnapshotRequest(
                material_system_id=system.id,
                provider="happy_hare",
                transport=transport,
                source_instance_id=source,
                observed_at=observed_at,
                slots=[
                    PrinterBridgeSlotSnapshot(
                        provider_index=0,
                        kind="gate",
                        present=True,
                        material=material,
                    )
                ],
                slot_topology_complete=False,
            ),
        )
        assert result.accepted is True

    data = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    observation = data["material_systems"][0]["slots"][0]["observation"]
    assert observation["source"] == "happy_hare_edge"
    assert observation["material"] == "RECENT"


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_loss", ["inactive", "stale"])
async def test_topology_owner_is_sticky_until_ineligible_then_fails_over(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
    owner_loss: str,
):
    printer, system, spool = await setup_printer(db_session, auth_user)
    edge_clock = datetime.now(timezone.utc) + timedelta(days=365)
    orca_clock = datetime(2001, 1, 1, tzinfo=timezone.utc)
    digest = hashlib.sha256(b"dual-transport-test-key").hexdigest()
    edge_report = edge_snapshot(
        system.id,
        edge_clock,
        digest=digest,
        spool_id=spool.id,
        count=2,
    )
    edge_report = edge_report.model_copy(
        update={
            "slots": [
                *edge_report.slots,
                PrinterBridgeSlotSnapshot(
                    provider_index=1023,
                    kind="bypass",
                    present=False,
                ),
            ]
        }
    )
    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        edge_report,
    )
    await handle_hh_snapshot(
        db_session,
        auth_user,
        HHSnapshotRequest(
            physical_printer_id=printer.id,
            gate_count=4,
            snapshot_ts=orca_clock,
            gates=[HHGateItem(gate=index, status=0) for index in range(4)],
            spool_ids=[None] * 4,
            inventory_key_digest=digest,
        ),
    )
    data = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    assert len(data["material_systems"]) == 1
    slots = data["material_systems"][0]["slots"]
    assert len(slots) == 3 and all(slot["active"] for slot in slots)
    assert data["material_systems"][0]["declared_slot_count"] == 2
    assert slots[0]["observation"]["source"] == "happy_hare_edge"
    assert slots[0]["observation"]["spool_id"] == spool.id
    assert all(slot["assignment"] is None for slot in slots)
    edge = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.physical_printer_id == printer.id,
            PhysicalPrinterConnector.transport == "edge_agent",
        )
    )
    orca = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.physical_printer_id == printer.id,
            PhysicalPrinterConnector.transport == "orca_plugin_lan",
        )
    )
    assert edge.topology_authority is True
    assert orca is not None and orca.topology_authority is False
    assert "write" not in edge.capabilities

    if owner_loss == "inactive":
        edge.active = False
    else:
        edge.last_topology_at = datetime.now(timezone.utc) - timedelta(seconds=301)
    await db_session.commit()
    await handle_hh_snapshot(
        db_session,
        auth_user,
        HHSnapshotRequest(
            physical_printer_id=printer.id,
            gate_count=4,
            snapshot_ts=orca_clock + timedelta(seconds=1),
            gates=[HHGateItem(gate=index, status=0) for index in range(4)],
            spool_ids=[None] * 4,
            inventory_key_digest=digest,
        ),
    )
    await db_session.refresh(orca)
    assert orca.topology_authority is False
    retained = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    assert len(retained["material_systems"][0]["slots"]) == 3

    await handle_hh_snapshot(
        db_session,
        auth_user,
        HHSnapshotRequest(
            physical_printer_id=printer.id,
            gate_count=4,
            snapshot_ts=datetime.now(timezone.utc),
            gates=[HHGateItem(gate=0, status=0)],
            spool_ids=[None] * 4,
            inventory_key_digest=digest,
        ),
    )
    failed_over = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    slots = failed_over["material_systems"][0]["slots"]
    assert [slot["provider_index"] for slot in slots] == [0, 1, 2, 3, 1023]
    assert all(slot["active"] for slot in slots)
    assert slots[0]["observation"]["source"] == "happy_hare_moonraker"
    assert slots[2]["observation"] is None
    await db_session.refresh(edge)
    await db_session.refresh(orca)
    assert edge.topology_authority is False
    assert orca.topology_authority is True


@pytest.mark.asyncio
async def test_non_topology_reports_preserve_owned_map_and_desired_assignment(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    printer, system, spool = await setup_printer(db_session, auth_user)
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    first = edge_snapshot(
        system.id,
        now,
        sequence=5,
        count=4,
        capabilities=["read", "presence"],
    )
    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        first,
    )
    initial = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    initial_slots = initial["material_systems"][0]["slots"]
    target = next(slot for slot in initial_slots if slot["provider_index"] == 3)
    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/material-slots/{target['id']}",
        json={
            "expected_revision": target["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": spool.id,
        },
    )
    assert assigned.status_code == 200, assigned.text
    committed = next(
        slot
        for slot in assigned.json()["material_systems"][0]["slots"]
        if slot["id"] == target["id"]
    )
    owner = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.physical_printer_id == printer.id,
            PhysicalPrinterConnector.transport == "edge_agent",
        )
    )
    assert owner is not None and owner.topology_authority is True
    topology_received_at = owner.last_topology_at

    partial = first.model_copy(
        update={
            "sequence": 6,
            "observed_at": now + timedelta(seconds=1),
            "capabilities": ["presence"],
            "slot_topology_complete": False,
            "slots": [
                first.slots[0].model_copy(
                    update={"label": "partial", "kind": "bypass", "present": False}
                )
            ],
        }
    )
    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        partial,
    )
    empty = PrinterBridgeSnapshotRequest(
        material_system_id=system.id,
        provider="happy_hare",
        transport="edge_agent",
        source_instance_id="edge-dual-transport",
        capabilities=["presence"],
        sequence=7,
        observed_at=now + timedelta(seconds=2),
        printer={"state": "idle"},
        slots=[],
        slot_topology_complete=True,
    )
    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        empty,
    )
    stale = first.model_copy(
        update={
            "sequence": 6,
            "observed_at": now + timedelta(seconds=3),
            "capabilities": ["presence"],
            "slots": [first.slots[0]],
        }
    )
    stale_result = await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        stale,
    )
    assert stale_result.stale is True

    ineligible = PrinterBridgeSnapshotRequest(
        material_system_id=system.id,
        provider="happy_hare",
        transport="orca_plugin_lan",
        source_instance_id="ineligible-orca-source",
        capabilities=["presence"],
        sequence=1,
        observed_at=now + timedelta(seconds=4),
        slot_topology_complete=True,
        slots=[{"provider_index": 9, "kind": "bypass", "present": True}],
    )
    await ingest_printer_bridge_snapshot(
        db_session,
        auth_user.id,
        printer.id,
        ineligible,
    )

    current = (await auth_client.get(f"/api/v1/physical-printers/{printer.id}")).json()
    current_slots = current["material_systems"][0]["slots"]
    assert [
        (slot["id"], slot["provider_index"], slot["kind"], slot["active"]) for slot in current_slots
    ] == [
        (slot["id"], slot["provider_index"], slot["kind"], slot["active"]) for slot in initial_slots
    ]
    retained = next(slot for slot in current_slots if slot["id"] == target["id"])
    assert current_slots[0]["observation"]["present"] is True
    assert retained["assignment"] == committed["assignment"]
    assert retained["assignment_revision"] == committed["assignment_revision"]
    await db_session.refresh(owner)
    assert owner.topology_authority is True
    assert owner.last_topology_at == topology_received_at
    assert owner.capabilities == ["read", "presence"]


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
            slot_topology_complete=True,
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
