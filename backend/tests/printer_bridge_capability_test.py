"""Capability boundaries shared by provider-neutral printer bridges."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user_spool import UserSpool

_GENERIC_SNAPSHOT_CAPABILITIES = (
    ("happy_hare", "edge_agent", {"read", "presence", "spool_identity", "tag_read"}),
    ("bambu", "orca_plugin_lan", {"read", "presence", "consumption", "tag_read"}),
)
_GENERIC_OPERATION_CASES = (
    ("desired", [], "read", None),
    ("slot", [], "presence", {"provider_index": 0}),
    (
        "identity",
        ["presence"],
        "spool_identity",
        {"provider_index": 0, "spool_identity_known": True},
    ),
    (
        "tag",
        ["presence"],
        "tag_read",
        {"provider_index": 0, "tag_uid": "04A1B2C3"},
    ),
)


def _generic_conformance_cases():
    # This ingress can prove only snapshot/desired-read operations. Runtime
    # write and consumption capabilities use their command/usage routes and
    # remain covered by those route-specific suites.
    return [
        pytest.param(
            provider,
            transport,
            case,
            stored_capabilities,
            required_capability,
            slot,
            id=f"{transport}-{case}",
        )
        for provider, transport, snapshot_capabilities in _GENERIC_SNAPSHOT_CAPABILITIES
        for case, stored_capabilities, required_capability, slot in _GENERIC_OPERATION_CASES
        if required_capability in snapshot_capabilities
    ]


async def _paired_bridge(
    auth_client: AsyncClient,
    capabilities: list[str],
    *,
    provider: str = "bambu",
    transport: str = "orca_plugin_lan",
) -> tuple[int, int, str, dict[str, str]]:
    printer = await auth_client.post(
        "/api/v1/physical-printers",
        json={"name": "Capability boundary printer"},
    )
    assert printer.status_code == 201
    printer_id = printer.json()["id"]
    system = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={"name": "Capability feed", "provider": provider, "slot_count": 1},
    )
    assert system.status_code == 201
    system_id = system.json()["material_systems"][0]["id"]
    pairing_code = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code",
        params={"transport": transport},
    )
    assert pairing_code.status_code == 200
    source_instance_id = f"capability-test-{printer_id:08d}"
    payload = {
        "pairing_code": pairing_code.json()["pairing_code"],
        "provider": provider,
        "transport": transport,
        "source_instance_id": source_instance_id,
        "plugin_version": "0.1.0-test",
        "capabilities": capabilities,
    }
    if transport == "edge_agent":
        payload["node_instance_id"] = f"capability-node-{printer_id:08d}"
    paired = await auth_client.post("/api/v1/printer-bridge/pair", json=payload)
    assert paired.status_code == 200
    return (
        printer_id,
        system_id,
        source_instance_id,
        {"X-FilamentHub-Bridge-Token": paired.json()["bridge_token"]},
    )


def _context(
    system_id: int,
    source_instance_id: str,
    *,
    provider: str = "bambu",
    transport: str = "orca_plugin_lan",
) -> dict[str, object]:
    return {
        "material_system_id": system_id,
        "provider": provider,
        "transport": transport,
        "source_instance_id": source_instance_id,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "provider",
        "transport",
        "case",
        "stored_capabilities",
        "required_capability",
        "slot",
    ),
    _generic_conformance_cases(),
)
async def test_generic_bridge_requires_persisted_capability_before_payload_update(
    auth_client: AsyncClient,
    provider: str,
    transport: str,
    case: str,
    stored_capabilities: list[str],
    required_capability: str,
    slot: dict[str, object] | None,
) -> None:
    _, system_id, source_instance_id, headers = await _paired_bridge(
        auth_client,
        stored_capabilities,
        provider=provider,
        transport=transport,
    )
    context = _context(
        system_id,
        source_instance_id,
        provider=provider,
        transport=transport,
    )

    if case == "desired":
        rejected = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
    else:
        advertised = sorted({*stored_capabilities, required_capability})
        rejected = await auth_client.post(
            "/api/v1/printer-bridge/snapshot",
            headers=headers,
            json={
                **context,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "capabilities": advertised,
                "slots": [slot],
            },
        )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == {
        "code": "ERR_PRINTER_BRIDGE_CAPABILITY_REQUIRED",
        "params": {"capability": required_capability},
    }

    granted = sorted({*stored_capabilities, required_capability})
    updated = await auth_client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers=headers,
        json={
            **context,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "capabilities": granted,
        },
    )
    assert updated.status_code == 200
    if case == "desired":
        accepted = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
    else:
        accepted = await auth_client.post(
            "/api/v1/printer-bridge/snapshot",
            headers=headers,
            json={
                **context,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "slots": [slot],
            },
        )
    assert accepted.status_code == 200


@pytest.mark.asyncio
async def test_generic_bridge_allows_status_and_heartbeat_without_material_capability(
    auth_client: AsyncClient,
) -> None:
    _, system_id, source_instance_id, headers = await _paired_bridge(auth_client, [])
    context = _context(system_id, source_instance_id)

    status_snapshot = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            **context,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "printer": {"state": "idle"},
        },
    )
    assert status_snapshot.status_code == 200
    heartbeat = await auth_client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers=headers,
        json={
            **context,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "capabilities": [],
        },
    )
    assert heartbeat.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "transport", "allowed"),
    [
        ("bambu", "orca_plugin_lan", {"read", "write", "presence", "consumption", "tag_read"}),
        ("moonraker", "edge_agent", {"read", "presence", "consumption"}),
        (
            "happy_hare",
            "edge_agent",
            {"read", "presence", "spool_identity", "consumption", "tag_read"},
        ),
    ],
)
async def test_generic_bridge_persists_only_manifest_capabilities(
    auth_client: AsyncClient,
    provider: str,
    transport: str,
    allowed: set[str],
) -> None:
    printer_id, system_id, source_instance_id, headers = await _paired_bridge(
        auth_client,
        [
            "read",
            "write",
            "presence",
            "spool_identity",
            "consumption",
            "local_command",
            "tag_read",
            "tag_write",
            "future_capability",
        ],
        provider=provider,
        transport=transport,
    )
    printer = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    connector = next(
        item
        for item in printer["connectors"]
        if item["provider"] == provider and item["transport"] == transport
    )
    assert set(connector["capabilities"]) == allowed
    assert allowed <= set(printer["material_systems"][0]["capabilities"])
    assert not {"local_command", "tag_write"} & set(
        printer["material_systems"][0]["capabilities"]
    )

    snapshot = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            **_context(
                system_id,
                source_instance_id,
                provider=provider,
                transport=transport,
            ),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "capabilities": [*allowed, "local_command", "tag_write"],
            "slot_topology_complete": True,
            "slots": [{"provider_index": 0}],
        },
    )
    assert snapshot.status_code == 200
    printer = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    connector = next(
        item
        for item in printer["connectors"]
        if item["provider"] == provider and item["transport"] == transport
    )
    assert set(connector["capabilities"]) == allowed
    assert allowed <= set(printer["material_systems"][0]["capabilities"])
    assert not {"local_command", "tag_write"} & set(
        printer["material_systems"][0]["capabilities"]
    )

    heartbeat = await auth_client.post(
        "/api/v1/printer-bridge/heartbeat",
        headers=headers,
        json={
            **_context(
                system_id,
                source_instance_id,
                provider=provider,
                transport=transport,
            ),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "capabilities": [*allowed, "local_command", "tag_write", "future_capability"],
        },
    )
    assert heartbeat.status_code == 200
    printer = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    connector = next(
        item
        for item in printer["connectors"]
        if item["provider"] == provider and item["transport"] == transport
    )
    assert set(connector["capabilities"]) == allowed
    assert allowed <= set(printer["material_systems"][0]["capabilities"])
    assert not {"local_command", "tag_write"} & set(
        printer["material_systems"][0]["capabilities"]
    )


@pytest.mark.asyncio
async def test_unimplemented_bambu_edge_keeps_identity_without_capabilities(
    auth_client: AsyncClient,
) -> None:
    printer_id, system_id, source_instance_id, headers = await _paired_bridge(
        auth_client,
        ["read", "presence", "spool_identity", "consumption", "tag_read"],
        provider="bambu",
        transport="edge_agent",
    )
    printer = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    connector = next(
        item
        for item in printer["connectors"]
        if item["provider"] == "bambu" and item["transport"] == "edge_agent"
    )
    assert connector["capabilities"] == []

    rejected = await auth_client.post(
        "/api/v1/printer-bridge/snapshot",
        headers=headers,
        json={
            **_context(
                system_id,
                source_instance_id,
                provider="bambu",
                transport="edge_agent",
            ),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "slots": [{"provider_index": 0}],
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == {
        "code": "ERR_PRINTER_BRIDGE_CAPABILITY_REQUIRED",
        "params": {"capability": "presence"},
    }


@pytest.mark.asyncio
async def test_bambu_orca_consumption_snapshot_route_and_estimate_are_idempotent(
    auth_client: AsyncClient, db_session
) -> None:
    printer_id, system_id, source, headers = await _paired_bridge(
        auth_client, ["read", "presence", "consumption"],
    )
    printer = (await auth_client.get(f"/api/v1/physical-printers/{printer_id}")).json()
    slot = printer["material_systems"][0]["slots"][0]
    created = await auth_client.post("/api/v1/spools", json={"initial_weight_g": 1000})
    assert created.status_code == 201, created.text
    spool_id = created.json()["id"]
    assigned = await auth_client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slot['id']}",
        json={
            "expected_revision": slot["assignment_revision"],
            "expected_spool_id": None,
            "spool_id": spool_id,
        },
    )
    assert assigned.status_code == 200, assigned.text
    desired = await auth_client.get("/api/v1/printer-bridge/snapshot", headers=headers)
    assert desired.status_code == 200, desired.text
    route = desired.json()["slots"][0]
    assert route["usage_route_proof"]
    event = {
        "contract_version": 2,
        "event_id": "bambu-estimate-1",
        "job_id": "bambu-job-1",
        "event_type": "terminal",
        "segment_sequence": 1,
        "outcome": "completed",
        "items": [{
            "slot_index": route["index"],
            "spool_id": spool_id,
            "used_weight_g": 10,
            "usage_route_proof": route["usage_route_proof"],
            "evidence": "route_proof",
            "consumption_kind": "estimated",
            "estimate_source": "slicer_gcode",
        }],
    }
    payload = {
        "material_system_id": system_id,
        "provider": "bambu",
        "transport": "orca_plugin_lan",
        "source_instance_id": source,
        "sequence": 1,
        "events": [event],
    }
    accepted = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches", headers=headers, json=payload
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["deduplicated"] is False
    replay = await auth_client.post(
        "/api/v1/printer-bridge/usage-batches", headers=headers, json=payload
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["deduplicated"] is True
    spool = await db_session.scalar(select(UserSpool).where(UserSpool.id == spool_id))
    assert spool.remaining_weight_g == 990
    usage = await db_session.scalar(select(PresetUsageEvent).where(
        PresetUsageEvent.spool_id == spool_id,
        PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
    ))
    assert usage is not None
    job = await auth_client.get(f"/api/v1/print-jobs/{usage.print_job_id}")
    assert job.status_code == 200
    assert job.json()["confirmed_consumption_g"] == 0
    assert job.json()["estimated_consumption_g"] == 10
