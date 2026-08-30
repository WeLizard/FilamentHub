"""A local node groups connections, but never grants rights between them."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.material_system import MaterialSystem, PhysicalPrinterConnector
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.printer_bridge import PrinterBridgePairRequest


@pytest.mark.parametrize(
    ("transport", "node_id", "valid"),
    [
        ("edge_agent", "edge-node-contract-0001", True),
        ("edge_agent", None, False),
        ("orca_plugin_lan", None, True),
        ("orca_plugin_lan", "edge-node-contract-0001", False),
    ],
)
def test_node_identity_is_required_only_for_edge(transport, node_id, valid):
    payload = {
        "pairing_code": "FH-ABCDE-12345",
        "provider": "happy_hare",
        "transport": transport,
        "source_instance_id": "connection-lifecycle-0001",
        "node_instance_id": node_id,
        "plugin_version": "0.1.0-test",
    }
    if valid:
        assert PrinterBridgePairRequest.model_validate(payload).node_instance_id == node_id
    else:
        with pytest.raises(ValidationError):
            PrinterBridgePairRequest.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [2, 10])
async def test_one_node_keeps_printer_identity_authorization_and_revoke_separate(
    auth_client,
    auth_user,
    db_session,
    count,
):
    node_id = "edge-shared-node-000001"
    connections = []
    for index in range(count):
        printer = await auth_client.post(
            "/api/v1/physical-printers", json={"name": f"Node printer {index}"}
        )
        assert printer.status_code == 201, printer.text
        printer_id = printer.json()["id"]
        provider = "happy_hare" if index % 2 else "manual"
        response = await auth_client.post(
            f"/api/v1/physical-printers/{printer_id}/material-systems",
            json={
                "name": f"Node feed {index}",
                "kind": "mmu" if index % 2 else "direct_feed",
                "provider": provider,
                "slot_count": 1,
            },
        )
        assert response.status_code == 201, response.text
        system = response.json()["material_systems"][0]
        system_id = system["id"]
        slot = system["slots"][0]
        spool = UserSpool(
            user_id=auth_user.id,
            initial_weight_g=1000,
            used_weight_g=0,
            state=UserSpoolState.shelf,
            source="manual",
        )
        db_session.add(spool)
        await db_session.commit()
        assigned = await auth_client.patch(
            f"/api/v1/physical-printers/{printer_id}/material-slots/{slot['id']}",
            json={
                "expected_revision": slot["assignment_revision"],
                "expected_spool_id": None,
                "spool_id": spool.id,
            },
        )
        assert assigned.status_code == 200, assigned.text
        path = f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}"
        status = await auth_client.get(path, params={"transport": "edge_agent"})
        assert status.status_code == 200
        assert status.json()["provider"] == ("happy_hare" if index % 2 else "legacy")
        code = await auth_client.post(path + "/pairing-code", params={"transport": "edge_agent"})
        pair = await auth_client.post(
            "/api/v1/printer-bridge/pair",
            json={
                "pairing_code": code.json()["pairing_code"],
                "provider": status.json()["provider"],
                "transport": "edge_agent",
                "source_instance_id": f"edge-connection-{index:08d}",
                "node_instance_id": node_id,
                "plugin_version": "0.1.0-test",
                "capabilities": ["read"],
            },
        )
        assert pair.status_code == 200, pair.text
        headers = {"X-FilamentHub-Bridge-Token": pair.json()["bridge_token"]}
        context = {
            "material_system_id": system_id,
            "provider": status.json()["provider"],
            "transport": "edge_agent",
            "source_instance_id": f"edge-connection-{index:08d}",
        }
        observed = await auth_client.post(
            "/api/v1/printer-bridge/snapshot",
            headers=headers,
            json={
                **context,
                "sequence": 1,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "printer": {"state": "idle"},
                "slots": [],
                "slot_topology_complete": False,
            },
        )
        assert observed.status_code == 200, observed.text
        status = await auth_client.get(path, params={"transport": "edge_agent"})
        assert status.json()["node_instance_id"] == node_id
        assert status.json()["source_instance_id"] == context["source_instance_id"]
        desired = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
        assert desired.status_code == 200, desired.text
        desired_slots = desired.json()["slots"]
        assert len(desired_slots) == 1
        assert desired_slots[0]["spool"]["id"] == spool.id
        assert desired_slots[0]["spool"]["remaining_weight_g"] == 1000
        assert spool.used_weight_g == 0
        connections.append((path, headers, context))

    rows = list(
        (
            await db_session.scalars(
                select(PhysicalPrinterConnector).where(
                    PhysicalPrinterConnector.node_instance_id == node_id,
                )
            )
        ).all()
    )
    assert len(rows) == count
    assert len({row.source_instance_id for row in rows}) == count
    assert len(list((await db_session.scalars(select(MaterialSystem))).all())) == count

    first, second = connections[:2]
    cross_printer = await auth_client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers=first[1],
        json={
            **second[2],
            "observed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert cross_printer.status_code == 401

    other = User(
        email="other-node-owner@example.com",
        username="othernodeowner",
        password_hash="test",
        active=True,
        email_verified=True,
        terms_version_accepted=auth_user.terms_version_accepted,
        personal_data_consent_version=auth_user.personal_data_consent_version,
    )
    db_session.add(other)
    await db_session.commit()
    foreign = {"Authorization": "Bearer " + create_access_token({"sub": other.email})}
    for method in (auth_client.get, auth_client.delete):
        denied = await method(first[0], params={"transport": "edge_agent"}, headers=foreign)
        assert denied.status_code == 404
        assert node_id not in denied.text

    revoked = await auth_client.delete(first[0], params={"transport": "edge_agent"})
    assert revoked.status_code == 204
    for index, (_, headers, _) in enumerate(connections):
        desired = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
        assert desired.status_code == (401 if index == 0 else 200)
