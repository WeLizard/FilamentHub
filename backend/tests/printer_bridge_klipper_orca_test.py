"""Filament usage of a Klipper printer reported by the OrcaSlicer plugin."""

import math
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_system import PhysicalPrinterConnector
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState

SOURCE = "orca-desktop-instance-01"
BRIDGE = "/api/v1/printer-bridge/klipper-usage-link"


async def _klipper_printer(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
    *,
    provider: str = "happy_hare",
    bound: bool = True,
) -> tuple[int, int, UserSpool]:
    """A printer card with one slot holding a spool, reached by one OrcaSlicer."""
    created = await auth_client.post("/api/v1/physical-printers", json={"name": "Voron"})
    printer_id = created.json()["id"]
    response = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={"name": "Feed", "kind": "mmu", "provider": provider, "slot_count": 1},
    )
    assert response.status_code in {200, 201}, response.text
    system = response.json()["material_systems"][0]
    spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(spool)
    if bound:
        db_session.add(PrinterConnectionBinding(
            user_id=auth_user.id, physical_printer_id=printer_id,
            source_instance_id=SOURCE, connection_ref="voron-connection",
            normalized_endpoint="fixture-voron-connection", status="bound",
            provider="moonraker",
        ))
    await db_session.commit()
    await db_session.refresh(spool)
    slot = system["slots"][0]
    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slot['id']}",
        json={
            "expected_revision": slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": spool.id,
        },
    )
    assert assigned.status_code == 200, assigned.text
    return printer_id, system["id"], spool


def _request(printer_id: int, system_id: int, capabilities: list[str]) -> dict:
    return {
        "physical_printer_id": printer_id,
        "material_system_id": system_id,
        "source_instance_id": SOURCE,
        "plugin_version": "0.3.0",
        "capabilities": capabilities,
    }


def _batch(system_id: int, provider: str, sequence: int, spool_id: int, proof: str | None) -> dict:
    item: dict[str, object] = {"slot_index": 0, "spool_id": spool_id, "used_length_mm": 1000}
    if proof is not None:
        item["usage_route_proof"] = proof
    return {
        "material_system_id": system_id,
        "provider": provider,
        "transport": "orca_plugin_lan",
        "source_instance_id": SOURCE,
        "sequence": sequence,
        "events": [{
            "contract_version": 2,
            "event_id": f"moonraker:job-1:{sequence}",
            "job_id": "moonraker:job-1",
            "segment_sequence": sequence,
            "event_type": "checkpoint",
            "reasons": ["periodic"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "items": [item],
        }],
    }


@pytest.mark.asyncio
async def test_a_bound_orca_installation_deducts_a_klipper_print_once(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer_id, system_id, spool = await _klipper_printer(auth_client, auth_user, db_session)

    granted = await auth_client.post(
        BRIDGE,
        # The plugin sets no slot through this link; a wider claim is trimmed.
        json=_request(printer_id, system_id, ["read", "consumption", "write"]),
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["provider"] == "happy_hare"
    headers = {"X-FilamentHub-Bridge-Token": granted.json()["bridge_token"]}
    connector = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.material_system_id == system_id,
            PhysicalPrinterConnector.source_instance_id == SOURCE,
        )
    )
    assert connector is not None and connector.transport == "orca_plugin_lan"
    assert sorted(connector.capabilities) == ["consumption", "read"]

    desired = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
    assert desired.status_code == 200, desired.text
    proof = desired.json()["slots"][0]["usage_route_proof"]
    assert proof

    payload = _batch(system_id, "happy_hare", 1, spool.id, proof)
    first = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches", headers=headers, json=payload
    )
    assert first.status_code == 200, first.text
    expected = 1000.0 * math.pi * (1.75 / 2.0) ** 2 / 1000.0 * 1.24
    assert first.json()["events"][0]["consumed_weight_g"] == pytest.approx(expected)
    # The answer was lost and the plugin sends the same batch again.
    replay = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches", headers=headers, json=payload
    )
    assert replay.status_code == 200 and replay.json()["deduplicated"] is True
    await db_session.refresh(spool)
    assert spool.used_weight_g == pytest.approx(expected)


@pytest.mark.asyncio
async def test_a_usage_link_needs_a_bound_connection_and_a_klipper_feed(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    unbound_id, unbound_system, _spool = await _klipper_printer(
        auth_client, auth_user, db_session, bound=False
    )
    refused = await auth_client.post(BRIDGE, json=_request(unbound_id, unbound_system, ["read"]))
    assert refused.status_code == 404

    bambu_id, bambu_system, _spool = await _klipper_printer(
        auth_client, auth_user, db_session, provider="bambu"
    )
    wrong = await auth_client.post(BRIDGE, json=_request(bambu_id, bambu_system, ["read"]))
    assert wrong.status_code == 409
    assert wrong.json()["detail"]["code"] == "ERR_PRINTER_BRIDGE_WRONG_PROVIDER"


@pytest.mark.asyncio
async def test_moonrakers_own_spoolman_report_keeps_the_plugin_from_deducting_again(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer_id, system_id, spool = await _klipper_printer(auth_client, auth_user, db_session)
    device = await db_session.get(UserPrinterDevice, printer_id)
    assert device is not None
    device.api_key = "klipper_native_spoolman_key"
    await db_session.commit()

    granted = await auth_client.post(
        BRIDGE, json=_request(printer_id, system_id, ["read", "consumption"])
    )
    headers = {"X-FilamentHub-Bridge-Token": granted.json()["bridge_token"]}
    # Moonraker has not been heard from: the plugin is the one that deducts.
    held = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
    proof = held.json()["slots"][0]["usage_route_proof"]
    assert proof

    reported = await auth_client.put(
        f"/api/v1/spool_compat/klipper_native_spoolman_key/v1/spool/{spool.id}/use",
        json={"use_weight": 25},
    )
    assert reported.status_code == 200, reported.text

    late = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches",
        headers=headers,
        json=_batch(system_id, "happy_hare", 1, spool.id, proof),
    )
    # Acknowledged, so the plugin's queue drains, and not deducted.
    assert late.status_code == 200, late.text
    assert late.json()["events"][0]["consumed_weight_g"] == 0
    await db_session.refresh(spool)
    assert spool.used_weight_g == pytest.approx(25)
    # While Moonraker's own link is in touch the plugin is given no proof either.
    after = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
    assert after.json()["slots"][0].get("usage_route_proof") is None
    connector = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.material_system_id == system_id,
            PhysicalPrinterConnector.source_instance_id == SOURCE,
        )
    )
    await db_session.refresh(connector)
    assert connector.usage_authority is False

    # The link was removed from Moonraker long ago: the plugin deducts again.
    device.native_last_seen_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await db_session.commit()
    resumed = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
    assert resumed.json()["slots"][0]["usage_route_proof"]
