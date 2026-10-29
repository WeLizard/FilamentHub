"""The external slot checkbox shows or hides a slot; it never deletes the row."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState

SOURCE = "fixture-plugin-instance-0101"


async def _bambu_printer(client: AsyncClient) -> tuple[int, int, dict]:
    printer_id = (await client.post("/api/v1/physical-printers", json={"name": "P2S"})).json()["id"]
    system_id = (
        await client.post(
            f"/api/v1/physical-printers/{printer_id}/material-systems",
            json={"name": "AMS", "kind": "mmu", "provider": "bambu",
                  "capabilities": ["read", "presence"]},
        )
    ).json()["material_systems"][0]["id"]
    pairing = await client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code"
    )
    paired = await client.post(
        "/api/v1/printer-bridge/pair",
        json={"pairing_code": pairing.json()["pairing_code"], "provider": "bambu",
              "transport": "orca_plugin_lan", "source_instance_id": SOURCE,
              "plugin_version": "0.1.0-test", "capabilities": ["read", "presence"]},
    )
    return printer_id, system_id, {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]}


async def _report(client, headers, system_id: int, external_present: bool = False) -> None:
    response = await client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            "material_system_id": system_id, "provider": "bambu",
            "transport": "orca_plugin_lan", "source_instance_id": SOURCE,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "slots": [
                {"provider_index": 0, "present": False},
                {"provider_index": 255, "kind": "external", "present": external_present,
                 **({"material": "PLA"} if external_present else {})},
            ],
            "slot_topology_complete": True,
        },
    )
    assert response.status_code == 200, response.text


async def _slots(client, printer_id: int) -> list[dict]:
    body = (await client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    return body["material_systems"][0]["slots"]


async def _save_topology(client, printer_id: int, system_id: int, indices: list[int]):
    slots = await _slots(client, printer_id)
    return await client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-systems/{system_id}",
        json={
            "kind": "mmu",
            "slots": [
                {"provider_index": i, "kind": "external" if i == 255 else "slot"} for i in indices
            ],
            "expected_slots": [
                {"material_slot_id": s["id"], "expected_revision": s["assignment_revision"],
                 "expected_spool_id": (s["assignment"] or {}).get("spool_id")}
                for s in slots
            ],
        },
    )


@pytest.mark.asyncio
async def test_hiding_the_external_slot_survives_provider_reports_and_restores_same_row(
    auth_client: AsyncClient,
) -> None:
    printer_id, system_id, headers = await _bambu_printer(auth_client)
    await _report(auth_client, headers, system_id)
    external_id = next(s["id"] for s in await _slots(auth_client, printer_id) if s["provider_index"] == 255)

    hidden = await _save_topology(auth_client, printer_id, system_id, [0])
    assert hidden.status_code == 200, hidden.text
    await _report(auth_client, headers, system_id)
    slots = await _slots(auth_client, printer_id)
    external = next(s for s in slots if s["provider_index"] == 255)
    assert external["id"] == external_id
    assert external["user_visibility"] == "hidden"
    assert external["active"] is True
    assert external["displayed"] is False

    # Material in the external holder shows it without changing the choice.
    await _report(auth_client, headers, system_id, external_present=True)
    external = next(s for s in await _slots(auth_client, printer_id) if s["provider_index"] == 255)
    assert external["user_visibility"] == "hidden"
    assert external["displayed"] is True

    restored = await _save_topology(auth_client, printer_id, system_id, [0, 255])
    assert restored.status_code == 200, restored.text
    external = next(s for s in await _slots(auth_client, printer_id) if s["provider_index"] == 255)
    assert external["id"] == external_id
    assert external["user_visibility"] == "shown"


@pytest.mark.asyncio
async def test_hiding_an_occupied_external_slot_is_accepted_and_keeps_it_displayed(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer_id, system_id, headers = await _bambu_printer(auth_client)
    await _report(auth_client, headers, system_id)
    spool = UserSpool(user_id=auth_user.id, initial_weight_g=1000, used_weight_g=0,
                      state=UserSpoolState.shelf, source="manual")
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)
    slots = await _slots(auth_client, printer_id)
    external = next(s for s in slots if s["provider_index"] == 255)
    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{external['id']}",
        json={"expected_revision": external["assignment_revision"],
              "expected_spool_id": None, "spool_id": spool.id},
    )
    assert assigned.status_code == 200, assigned.text

    hidden = await _save_topology(auth_client, printer_id, system_id, [0])
    assert hidden.status_code == 200, hidden.text
    external = next(s for s in await _slots(auth_client, printer_id) if s["provider_index"] == 255)
    assert external["assignment"]["spool_id"] == spool.id
    assert external["user_visibility"] == "hidden"
    assert external["displayed"] is True
