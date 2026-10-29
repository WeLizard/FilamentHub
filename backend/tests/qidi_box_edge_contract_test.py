"""A QIDI Box reported by Edge as a legacy Klipper feed (no new provider)."""

import json
import sys
from pathlib import Path

import pytest
from httpx import AsyncClient

EDGE = Path(__file__).resolve().parents[2] / "edge-agent"
FIXTURES = EDGE / "tests" / "fixtures" / "qidi_box"


@pytest.mark.asyncio
async def test_legacy_edge_accepts_qidi_box_slots(auth_client: AsyncClient) -> None:
    sys.path.insert(0, str(EDGE / "src"))
    try:
        from filamenthub_edge.providers import qidi_box
    finally:
        sys.path.remove(str(EDGE / "src"))

    printer_id = (
        await auth_client.post("/api/v1/physical-printers", json={"name": "Qidi Q2"})
    ).json()["id"]
    system = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={"name": "Feed", "provider": "legacy", "slot_count": 1},
    )
    system_id = system.json()["material_systems"][0]["id"]
    pairing = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
        params={"transport": "edge_agent"},
    )
    source = "qidi-edge-instance-0001"
    paired = await auth_client.post(
        "/api/v1/printer-bridge/pair",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "provider": "legacy",
            "transport": "edge_agent",
            "source_instance_id": source,
            "plugin_version": "0.1.0-test",
            "node_instance_id": "edge-node-test-000001",
            "capabilities": ["read", "presence"],
        },
    )
    headers = {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]}
    status = json.loads((FIXTURES / "query.json").read_text(encoding="utf-8"))["result"]["status"]
    colors, filaments = qidi_box.parse_dictionary(
        (FIXTURES / "officiall_filas_list.cfg").read_text(encoding="utf-8")
    )
    slots = qidi_box.build_slots(status, colors, filaments)
    response = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            "material_system_id": system_id,
            "provider": "legacy",
            "transport": "edge_agent",
            "source_instance_id": source,
            "capabilities": ["read", "presence"],
            "sequence": 1,
            "observed_at": "2099-01-01T00:00:00+00:00",
            "slots": slots,
            "slot_topology_complete": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    listed = await auth_client.get(f"/api/v1/physical-printers/{printer_id}")
    stored = listed.json()["material_systems"][0]["slots"]
    observed = [(item["observation"] or {}) for item in stored]
    assert [item.get("present") for item in observed] == [True, True, False, None]
    assert [item.get("material") for item in observed][:2] == ["PLA", "PETG"]
