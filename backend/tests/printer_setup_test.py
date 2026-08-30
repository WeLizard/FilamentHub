"""Onboarding retries and attaching local evidence must not multiply printers."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.material_system import MaterialSystem
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.schemas.material_contract import PrinterBridgeSnapshotRequest
from app.services.material_contract_service import ingest_printer_bridge_snapshot

pytestmark = pytest.mark.asyncio
PATH = "/api/v1/physical-printers"
SOURCE = "setup-test-desktop-instance"


def connection(**overrides):
    return {
        "source_instance_id": SOURCE, "connection_ref": "local-manual-1",
        "origin": "local_manual", "provider": "moonraker", "endpoint_token": "a" * 64,
        "device_identity": {"kind": "moonraker_instance", "token": "b" * 64},
        **overrides,
    }


async def test_creation_retry_keeps_one_printer_and_one_system(auth_client, db_session):
    payload = {
        "name": "Workshop", "request_id": str(uuid4()),
        "material_system": {"name": "External spool", "slot_count": 1},
    }
    first = await auth_client.post(PATH, json=payload)
    assert first.status_code == 201, first.text
    printer = first.json()
    assert len(printer["material_systems"][0]["slots"]) == 1
    await auth_client.patch(f"{PATH}/{printer['id']}", json={"name": "Renamed"})
    replay = await auth_client.post(PATH, json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == printer["id"]
    assert replay.json()["name"] == "Renamed"
    assert replay.json()["material_systems"] == printer["material_systems"]
    assert await db_session.scalar(select(func.count()).select_from(UserPrinterDevice)) == 1
    assert await db_session.scalar(select(func.count()).select_from(MaterialSystem)) == 1


async def test_three_explicit_identical_manual_printers_remain_three(auth_client):
    ids = set()
    for _ in range(3):
        response = await auth_client.post(PATH, json={"name": "Voron", "request_id": str(uuid4())})
        assert response.status_code == 201
        ids.add(response.json()["id"])
    assert len(ids) == 3


async def test_detaching_one_binding_does_not_block_a_bound_or_explicitly_restored_sibling(auth_client, db_session):
    created = await auth_client.post(PATH, json={"name": "Local", "connection": connection()})
    printer_id = created.json()["id"]
    setup_path = f"{PATH}/{printer_id}/connection-setup"
    sibling = connection(connection_ref="sibling")
    assert (await auth_client.post(setup_path, json={"connection": sibling})).status_code == 200
    bindings = (await db_session.scalars(select(PrinterConnectionBinding).order_by(PrinterConnectionBinding.id))).all()
    base = "/api/v1/orcaslicer/printer-connections/bindings"
    assert (await auth_client.delete(f"{base}/{bindings[0].id}", params={"physical_printer_id": printer_id})).status_code == 204
    assert (await auth_client.post(setup_path, json={"connection": sibling})).status_code == 200
    assert bindings[0].status == "detached"
    assert (await auth_client.delete(f"{base}/{bindings[1].id}", params={"physical_printer_id": printer_id})).status_code == 204
    assert (await auth_client.patch(f"{base}/{bindings[1].id}", json={"physical_printer_id": printer_id})).status_code == 204
    assert (await auth_client.post(setup_path, json={"connection": sibling})).status_code == 200
    assert bindings[0].status == "detached"
    assert (await auth_client.post(setup_path, json={"connection": connection(connection_ref="new-alias")})).status_code == 409


async def test_detached_connection_cannot_be_restored_by_setup_or_endpoint_alias(auth_client, db_session):
    payload = {"name": "Workshop", "request_id": str(uuid4()), "connection": connection()}
    created = await auth_client.post(PATH, json=payload)
    assert created.status_code == 201, created.text
    printer = created.json()
    binding = await db_session.scalar(select(PrinterConnectionBinding))
    response = await auth_client.delete(f"/api/v1/orcaslicer/printer-connections/bindings/{binding.id}",
                                        params={"physical_printer_id": printer["id"]})
    assert response.status_code == 204
    for ref in (connection()["connection_ref"], "stale-alias"):
        response = await auth_client.post(f"{PATH}/{printer['id']}/connection-setup",
                                          json={"request_id": str(uuid4()), "connection": connection(connection_ref=ref)})
        assert response.status_code == 409, response.text
    replay = await auth_client.post(PATH, json=payload)
    assert replay.status_code in {201, 409}
    await db_session.refresh(binding)
    assert binding.status == "detached"
    assert await db_session.scalar(select(func.count()).select_from(UserPrinterDevice)) == 1


async def test_manual_topology_preserves_external_spool_and_rejects_stale_or_occupied_edits(
    auth_client, db_session, auth_user,
):
    routes = [{"provider_index": i, "kind": "gate"} for i in range(4)]
    routes.append({"provider_index": 1023, "kind": "bypass"})
    created = (await auth_client.post(PATH, json={"name": "Manual HH", "material_system": {
        "name": "HH", "provider": "happy_hare", "kind": "mmu", "slots": routes,
    }})).json()
    system = created["material_systems"][0]
    bypass = next(slot for slot in system["slots"] if slot["provider_index"] == 1023)
    spool = UserSpool(user_id=auth_user.id, initial_weight_g=1000, used_weight_g=123)
    db_session.add(spool)
    await db_session.commit()
    assigned = await auth_client.patch(f"{PATH}/{created['id']}/material-slots/{bypass['id']}", json={
        "spool_id": spool.id, "expected_spool_id": None, "expected_revision": 0,
    })
    assert assigned.status_code == 200, assigned.text
    path = f"{PATH}/{created['id']}/material-systems/{system['id']}"
    resized = await auth_client.patch(path, json={"slot_count": 8})
    assert resized.status_code == 200, resized.text
    current = resized.json()["material_systems"][0]
    assert len(current["slots"]) == 9
    actual = next(slot for slot in current["slots"] if slot["id"] == bypass["id"])
    assert actual["kind"] == "bypass" and actual["assignment"]["spool_id"] == spool.id
    expected = [{"material_slot_id": slot["id"], "expected_revision": slot["assignment_revision"],
                 "expected_spool_id": slot["assignment"]["spool_id"] if slot["assignment"] else None}
                for slot in current["slots"]]
    ordinary = [{"provider_index": i, "kind": "gate"} for i in range(8)]
    refused = await auth_client.patch(path, json={"slots": ordinary, "expected_slots": expected})
    assert refused.status_code == 409 and "ERR_MATERIAL_SLOT_IN_USE" in refused.text
    stale = [{**item, "expected_revision": item["expected_revision"] + 1} for item in expected]
    refused = await auth_client.patch(path, json={"slots": routes, "expected_slots": stale})
    assert refused.status_code == 409 and "ERR_MATERIAL_ASSIGNMENT_CONFLICT" in refused.text
    # Explicitly reducing only the empty ordinary gates leaves the bypass in place.
    payload = {"slots": routes, "expected_slots": expected, "kind": "mmu"}
    changed = await auth_client.patch(path, json=payload)
    assert changed.status_code == 200, changed.text
    replay = await auth_client.patch(path, json=payload)
    assert replay.status_code == 200 and replay.json() == changed.json()
    await db_session.refresh(spool)
    assert spool.used_weight_g == 123


async def test_existing_manual_printer_adopts_native_connection_without_recreating_slots(auth_client):
    created = (await auth_client.post(PATH, json={"name": "Octo machine", "material_system": {
        "name": "External", "kind": "direct_feed", "slots": [{"provider_index": 0, "kind": "external"}],
    }})).json()
    system = created["material_systems"][0]
    slot = system["slots"][0]
    payload = {"material_system_id": system["id"], "material_system_update": {
        "provider": "octoprint", "kind": "direct_feed", "slots": [{"provider_index": 0, "kind": "external"}],
        "expected_slots": [{"material_slot_id": slot["id"], "expected_revision": 0, "expected_spool_id": None}],
    }}
    response = await auth_client.post(f"{PATH}/{created['id']}/connection-setup", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()["material_systems"][0]
    assert result["id"] == system["id"] and result["provider"] == "octoprint"
    assert result["slots"][0]["id"] == slot["id"]
    replay = await auth_client.post(f"{PATH}/{created['id']}/connection-setup", json=payload)
    assert replay.status_code == 200 and replay.json() == response.json()
    payload["material_system_update"]["name"] = "Named Octo feed"
    renamed = await auth_client.post(f"{PATH}/{created['id']}/connection-setup", json=payload)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["material_systems"][0]["name"] == "Named Octo feed"


@pytest.mark.parametrize(("path", "route_kind"), [
    (path, kind) for path in ("edit", "legacy", "bridge") for kind in ("slot", "external")
] + [("partial_bridge", "slot")])
async def test_occupied_single_spool_is_never_reinterpreted_as_gate_zero(
    auth_client, db_session, auth_user, route_kind, path,
):
    created = (await auth_client.post(PATH, json={"name": "Single spool", "material_system": {
        "name": "Spool", "slots": [{"provider_index": 0, "kind": route_kind}],
    }})).json()
    printer_id, system = created["id"], created["material_systems"][0]
    slot = system["slots"][0]
    user_id = auth_user.id
    spool = UserSpool(user_id=user_id, initial_weight_g=1000, used_weight_g=123)
    db_session.add(spool)
    await db_session.commit()
    spool_id = spool.id
    assigned = await auth_client.patch(f"{PATH}/{printer_id}/material-slots/{slot['id']}", json={
        "spool_id": spool_id, "expected_spool_id": None, "expected_revision": 0,
    })
    assert assigned.status_code == 200, assigned.text
    if path == "edit":
        response = await auth_client.patch(f"{PATH}/{printer_id}/material-systems/{system['id']}", json={
            "kind": "mmu", "slots": [{"provider_index": 0, "kind": "gate"}],
            "expected_slots": [{"material_slot_id": slot["id"], "expected_spool_id": spool_id, "expected_revision": 1}],
        })
    elif path == "legacy":
        response = await auth_client.post('/api/v1/orcaslicer/preset-slot-sync/hh/snapshot', json={
            "physical_printer_id": printer_id, "gate_count": 4,
            "snapshot_ts": datetime.now(timezone.utc).isoformat(),
            "gates": [{"gate": index, "status": 0} for index in range(4)],
        })
    else:
        with pytest.raises(HTTPException) as error:
            await ingest_printer_bridge_snapshot(db_session, user_id, printer_id, PrinterBridgeSnapshotRequest(
                material_system_id=system["id"], provider="happy_hare", transport="orca_plugin_lan",
                source_instance_id="test-route-reinterpretation", observed_at=datetime.now(timezone.utc),
                slots=[{"provider_index": 1 if path == "partial_bridge" else 0, "kind": "gate"}],
                slot_topology_complete=path != "partial_bridge",
            ))
        assert error.value.status_code == 409 and "ERR_MATERIAL_SLOT_IN_USE" in str(error.value.detail)
    if path in {"edit", "legacy"}:
        assert response.status_code == 409 and "ERR_MATERIAL_SLOT_IN_USE" in response.text
    await db_session.rollback()
    final = (await auth_client.get(f"{PATH}/{printer_id}")).json()["material_systems"][0]
    assert final["id"] == system["id"] and final["kind"] == "direct_feed"
    assert final["slots"][0]["id"] == slot["id"] and final["slots"][0]["kind"] == route_kind
    assert final["slots"][0]["assignment"]["spool_id"] == spool_id
    await db_session.refresh(spool)
    assert spool.used_weight_g == 123


async def test_provider_topology_change_invalidates_open_editor(auth_client, db_session, auth_user):
    created = (await auth_client.post(PATH, json={"name": "Open editor", "material_system": {
        "name": "Slots", "kind": "mmu", "slot_count": 2,
    }})).json()
    system = created["material_systems"][0]
    await ingest_printer_bridge_snapshot(db_session, auth_user.id, created["id"], PrinterBridgeSnapshotRequest(
        material_system_id=system["id"], provider="happy_hare", transport="orca_plugin_lan",
        source_instance_id="test-route-editor-revision", observed_at=datetime.now(timezone.utc),
        slots=[{"provider_index": 0, "kind": "gate"}], slot_topology_complete=True,
    ))
    response = await auth_client.patch(f"{PATH}/{created['id']}/material-systems/{system['id']}", json={
        "slots": [{"provider_index": index, "kind": "slot"} for index in range(2)],
        "expected_slots": [{"material_slot_id": item["id"], "expected_spool_id": None, "expected_revision": 0}
                           for item in system["slots"]],
    })
    assert response.status_code == 409 and "ERR_MATERIAL_ASSIGNMENT_CONFLICT" in response.text


async def test_manual_direct_connection_can_be_revoked_before_first_snapshot(auth_client):
    created = (await auth_client.post(PATH, json={"name": "Not observed", "material_system": {
        "name": "External spool", "slot_count": 1,
    }})).json()
    path = f"/api/v1/printer-bridge/connections/{created['id']}/{created['material_systems'][0]['id']}"
    code = await auth_client.post(path + "/pairing-code", params={"transport": "edge_agent"})
    paired = await auth_client.post("/api/v1/printer-bridge/pair", json={
        "pairing_code": code.json()["pairing_code"], "provider": "legacy", "transport": "edge_agent",
        "source_instance_id": "not-observed-connection", "node_instance_id": "not-observed-node",
        "plugin_version": "0.1.0-test",
    })
    assert paired.status_code == 200, paired.text
    headers = {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]}
    assert (await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)).status_code == 200
    revoked = await auth_client.delete(path, params={"transport": "edge_agent"})
    assert revoked.status_code == 204, revoked.text
    assert (await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)).status_code == 401


async def test_attach_and_reconnect_preserve_existing_manual_slots(auth_client, db_session):
    created = (await auth_client.post(PATH, json={
        "name": "My printer", "material_system": {"name": "Manual MMU", "slot_count": 4},
    })).json()
    system = created["material_systems"][0]
    attached = await auth_client.post(f"{PATH}/{created['id']}/connection-setup", json={
        "connection": connection(),
        "material_system": {"name": "Happy Hare", "provider": "happy_hare", "kind": "mmu"},
    })
    assert attached.status_code == 200, attached.text
    assert attached.json()["material_systems"][0] == system
    # Starting from Add again with the same connection resumes, never duplicates.
    again = await auth_client.post(PATH, json={
        "name": "Another label", "request_id": str(uuid4()), "connection": connection(),
    })
    assert again.status_code == 201, again.text
    assert again.json()["id"] == created["id"]
    assert again.json()["name"] == "My printer"
    assert await db_session.scalar(select(func.count()).select_from(PrinterConnectionBinding)) == 1


async def test_first_hh_observation_keeps_manual_spool_and_slot_identity(
    auth_client, db_session, auth_user,
):
    from datetime import datetime, timezone

    created = (await auth_client.post(PATH, json={
        "name": "Loaded manual printer", "material_system": {"name": "MMU", "slot_count": 4},
    })).json()
    system = created["material_systems"][0]
    slot = system["slots"][0]
    spool = UserSpool(user_id=auth_user.id, initial_weight_g=1000, used_weight_g=123)
    db_session.add(spool)
    await db_session.commit()
    assigned = await auth_client.patch(f"{PATH}/{created['id']}/material-slots/{slot['id']}", json={
        "spool_id": spool.id, "expected_spool_id": None, "expected_revision": 0,
    })
    assert assigned.status_code == 200, assigned.text
    attached = await auth_client.post(f"{PATH}/{created['id']}/connection-setup", json={
        "connection": connection(),
    })
    assert attached.status_code == 200
    observed = await auth_client.post('/api/v1/orcaslicer/preset-slot-sync/hh/snapshot', json={
        "physical_printer_id": created["id"], "gate_count": 4,
        "snapshot_ts": datetime.now(timezone.utc).isoformat(),
        "gates": [{"gate": index, "status": 0} for index in range(4)],
        "spool_ids": [None, None, None, None],
    })
    assert observed.status_code == 200, observed.text
    final = (await auth_client.get(f"{PATH}/{created['id']}")).json()["material_systems"][0]
    assert final["id"] == system["id"] and final["provider"] == "happy_hare"
    actual_slot = next(item for item in final["slots"] if item["id"] == slot["id"])
    assert actual_slot["assignment"]["spool_id"] == spool.id
    await db_session.refresh(spool)
    assert spool.used_weight_g == 123


async def test_cannot_steal_a_connection_from_another_card(auth_client, db_session):
    first = (await auth_client.post(PATH, json={"name": "First", "connection": connection()})).json()
    second = (await auth_client.post(PATH, json={"name": "Second"})).json()
    rejected = await auth_client.post(f"{PATH}/{second['id']}/connection-setup", json={
        "connection": connection(), "material_system": {"name": "Must not be created"},
    })
    assert rejected.status_code == 409
    binding = await db_session.scalar(select(PrinterConnectionBinding))
    assert binding.physical_printer_id == first["id"]
    assert await db_session.scalar(select(func.count()).select_from(MaterialSystem)) == 0


async def test_local_manual_connection_not_retired_by_orca_inventory(auth_client, db_session):
    await auth_client.post(PATH, json={"name": "Local", "connection": connection()})
    response = await auth_client.post("/api/v1/orcaslicer/printer-connections/observe", json={
        "source_instance_id": SOURCE, "observations": [], "snapshot_complete": True,
    })
    assert response.status_code == 200, response.text
    binding = await db_session.scalar(select(PrinterConnectionBinding))
    assert binding.status == "bound" and binding.source == "local_setup"


async def test_context_is_scoped_and_contains_no_local_secrets(auth_client):
    await auth_client.post(PATH, json={"name": "Local", "connection": connection()})
    path = "/api/v1/orcaslicer/printer-connections/setup-context"
    response = await auth_client.get(path, params={"source_instance_id": SOURCE})
    assert response.status_code == 200, response.text
    assert len(response.json()["discovery_key"]) == 64
    assert len(response.json()["bindings"]) == 1
    assert set(response.json()["bindings"][0]) == {"connection_ref", "physical_printer_id", "status", "inventory_key_digest"}
    other = await auth_client.get(path, params={"source_instance_id": "other-desktop-instance"})
    assert other.json()["bindings"] == []
    assert other.json()["discovery_key"] == response.json()["discovery_key"]
    assert (await auth_client.get(path, params={"source_instance_id": "x"})).status_code == 422


async def test_setup_context_exposes_only_inventory_digest_for_the_bound_printer(auth_client, db_session):
    from app.core.security import device_api_key_verifier, device_inventory_digest

    created = await auth_client.post(PATH, json={"name": "Local", "connection": connection()})
    printer = await db_session.get(UserPrinterDevice, created.json()["id"])
    printer.api_key = device_api_key_verifier("fh_device_local-test-only")
    await db_session.commit()
    response = await auth_client.get("/api/v1/orcaslicer/printer-connections/setup-context",
                                     params={"source_instance_id": SOURCE})
    assert response.status_code == 200
    assert response.json()["bindings"][0]["inventory_key_digest"] == device_inventory_digest(printer.api_key)
    assert "fh_device_local-test-only" not in response.text and printer.api_key not in response.text


async def test_connection_setup_requires_ownership(auth_client, db_session, admin_user):
    foreign = UserPrinterDevice(user_id=admin_user.id, name="Private")
    db_session.add(foreign)
    await db_session.commit()
    response = await auth_client.post(f"{PATH}/{foreign.id}/connection-setup", json={
        "connection": connection(),
    })
    assert response.status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(PrinterConnectionBinding)) == 0
