"""Delayed inventory evidence must retain its physical spool and issued route."""

import hashlib
import json
import math
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import PhysicalPrinterConnector
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.printer_bridge_receipt import PrinterBridgeReceipt
from app.models.user import User
from app.models.user_spool import UserSpool
from app.schemas.printer_bridge import PrinterBridgeUsageBatchRequest
from app.schemas.printer_usage import PrinterUsageEvent
from app.services.printer_usage_service import _terminal_payload_hash, usage_payload_hash


async def _system(client):
    response = await client.post("/api/v1/physical-printers", json={"name": "Route printer"})
    assert response.status_code == 201
    printer_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={"name": "Feed", "kind": "mmu", "provider": "octoprint", "slot_count": 2},
    )
    assert response.status_code == 201
    return printer_id, response.json()["material_systems"][0]


async def _pair(client, bridge, source=None):
    source = source or bridge.source
    prefix = "printer-bridge" if bridge.transport == "edge" else "octoprint-bridge"
    response = await client.post(
        f"/api/v1/{prefix}/connections/{bridge.printer_id}/{bridge.system_id}/pairing-code",
        params={"transport": "edge_agent"} if bridge.transport == "edge" else {},
    )
    assert response.status_code == 200
    payload = {
        "pairing_code": response.json()["pairing_code"],
        "capabilities": ["read", "consumption"],
        "plugin_version": "0.1.0",
    }
    if bridge.transport == "edge":
        payload.update(
            provider="octoprint",
            transport="edge_agent",
            source_instance_id=source,
            node_instance_id="usage-route-node-0001",
        )
    else:
        payload.update(instance_id=source, octoprint_version="1.11.8")
    response = await client.post(f"/api/v1/{prefix}/pair", json=payload)
    assert response.status_code == 200, response.text
    return {"X-FilamentHub-Bridge-Token": response.json()["bridge_token"]}


async def _assign(client, printer_id, slot, spool_id, preset_id):
    response = await client.patch(
        f"/api/v1/physical-printers/{printer_id}/material-slots/{slot['id']}",
        json={
            "expected_revision": slot["assignment_revision"],
            "expected_spool_id": (
                slot.get("assignment", {}).get("spool_id") if slot.get("assignment") else None
            ),
            "spool_id": spool_id,
            "preset_id": preset_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["material_systems"][0]["slots"][0]


async def _snapshot(client, bridge, etag=None):
    headers = dict(bridge.headers)
    if etag:
        headers["If-None-Match"] = etag
    return await client.get(f"/api/v1/{bridge.prefix}/snapshot", headers=headers)


async def _send(client, bridge, event, sequence=1):
    if bridge.transport == "edge":
        return await client.post(
            "/api/v1/printer-bridge/usage-batches",
            headers=bridge.headers,
            json={
                "material_system_id": bridge.system_id,
                "provider": "octoprint",
                "transport": "edge_agent",
                "source_instance_id": bridge.source,
                "sequence": sequence,
                "events": [event],
            },
        )
    return await client.post("/api/v1/octoprint-bridge/usage", headers=bridge.headers, json=event)


def _event(
    spool_id,
    proof,
    event_id="delayed-A",
    *,
    segment_sequence=None,
    tool_index=None,
):
    event = {
        "event_id": event_id,
        "job_id": "offline-attempt",
        "event_type": "checkpoint",
        "items": [
            {
                "slot_index": 0,
                "spool_id": spool_id,
                "used_length_mm": 1000,
                "usage_route_proof": proof,
            }
        ],
    }
    if segment_sequence is not None:
        event["contract_version"] = 2
        event["segment_sequence"] = segment_sequence
        event["items"][0]["tool_index"] = tool_index
        event["items"][0]["evidence"] = "route_proof"
    return event


@pytest.fixture(params=["edge", "octoprint"])
async def route_bridge(request, auth_client, auth_user, db_session):
    printer_id, system = await _system(auth_client)
    brand = Brand(name="Same QR brand", slug="same-qr-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Same QR PLA",
        slug="same-qr-pla",
        material_type="PLA",
        color_name="Red",
        color_hex="#FF0000",
        density=1.24,
        diameter=1.75,
        qr_code="FHUB-SAME-PRODUCT",
    )
    db_session.add(filament)
    await db_session.flush()
    preset = Preset(
        user_id=auth_user.id,
        filament_id=filament.id,
        name="Shared recipe",
        extruder_temp=210,
        bed_temp=60,
        moderation_status=PresetModerationStatus.APPROVED,
    )
    spools = [
        UserSpool(user_id=auth_user.id, filament_id=filament.id, initial_weight_g=1000)
        for _ in range(2)
    ]
    db_session.add_all([preset, *spools])
    await db_session.commit()
    slot = await _assign(auth_client, printer_id, system["slots"][0], spools[0].id, preset.id)
    bridge = SimpleNamespace(
        transport=request.param,
        printer_id=printer_id,
        system_id=system["id"],
        slot=slot,
        source="usage-route-source-0001",
        spool_a=spools[0],
        spool_b=spools[1],
        spool_a_id=spools[0].id,
        spool_b_id=spools[1].id,
        preset_id=preset.id,
        filament=filament,
        preset=preset,
        prefix="printer-bridge" if request.param == "edge" else "octoprint-bridge",
    )
    bridge.headers = await _pair(auth_client, bridge)
    snapshot = await _snapshot(auth_client, bridge)
    assert snapshot.status_code == 200, snapshot.text
    bridge.proof = snapshot.json()["slots"][0]["usage_route_proof"]
    bridge.etag = snapshot.headers["etag"]
    assert len(bridge.proof) == 108
    return bridge


async def test_first_offline_usage_after_identical_spool_replacement_is_attributed_once(
    route_bridge,
    auth_client,
    db_session,
):
    bridge = route_bridge
    original = _event(
        bridge.spool_a_id,
        bridge.proof,
        segment_sequence=1,
        tool_index=0,
    )
    assert bridge.spool_a_id != bridge.spool_b_id
    assert bridge.spool_a.filament_id == bridge.spool_b.filament_id
    assert bridge.filament.qr_code == "FHUB-SAME-PRODUCT"
    await _assign(auth_client, bridge.printer_id, bridge.slot, bridge.spool_b_id, bridge.preset_id)
    # This is the first arrival of A, after replacement by visually identical B.
    first = await _send(auth_client, bridge, original)
    assert first.status_code == 200, first.text
    assert first.json()["deduplicated"] is False
    replay = await _send(auth_client, bridge, original)
    assert replay.status_code == 200
    assert replay.json()["deduplicated"] is True
    expected = math.pi * (1.75 / 2) ** 2 * 1.24
    await db_session.refresh(bridge.spool_a)
    await db_session.refresh(bridge.spool_b)
    assert bridge.spool_a.used_weight_g == pytest.approx(expected)
    assert bridge.spool_b.used_weight_g == 0
    counterfeit = _event(bridge.spool_b_id, bridge.proof, "forged-B")
    rejected = await _send(auth_client, bridge, counterfeit, 2)
    assert rejected.status_code == 409
    snapshot_b = await _snapshot(auth_client, bridge)
    skipped = _event(
        bridge.spool_b_id,
        snapshot_b.json()["slots"][0]["usage_route_proof"],
        "skipped-B",
        segment_sequence=3,
        tool_index=1,
    )
    rejected_gap = await _send(auth_client, bridge, skipped, 2)
    assert rejected_gap.status_code == 409
    assert rejected_gap.json()["detail"] == {
        "code": "ERR_PRINT_JOB_REPLAY_CONFLICT",
        "params": {"expected_sequence": 2},
    }
    await db_session.refresh(bridge.spool_b)
    assert bridge.spool_b.used_weight_g == 0
    next_event = _event(
        bridge.spool_b_id,
        snapshot_b.json()["slots"][0]["usage_route_proof"],
        "next-B",
        segment_sequence=2,
        tool_index=1,
    )
    continued = await _send(auth_client, bridge, next_event, 2)
    assert continued.status_code == 200, continued.text
    await db_session.refresh(bridge.spool_b)
    assert bridge.spool_b.used_weight_g == pytest.approx(expected)
    rows = list(await db_session.scalars(select(PresetUsageEvent)))
    assert [row.spool_id for row in rows] == [bridge.spool_a_id, bridge.spool_b_id]
    assert all(row.preset_id == bridge.preset_id for row in rows)
    assert rows[0].meta["usage_route"]["spool_id"] == bridge.spool_a_id
    job = await auth_client.get(f"/api/v1/print-jobs/{rows[0].print_job_id}")
    assert job.status_code == 200, job.text
    body = job.json()
    assert [segment["segment_sequence"] for segment in body["usage_segments"]] == [1, 2]
    assert [segment["items"][0]["spool_id"] for segment in body["usage_segments"]] == [
        bridge.spool_a_id,
        bridge.spool_b_id,
    ]
    assert [segment["items"][0]["tool_index"] for segment in body["usage_segments"]] == [
        0,
        1,
    ]
    assert {
        item["evidence"] for segment in body["usage_segments"] for item in segment["items"]
    } == {"route_proof"}
    assert "usage_route_proof" not in json.dumps(body)
    assert bridge.proof not in json.dumps(body)


async def test_multi_item_checkpoint_is_one_segment_with_ordered_items(
    route_bridge,
    auth_client,
    db_session,
):
    bridge = route_bridge
    printer = await auth_client.get(f"/api/v1/physical-printers/{bridge.printer_id}")
    slot_one = printer.json()["material_systems"][0]["slots"][1]
    await _assign(auth_client, bridge.printer_id, slot_one, bridge.spool_b_id, bridge.preset_id)
    snapshot = await _snapshot(auth_client, bridge)
    slots = snapshot.json()["slots"]
    event = {
        "contract_version": 2,
        "event_id": "multi-item-segment",
        "job_id": "multi-item-job",
        "segment_sequence": 1,
        "event_type": "checkpoint",
        "reasons": ["tool_change"],
        "items": [
            {
                "slot_index": slot["index"],
                "tool_index": slot["index"],
                "spool_id": slot["spool"]["id"],
                "usage_route_proof": slot["usage_route_proof"],
                "evidence": "route_proof",
                "used_weight_g": 1,
            }
            for slot in slots
        ],
    }
    accepted = await _send(auth_client, bridge, event)
    assert accepted.status_code == 200, accepted.text
    rows = list(await db_session.scalars(select(PresetUsageEvent)))
    job = await auth_client.get(f"/api/v1/print-jobs/{rows[0].print_job_id}")
    assert job.status_code == 200, job.text
    segments = job.json()["usage_segments"]
    assert len(segments) == 1
    assert segments[0]["event_id"] == "multi-item-segment"
    assert [item["slot_index"] for item in segments[0]["items"]] == [0, 1]
    assert [item["spool_id"] for item in segments[0]["items"]] == [
        bridge.spool_a_id,
        bridge.spool_b_id,
    ]


async def test_original_route_survives_move_archive_empty_and_token_rotation(
    route_bridge,
    auth_client,
    db_session,
):
    bridge = route_bridge
    events = [_event(bridge.spool_a_id, bridge.proof, f"captured-{i}") for i in range(3)]
    other_printer, other_system = await _system(auth_client)
    await _assign(
        auth_client, other_printer, other_system["slots"][0], bridge.spool_a_id, bridge.preset_id
    )
    bridge.headers = await _pair(auth_client, bridge)
    for sequence, state in enumerate([None, "archived", "empty"], 1):
        if state:
            edited = await auth_client.patch(
                f"/api/v1/spools/{bridge.spool_a_id}", json={"state": state}
            )
            assert edited.status_code == 200, edited.text
        response = await _send(auth_client, bridge, events[sequence - 1], sequence)
        assert response.status_code == 200, response.text
        replay = await _send(auth_client, bridge, events[sequence - 1], sequence)
        assert replay.status_code == 200
        assert replay.json()["deduplicated"] is True
    rows = list(
        await db_session.scalars(
            select(PresetUsageEvent).where(
                PresetUsageEvent.event_type == PresetUsageEventType.printer_report
            )
        )
    )
    assert len(rows) == 3
    assert all(row.spool_id == bridge.spool_a_id for row in rows)
    assert rows[-1].delta_weight_g == 0
    assert rows[-1].meta["reported_weight_g"] > 0


async def test_route_is_stable_without_revision_churn_and_freezes_material_properties(
    route_bridge,
    auth_client,
    db_session,
):
    bridge = route_bridge
    assignment = await db_session.scalar(
        select(MaterialSlotAssignment).where(
            MaterialSlotAssignment.material_slot_id == bridge.slot["id"]
        )
    )
    assignment.source_ts += timedelta(seconds=5)
    await db_session.commit()
    unchanged = await _snapshot(auth_client, bridge, bridge.etag)
    assert unchanged.status_code == 304
    receipts = list(await db_session.scalars(select(PrinterBridgeReceipt)))
    assert len(receipts) == 1
    original = _event(bridge.spool_a_id, bridge.proof)
    bridge.filament.density = 2.48
    await db_session.commit()
    changed = await _snapshot(auth_client, bridge, bridge.etag)
    assert changed.status_code == 200
    new_proof = changed.json()["slots"][0]["usage_route_proof"]
    assert new_proof != bridge.proof
    assert changed.json()["slots"][0]["assignment_revision"] == bridge.slot["assignment_revision"]
    first = await _send(auth_client, bridge, original)
    assert first.status_code == 200
    second = await _send(
        auth_client, bridge, _event(bridge.spool_a_id, new_proof, "new-density"), 2
    )
    assert second.status_code == 200
    rows = list(await db_session.scalars(select(PresetUsageEvent)))
    assert rows[1].delta_weight_g == pytest.approx(rows[0].delta_weight_g * 2)


async def test_bad_foreign_rebound_and_deleted_spool_proofs_never_fall_back(
    route_bridge,
    auth_client,
    db_session,
):
    bridge = route_bridge
    for proof in ["malformed", bridge.proof[:-1] + ("A" if bridge.proof[-1] != "A" else "B")]:
        result = await _send(auth_client, bridge, _event(bridge.spool_a_id, proof))
        assert result.status_code == 409
    original = _event(bridge.spool_a_id, bridge.proof)
    bridge.source = "usage-route-different-source"
    bridge.headers = await _pair(auth_client, bridge)
    rejected = await _send(auth_client, bridge, original)
    assert rejected.status_code == 409
    bridge.source = "usage-route-source-0001"
    bridge.headers = await _pair(auth_client, bridge)
    deleted = await auth_client.delete(f"/api/v1/spools/{bridge.spool_a_id}")
    assert deleted.status_code == 204
    rejected = await _send(auth_client, bridge, original)
    assert rejected.status_code == 404
    assert list(await db_session.scalars(select(PresetUsageEvent))) == []
    await db_session.refresh(bridge.spool_b)
    assert bridge.spool_b.used_weight_g == 0


async def test_issued_route_cannot_cross_connector_or_account(
    route_bridge,
    auth_client,
    auth_user,
    db_session,
):
    bridge = route_bridge
    foreign = User(
        email="other-route-owner@example.com",
        username="otherrouteowner",
        password_hash="unused",
        active=True,
        email_verified=True,
        terms_version_accepted=auth_user.terms_version_accepted,
        personal_data_consent_version=auth_user.personal_data_consent_version,
    )
    db_session.add(foreign)
    await db_session.commit()
    foreign_email = foreign.email
    foreign_id = foreign.id
    filament_id = bridge.filament.id
    original = _event(bridge.spool_a_id, bridge.proof)
    alternate = SimpleNamespace(**vars(bridge))
    alternate.transport = "octoprint" if bridge.transport == "edge" else "edge"
    alternate.prefix = (
        "octoprint-bridge" if alternate.transport == "octoprint" else "printer-bridge"
    )
    alternate.headers = await _pair(auth_client, alternate)
    rejected = await _send(auth_client, alternate, original)
    assert rejected.status_code == 409
    # The other account has the same product, slot index and local source name.
    previous_authorization = auth_client.headers["Authorization"]
    auth_client.headers["Authorization"] = f"Bearer {create_access_token({'sub': foreign_email})}"
    try:
        printer_id, system = await _system(auth_client)
        foreign_spool = UserSpool(
            user_id=foreign_id, filament_id=filament_id, initial_weight_g=1000
        )
        db_session.add(foreign_spool)
        await db_session.commit()
        foreign_spool_id = foreign_spool.id
        await _assign(auth_client, printer_id, system["slots"][0], foreign_spool_id, None)
        alternate.printer_id = printer_id
        alternate.system_id = system["id"]
        alternate.headers = await _pair(auth_client, alternate)
        rejected = await _send(auth_client, alternate, _event(foreign_spool_id, bridge.proof))
        assert rejected.status_code == 409
        assert list(await db_session.scalars(select(PresetUsageEvent))) == []
        await db_session.refresh(foreign_spool)
        assert foreign_spool.used_weight_g == 0
    finally:
        auth_client.headers["Authorization"] = previous_authorization


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def test_pre_upgrade_event_and_terminal_receipt_hashes_are_unchanged():
    event = PrinterUsageEvent.model_validate(
        {
            "event_id": "old-event",
            "job_id": "old-job",
            "outcome": "completed",
            "items": [{"slot_index": 0, "spool_id": 7, "used_length_mm": 1000}],
        }
    )
    old = event.model_dump(mode="json")
    old["items"][0].pop("usage_route_proof")
    old["items"][0].pop("tool_index")
    old["items"][0].pop("evidence")
    old.pop("contract_version")
    old.pop("segment_sequence")
    old.pop("event_type")
    old.pop("reasons")
    old.pop("started_at")
    old.pop("observed_at")
    assert usage_payload_hash(event) == _hash(old)
    old.pop("event_id")
    assert _terminal_payload_hash(event) == _hash(old)


def test_usage_v2_requires_sequence_and_rejects_false_evidence():
    base = {
        "contract_version": 2,
        "event_id": "v2-checkpoint",
        "job_id": "v2-job",
        "event_type": "checkpoint",
        "items": [{"slot_index": 0, "spool_id": 7, "used_weight_g": 1}],
    }
    with pytest.raises(ValueError, match="requires segment_sequence"):
        PrinterUsageEvent.model_validate(base)
    with pytest.raises(ValueError, match="evidence must match"):
        PrinterUsageEvent.model_validate(
            {
                **base,
                "segment_sequence": 1,
                "items": [
                    {
                        **base["items"][0],
                        "evidence": "route_proof",
                    }
                ],
            }
        )
    parsed = PrinterUsageEvent.model_validate({**base, "segment_sequence": 1})
    assert parsed.items[0].evidence is None


async def test_pre_upgrade_batch_receipt_replays_without_new_optional_field(
    route_bridge,
    auth_client,
    db_session,
):
    bridge = route_bridge
    if bridge.transport != "edge":
        return
    event = _event(bridge.spool_a_id, None)
    event["items"][0].pop("usage_route_proof")
    payload = PrinterBridgeUsageBatchRequest.model_validate(
        {
            "material_system_id": bridge.system_id,
            "provider": "octoprint",
            "transport": "edge_agent",
            "source_instance_id": bridge.source,
            "sequence": 1,
            "events": [event],
        }
    ).model_dump(mode="json")
    event_payload = payload["events"][0]
    event_payload.pop("contract_version")
    event_payload.pop("segment_sequence")
    event_payload["items"][0].pop("usage_route_proof")
    event_payload["items"][0].pop("tool_index")
    event_payload["items"][0].pop("evidence")
    connector = await db_session.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.physical_printer_id == bridge.printer_id
        )
    )
    db_session.add(
        PrinterBridgeReceipt(
            connector_id=connector.id,
            source_instance_id=bridge.source,
            receipt_kind="usage_batch",
            receipt_id="1",
            sequence=1,
            payload_hash=_hash(payload),
            response_payload={
                "accepted": True,
                "deduplicated": False,
                "ack_sequence": 1,
                "events": [
                    {"event_id": event["event_id"], "deduplicated": False, "consumed_weight_g": 3}
                ],
            },
        )
    )
    await db_session.commit()
    replay = await _send(auth_client, bridge, event)
    assert replay.status_code == 200, replay.text
    assert replay.json()["deduplicated"] is True
    assert list(await db_session.scalars(select(PresetUsageEvent))) == []
