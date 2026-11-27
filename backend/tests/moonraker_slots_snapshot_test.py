"""Plugin-side QIDI Box slots reach the same legacy material system as Edge's."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

URL = "/api/v1/orcaslicer/preset-slot-sync/moonraker/snapshot"


def _slots(present: list[bool | None]) -> list[dict]:
    return [
        {
            "provider_index": index,
            "kind": "slot",
            "label": f"Box 1 slot {index + 1}",
            "present": value,
            "material": "PLA" if value else None,
            "spool_identity_known": False,
        }
        for index, value in enumerate(present)
    ]


@pytest.mark.asyncio
async def test_plugin_reports_qidi_box_slots_and_online_state(auth_client: AsyncClient) -> None:
    printer_id = (
        await auth_client.post("/api/v1/physical-printers", json={"name": "Qidi Q2"})
    ).json()["id"]
    now = datetime.now(timezone.utc)

    first = await auth_client.post(
        URL,
        json={
            "physical_printer_id": printer_id,
            "snapshot_ts": now.isoformat(),
            "slots": _slots([True, False, None, True]),
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["slots_seen"] == 4

    older = await auth_client.post(
        URL,
        json={
            "physical_printer_id": printer_id,
            "snapshot_ts": (now - timedelta(minutes=5)).isoformat(),
            "slots": _slots([False, False, False, False]),
        },
    )
    assert older.status_code == 200, older.text

    printer = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    systems = printer["material_systems"]
    assert [item["provider"] for item in systems] == ["legacy"]
    observed = [slot["observation"] or {} for slot in systems[0]["slots"]]
    # the stale snapshot must not overwrite the newer one
    assert [item.get("present") for item in observed] == [True, False, None, True]


@pytest.mark.asyncio
async def test_snapmaker_heads_reach_a_printer_set_up_as_single_feed(
    auth_client: AsyncClient,
) -> None:
    # The setup wizard offers "single feed" first; the U1's four heads must
    # still show once the plugin reads them.
    created = await auth_client.post(
        "/api/v1/physical-printers",
        json={
            "name": "Snapmaker U1",
            "material_system": {
                "name": "Feed", "provider": "manual", "capabilities": [],
                "kind": "direct_feed", "slot_count": 1,
                "slots": [{"provider_index": 0, "kind": "external"}],
            },
        },
    )
    assert created.status_code in {200, 201}, created.text
    printer_id = created.json()["id"]
    heads = [
        {"provider_index": index, "kind": "slot", "label": f"Head {index + 1}",
         "present": True, "material": "PLA", "spool_identity_known": False,
         "active_feed": index == 2}
        for index in range(4)
    ]
    response = await auth_client.post(
        URL,
        json={
            "physical_printer_id": printer_id,
            "snapshot_ts": datetime.now(timezone.utc).isoformat(),
            "slots": heads,
        },
    )
    assert response.status_code == 200, response.text

    printer = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    systems = printer["material_systems"]
    assert len(systems) == 1, systems
    active = [slot for slot in systems[0]["slots"] if slot.get("active", True)]
    assert [slot["provider_index"] for slot in active] == [0, 1, 2, 3], systems


@pytest.mark.asyncio
async def test_duplicate_slot_indices_are_rejected(auth_client: AsyncClient) -> None:
    printer_id = (
        await auth_client.post("/api/v1/physical-printers", json={"name": "Qidi dup"})
    ).json()["id"]
    slots = _slots([True, True])
    slots[1]["provider_index"] = 0
    response = await auth_client.post(
        URL,
        json={
            "physical_printer_id": printer_id,
            "snapshot_ts": datetime.now(timezone.utc).isoformat(),
            "slots": slots,
        },
    )
    assert response.status_code == 422
