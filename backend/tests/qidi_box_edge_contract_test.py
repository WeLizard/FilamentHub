"""A QIDI Box reported by Edge as a legacy Klipper feed (no new provider)."""

import importlib.util
import json
from pathlib import Path

import pytest
from httpx import AsyncClient

ROOT = Path(__file__).resolve().parents[2]
QIDI_BOX = ROOT / "edge-agent" / "src" / "filamenthub_edge" / "providers" / "qidi_box.py"
FIXTURES = ROOT / "edge-agent" / "tests" / "fixtures" / "qidi_box"


@pytest.mark.asyncio
async def test_legacy_edge_accepts_qidi_box_slots(auth_client: AsyncClient) -> None:
    spec = importlib.util.spec_from_file_location("edge_qidi_box", QIDI_BOX)
    assert spec is not None and spec.loader is not None
    qidi_box = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qidi_box)

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
