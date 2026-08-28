"""Canonical application of replay-protected printer usage evidence."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_MATERIAL_ASSIGNMENT_CONFLICT,
    ERR_MATERIAL_SLOT_NOT_FOUND,
    ERR_PRINTER_BRIDGE_EVENT_CONFLICT,
    ERR_PRINTER_BRIDGE_NOT_CONFIGURED,
    raise_error,
)
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, PhysicalPrinterConnector
from app.models.preset_gate_state import PresetGateStateSource
from app.models.preset_usage_event import PresetUsageEventType
from app.models.print_job import PrintJobStatus
from app.models.printer_bridge_receipt import PrinterBridgeReceipt
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.printer_usage import PrinterUsageEvent
from app.services.material_contract_service import require_physical_printer
from app.services.print_job_service import (
    confirmed_consumption_for_job,
    ensure_provider_job_event,
)
from app.services.spool_service import clear_spool_gate_assignments, clear_spool_location_projection
from app.services.spool_usage_service import (
    record_spool_usage,
    resolve_assigned_preset_id,
)

DEFAULT_DENSITY_G_CM3 = 1.24
DEFAULT_DIAMETER_MM = 1.75
USAGE_RECEIPT_KIND = "usage_event"


@dataclass(frozen=True)
class PrinterUsageResult:
    event_id: str
    deduplicated: bool
    consumed_weight_g: float


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def usage_payload_hash(payload: PrinterUsageEvent) -> str:
    payload_data = payload.model_dump(mode="json")
    if payload.event_type == "terminal":
        # Preserve hashes written by the native OctoPrint Bridge before the
        # provider-neutral contract was extracted.
        payload_data.pop("event_type", None)
    if not payload.reasons:
        payload_data.pop("reasons", None)
    if payload.started_at is None:
        payload_data.pop("started_at", None)
    if payload.observed_at is None:
        payload_data.pop("observed_at", None)
    return hashlib.sha256(
        json.dumps(
            payload_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _terminal_payload_hash(payload: PrinterUsageEvent) -> str:
    payload_data = payload.model_dump(mode="json")
    payload_data.pop("event_id", None)
    payload_data.pop("event_type", None)
    if not payload.reasons:
        payload_data.pop("reasons", None)
    if payload.started_at is None:
        payload_data.pop("started_at", None)
    if payload.observed_at is None:
        payload_data.pop("observed_at", None)
    return hashlib.sha256(
        json.dumps(
            payload_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _received_source_time(value: datetime | None, received_at: datetime) -> datetime:
    if value is None:
        return received_at
    return min(_as_utc(value), received_at)


def _weight_from_length(length_mm: float, density: float, diameter_mm: float) -> float:
    radius = diameter_mm / 2.0
    return max(length_mm * math.pi * radius * radius / 1000.0 * density, 0.0)


async def process_printer_usage_event(
    db: AsyncSession,
    *,
    connector: PhysicalPrinterConnector,
    source_instance_id: str,
    payload: PrinterUsageEvent,
    print_job_source: str,
    print_job_source_ref: str,
    adapter: str,
    conflict_error: str = ERR_PRINTER_BRIDGE_EVENT_CONFLICT,
) -> PrinterUsageResult:
    """Apply one transport event once through PrintJob and the shared spool ledger.

    The caller serializes its connector/connection and owns the transaction.
    This function never commits, which lets a whole Edge batch be acknowledged
    only after all of its receipts and ledger rows are durable together.
    """
    payload_hash = usage_payload_hash(payload)
    existing = await db.scalar(
        select(PrinterBridgeReceipt).where(
            PrinterBridgeReceipt.connector_id == connector.id,
            PrinterBridgeReceipt.source_instance_id == source_instance_id,
            PrinterBridgeReceipt.receipt_kind == USAGE_RECEIPT_KIND,
            PrinterBridgeReceipt.receipt_id == payload.event_id,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise_error(409, conflict_error)
        return PrinterUsageResult(
            event_id=payload.event_id,
            deduplicated=True,
            consumed_weight_g=existing.consumed_weight_g,
        )

    if connector.material_system_id is None:
        raise_error(409, ERR_PRINTER_BRIDGE_NOT_CONFIGURED)
    physical_printer = await require_physical_printer(
        db, connector.user_id, connector.physical_printer_id
    )

    slot_rows = (
        await db.execute(
            select(MaterialSlot.provider_index, MaterialSlotAssignment.spool_id)
            .outerjoin(
                MaterialSlotAssignment,
                MaterialSlotAssignment.material_slot_id == MaterialSlot.id,
            )
            .where(MaterialSlot.material_system_id == connector.material_system_id)
        )
    ).all()
    assigned_spools = {int(index): spool_id for index, spool_id in slot_rows}
    if any(item.slot_index not in assigned_spools for item in payload.items):
        raise_error(404, ERR_MATERIAL_SLOT_NOT_FOUND)
    if any(assigned_spools[item.slot_index] != item.spool_id for item in payload.items):
        raise_error(409, ERR_MATERIAL_ASSIGNMENT_CONFLICT)

    spool_ids = {item.spool_id for item in payload.items}
    spools = list(
        (
            await db.execute(
                select(UserSpool)
                .where(UserSpool.id.in_(spool_ids), UserSpool.user_id == connector.user_id)
                .options(selectinload(UserSpool.filament).selectinload(Filament.brand))
                .with_for_update()
            )
        ).scalars()
    )
    spools_by_id = {spool.id: spool for spool in spools}
    if set(spools_by_id) != spool_ids:
        raise_error(404, ERR_ACCESS_DENIED)

    received_at = _now()
    occurred_at = _received_source_time(payload.observed_at, received_at)
    started_at = (
        min(_as_utc(payload.started_at), occurred_at) if payload.started_at is not None else None
    )
    if payload.event_type == "terminal":
        if payload.outcome is None:  # guarded by the request model
            raise ValueError("terminal usage event requires an outcome")
        status = PrintJobStatus(payload.outcome)
        job_payload_hash = _terminal_payload_hash(payload)
    else:
        status = PrintJobStatus.paused if "paused" in payload.reasons else PrintJobStatus.printing
        job_payload_hash = payload_hash
    print_job, should_record_usage = await ensure_provider_job_event(
        db,
        user_id=connector.user_id,
        physical_printer_id=connector.physical_printer_id,
        printer_name=physical_printer.name,
        source=print_job_source,
        source_ref=print_job_source_ref,
        event_key=f"{payload.event_type}:{payload.event_id}",
        payload_hash=job_payload_hash,
        status=status,
        title=payload.file_name or payload.job_id,
        file_name=payload.file_name,
        actual_duration_s=payload.duration_s,
        materials=[
            (spools_by_id[item.spool_id], f"slot:{item.slot_index}", None)
            for item in payload.items
        ],
        occurred_at=occurred_at,
        started_at=started_at,
        details={"reasons": payload.reasons, "adapter": adapter},
    )
    if not should_record_usage:
        consumed_weight_g = await confirmed_consumption_for_job(db, print_job.id)
        db.add(
            PrinterBridgeReceipt(
                connector_id=connector.id,
                source_instance_id=source_instance_id,
                receipt_kind=USAGE_RECEIPT_KIND,
                receipt_id=payload.event_id,
                payload_hash=payload_hash,
                consumed_weight_g=consumed_weight_g,
            )
        )
        await db.flush()
        return PrinterUsageResult(payload.event_id, True, consumed_weight_g)

    total_consumed = 0.0
    for item in payload.items:
        spool = spools_by_id[item.spool_id]
        filament = spool.filament
        density = (
            filament.density
            if filament is not None and filament.density and filament.density > 0
            else DEFAULT_DENSITY_G_CM3
        )
        diameter = (
            filament.diameter
            if filament is not None and filament.diameter and filament.diameter > 0
            else DEFAULT_DIAMETER_MM
        )
        reported_weight = (
            item.used_weight_g
            if item.used_weight_g is not None
            else _weight_from_length(item.used_length_mm or 0.0, density, diameter)
        )
        before = spool.used_weight_g
        spool.used_weight_g = min(spool.initial_weight_g, before + reported_weight)
        consumed = spool.used_weight_g - before
        total_consumed += consumed
        spool.last_used_at = received_at
        if spool.first_used_at is None:
            spool.first_used_at = received_at
        preset_id = await resolve_assigned_preset_id(
            db,
            user_id=spool.user_id,
            spool_id=spool.id,
            physical_printer_id=connector.physical_printer_id,
            material_system_id=connector.material_system_id,
            slot_index=item.slot_index,
        )
        await record_spool_usage(
            db,
            spool=spool,
            event_type=PresetUsageEventType.printer_report,
            delta_weight_g=consumed,
            device_id=connector.physical_printer_id,
            preset_id=preset_id,
            print_job_id=print_job.id,
            job_ref=f"printer_bridge:{connector.id}:{payload.event_id}:{spool.id}",
            reported_weight_g=reported_weight,
            meta={
                "adapter": adapter,
                "job_id": payload.job_id,
                "outcome": payload.outcome,
                "event_type": payload.event_type,
                "reasons": payload.reasons,
                "observed_at": occurred_at.isoformat(),
                "slot_index": item.slot_index,
                "file_name": payload.file_name,
                "duration_s": payload.duration_s,
                "used_length_mm": item.used_length_mm,
                "source_instance_id": source_instance_id,
            },
        )
        if spool.remaining_weight_g <= 0:
            spool.state = UserSpoolState.empty
            await clear_spool_gate_assignments(
                db, spool, source=PresetGateStateSource.provider_report
            )
            clear_spool_location_projection(spool)

    db.add(
        PrinterBridgeReceipt(
            connector_id=connector.id,
            source_instance_id=source_instance_id,
            receipt_kind=USAGE_RECEIPT_KIND,
            receipt_id=payload.event_id,
            payload_hash=payload_hash,
            consumed_weight_g=total_consumed,
        )
    )
    await db.flush()
    return PrinterUsageResult(payload.event_id, False, total_consumed)
