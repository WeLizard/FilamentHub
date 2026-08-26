"""One provider-neutral source of truth for print attempts and their lifecycle."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_PRINT_JOB_INVALID_TRANSITION,
    ERR_PRINT_JOB_NOT_FOUND,
    ERR_PRINT_JOB_REFERENCE_INVALID,
    ERR_PRINT_JOB_REPLAY_CONFLICT,
    raise_error,
)
from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.filament import Filament
from app.models.orca_slice_report import OrcaSliceReport
from app.models.preset_usage_event import PresetUsageEvent
from app.models.print_job import PrintJob, PrintJobEvent, PrintJobMaterial, PrintJobStatus
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.schemas.print_job import (
    PrintJobCreate,
    PrintJobEventResponse,
    PrintJobListResponse,
    PrintJobMaterialResponse,
    PrintJobResponse,
    PrintJobTransitionCreate,
)

TERMINAL_STATUSES = {
    PrintJobStatus.completed,
    PrintJobStatus.cancelled,
    PrintJobStatus.failed,
}
ALLOWED_TRANSITIONS: dict[PrintJobStatus, set[PrintJobStatus]] = {
    PrintJobStatus.prepared: {
        PrintJobStatus.sent,
        PrintJobStatus.printing,
        PrintJobStatus.cancelled,
        PrintJobStatus.failed,
    },
    PrintJobStatus.sent: {
        PrintJobStatus.printing,
        PrintJobStatus.cancelled,
        PrintJobStatus.failed,
    },
    PrintJobStatus.printing: {
        PrintJobStatus.paused,
        PrintJobStatus.completed,
        PrintJobStatus.cancelled,
        PrintJobStatus.failed,
    },
    PrintJobStatus.paused: {
        PrintJobStatus.printing,
        PrintJobStatus.completed,
        PrintJobStatus.cancelled,
        PrintJobStatus.failed,
    },
    PrintJobStatus.completed: set(),
    PrintJobStatus.cancelled: set(),
    PrintJobStatus.failed: set(),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _job_load_options() -> tuple:
    return (
        selectinload(PrintJob.physical_printer),
        selectinload(PrintJob.calculator_history),
        selectinload(PrintJob.orca_slice_report),
        selectinload(PrintJob.events),
        selectinload(PrintJob.materials),
        selectinload(PrintJob.usage_events),
    )


async def _load_job(db: AsyncSession, *, user_id: int, job_id: int) -> PrintJob:
    job = await db.scalar(
        select(PrintJob)
        .where(PrintJob.id == job_id, PrintJob.user_id == user_id)
        .options(*_job_load_options())
    )
    if job is None:
        raise_error(404, ERR_PRINT_JOB_NOT_FOUND)
    return job


def _material_snapshot(spool: UserSpool) -> dict:
    filament = spool.filament
    brand = filament.brand if filament is not None else None
    filament_label = filament.name if filament is not None else None
    spool_name = " · ".join(
        part for part in (brand.name if brand is not None else None, filament_label) if part
    )
    return {
        "spool_name": spool_name or f"Spool #{spool.id}",
        "filament_name": filament_label,
        "material_type": filament.material_type if filament is not None else None,
        "color_hex": filament.color_hex if filament is not None else None,
    }


def _estimated_duration_from_calculation(
    calculation: CalculatorHistoryEntry | None, calculator_job_key: str | None
) -> float | None:
    if calculation is None:
        return None
    parsed = calculation.parsed_gcode or {}
    if parsed.get("format") == "calculator_batch_v1":
        jobs = [row for row in parsed.get("jobs", []) if isinstance(row, dict)]
        if calculator_job_key is not None:
            jobs = [row for row in jobs if row.get("job_key") == calculator_job_key]
        values = [(row.get("parsed_gcode") or {}).get("print_time_seconds") for row in jobs]
        numeric = [float(value) for value in values if isinstance(value, (int, float))]
        return sum(numeric) if numeric else None
    value = parsed.get("print_time_seconds")
    return float(value) if isinstance(value, (int, float)) else None


def _response(job: PrintJob) -> PrintJobResponse:
    return PrintJobResponse(
        id=job.id,
        logical_id=job.logical_id,
        physical_printer_id=job.physical_printer_id,
        printer_name=(
            job.physical_printer.name
            if job.physical_printer is not None
            else job.printer_name_snapshot
        ),
        calculator_history_id=job.calculator_history_id,
        calculation_title=(
            job.calculator_history.title
            if job.calculator_history is not None
            else job.calculation_title_snapshot
        ),
        calculator_job_key=job.calculator_job_key,
        orca_slice_report_id=job.orca_slice_report_id,
        file_name=(
            job.orca_slice_report.file_name
            if job.orca_slice_report is not None
            else job.file_name_snapshot
        ),
        title=job.title,
        status=job.status,
        source=job.source,
        estimated_duration_s=job.estimated_duration_s,
        actual_duration_s=job.actual_duration_s,
        confirmed_consumption_g=round(
            sum(event.delta_weight_g or 0.0 for event in job.usage_events), 4
        ),
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
        materials=[
            PrintJobMaterialResponse(
                id=material.id,
                spool_id=material.spool_id,
                material_line_key=material.material_line_key,
                tool_index=material.tool_index,
                planned_weight_g=material.planned_weight_g,
                spool_name=str(material.spool_snapshot.get("spool_name") or "Spool"),
                filament_name=material.spool_snapshot.get("filament_name"),
                material_type=material.spool_snapshot.get("material_type"),
                color_hex=material.spool_snapshot.get("color_hex"),
            )
            for material in job.materials
        ],
        events=[
            PrintJobEventResponse(
                id=event.id,
                status=event.status,
                source=event.source,
                note=(event.details or {}).get("note"),
                occurred_at=event.occurred_at,
                received_at=event.received_at,
            )
            for event in job.events
        ],
    )


async def list_print_jobs(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int | None,
    page: int,
    size: int,
) -> PrintJobListResponse:
    filters = [PrintJob.user_id == user_id]
    if physical_printer_id is not None:
        filters.append(PrintJob.physical_printer_id == physical_printer_id)
    total = await db.scalar(select(func.count()).select_from(PrintJob).where(*filters))
    jobs = list(
        (
            await db.execute(
                select(PrintJob)
                .where(*filters)
                .options(*_job_load_options())
                .order_by(PrintJob.created_at.desc(), PrintJob.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        .scalars()
        .unique()
    )
    return PrintJobListResponse(items=[_response(job) for job in jobs], total=total or 0)


async def get_print_job(db: AsyncSession, *, user_id: int, job_id: int) -> PrintJobResponse:
    return _response(await _load_job(db, user_id=user_id, job_id=job_id))


async def create_print_job(
    db: AsyncSession, *, user_id: int, payload: PrintJobCreate
) -> PrintJobResponse:
    # Serialize idempotent creates for one account. SQLite ignores FOR UPDATE;
    # PostgreSQL, which serves production, closes the no-row insertion race.
    await db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    payload_hash = _hash_payload(payload.model_dump(mode="json"))
    existing = await db.scalar(
        select(PrintJob).where(
            PrintJob.user_id == user_id,
            PrintJob.source == "manual",
            PrintJob.source_ref == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.source_payload_hash != payload_hash:
            raise_error(409, ERR_PRINT_JOB_REPLAY_CONFLICT)
        return _response(await _load_job(db, user_id=user_id, job_id=existing.id))

    printer = await db.scalar(
        select(UserPrinterDevice).where(
            UserPrinterDevice.id == payload.physical_printer_id,
            UserPrinterDevice.user_id == user_id,
        )
    )
    if printer is None:
        raise_error(404, ERR_ACCESS_DENIED)

    calculation = None
    if payload.calculator_history_id is not None:
        calculation = await db.scalar(
            select(CalculatorHistoryEntry).where(
                CalculatorHistoryEntry.id == payload.calculator_history_id,
                CalculatorHistoryEntry.user_id == user_id,
            )
        )
        if calculation is None:
            raise_error(409, ERR_PRINT_JOB_REFERENCE_INVALID)
        if payload.calculator_job_key is not None:
            parsed = calculation.parsed_gcode or {}
            known_keys = {
                row.get("job_key") for row in parsed.get("jobs", []) if isinstance(row, dict)
            }
            if payload.calculator_job_key not in known_keys:
                raise_error(409, ERR_PRINT_JOB_REFERENCE_INVALID)

    slice_report = None
    if payload.orca_slice_report_id is not None:
        slice_report = await db.scalar(
            select(OrcaSliceReport).where(
                OrcaSliceReport.id == payload.orca_slice_report_id,
                OrcaSliceReport.user_id == user_id,
            )
        )
        if slice_report is None or (
            slice_report.physical_printer_id is not None
            and slice_report.physical_printer_id != printer.id
        ):
            raise_error(409, ERR_PRINT_JOB_REFERENCE_INVALID)

    spool_ids = {item.spool_id for item in payload.materials}
    spools = list(
        (
            await db.execute(
                select(UserSpool)
                .where(UserSpool.id.in_(spool_ids), UserSpool.user_id == user_id)
                .options(selectinload(UserSpool.filament).selectinload(Filament.brand))
            )
        ).scalars()
    )
    spools_by_id = {spool.id: spool for spool in spools}
    if set(spools_by_id) != spool_ids:
        raise_error(404, ERR_ACCESS_DENIED)

    now = _now()
    job = PrintJob(
        user_id=user_id,
        physical_printer_id=printer.id,
        calculator_history_id=calculation.id if calculation is not None else None,
        calculator_job_key=payload.calculator_job_key,
        orca_slice_report_id=slice_report.id if slice_report is not None else None,
        title=payload.title,
        status=PrintJobStatus.prepared,
        source="manual",
        source_ref=payload.idempotency_key,
        source_payload_hash=payload_hash,
        printer_name_snapshot=printer.name,
        calculation_title_snapshot=calculation.title if calculation is not None else None,
        file_name_snapshot=slice_report.file_name if slice_report is not None else None,
        estimated_duration_s=(
            payload.estimated_duration_s
            if payload.estimated_duration_s is not None
            else _estimated_duration_from_calculation(calculation, payload.calculator_job_key)
        ),
    )
    db.add(job)
    await db.flush()
    for item in payload.materials:
        db.add(
            PrintJobMaterial(
                print_job_id=job.id,
                spool_id=item.spool_id,
                material_line_key=item.material_line_key,
                tool_index=item.tool_index,
                planned_weight_g=item.planned_weight_g,
                spool_snapshot=_material_snapshot(spools_by_id[item.spool_id]),
            )
        )
    db.add(
        PrintJobEvent(
            print_job_id=job.id,
            user_id=user_id,
            status=PrintJobStatus.prepared,
            source="user",
            event_key=f"create:{payload.idempotency_key}",
            payload_hash=payload_hash,
            occurred_at=now,
        )
    )
    await db.commit()
    return _response(await _load_job(db, user_id=user_id, job_id=job.id))


async def transition_print_job(
    db: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    payload: PrintJobTransitionCreate,
) -> PrintJobResponse:
    job = await db.scalar(
        select(PrintJob).where(PrintJob.id == job_id, PrintJob.user_id == user_id).with_for_update()
    )
    if job is None:
        raise_error(404, ERR_PRINT_JOB_NOT_FOUND)

    payload_hash = _hash_payload(payload.model_dump(mode="json"))
    event_key = f"user:{payload.idempotency_key}"
    existing = await db.scalar(
        select(PrintJobEvent).where(
            PrintJobEvent.print_job_id == job.id,
            PrintJobEvent.event_key == event_key,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise_error(409, ERR_PRINT_JOB_REPLAY_CONFLICT)
        return _response(await _load_job(db, user_id=user_id, job_id=job.id))

    if payload.status not in ALLOWED_TRANSITIONS[job.status]:
        raise_error(
            409,
            ERR_PRINT_JOB_INVALID_TRANSITION,
            params={"from": job.status.value, "to": payload.status.value},
        )

    now = _now()
    job.status = payload.status
    if payload.status == PrintJobStatus.printing and job.started_at is None:
        job.started_at = now
    if payload.status in TERMINAL_STATUSES:
        job.finished_at = now
    db.add(
        PrintJobEvent(
            print_job_id=job.id,
            user_id=user_id,
            status=payload.status,
            source="user",
            event_key=event_key,
            payload_hash=payload_hash,
            details={"note": payload.note} if payload.note else None,
            occurred_at=now,
        )
    )
    await db.commit()
    return _response(await _load_job(db, user_id=user_id, job_id=job.id))


async def _ensure_provider_job_materials(
    db: AsyncSession,
    *,
    job: PrintJob,
    materials: list[tuple[UserSpool, str | None, int | None]],
) -> None:
    existing = set(
        (
            await db.execute(
                select(
                    PrintJobMaterial.spool_id,
                    PrintJobMaterial.material_line_key,
                ).where(PrintJobMaterial.print_job_id == job.id)
            )
        ).all()
    )
    for spool, material_line_key, tool_index in materials:
        key = (spool.id, material_line_key)
        if key in existing:
            continue
        db.add(
            PrintJobMaterial(
                print_job_id=job.id,
                spool_id=spool.id,
                material_line_key=material_line_key,
                tool_index=tool_index,
                spool_snapshot=_material_snapshot(spool),
            )
        )
        existing.add(key)


async def ensure_provider_job_event(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    printer_name: str,
    source: str,
    source_ref: str,
    event_key: str,
    payload_hash: str,
    status: PrintJobStatus,
    title: str,
    file_name: str | None,
    actual_duration_s: float | None,
    materials: list[tuple[UserSpool, str | None, int | None]],
    occurred_at: datetime,
    started_at: datetime | None = None,
    details: dict | None = None,
) -> tuple[PrintJob, bool]:
    """Create or advance one provider job and reject terminal replays.

    The adapter owns transport replay. This job-level identity additionally
    prevents a terminal retry under a different transport event from consuming
    material twice, while checkpoints may add new deltas to the same attempt.
    """
    if status not in {PrintJobStatus.printing, PrintJobStatus.paused, *TERMINAL_STATUSES}:
        raise ValueError("unsupported provider job status")
    existing = await db.scalar(
        select(PrintJob)
        .where(
            PrintJob.user_id == user_id,
            PrintJob.source == source,
            PrintJob.source_ref == source_ref,
        )
        .with_for_update()
    )
    if existing is not None:
        previous_status = existing.status
        if existing.status in TERMINAL_STATUSES:
            if existing.status != status or existing.source_payload_hash != payload_hash:
                raise_error(409, ERR_PRINT_JOB_REPLAY_CONFLICT)
            return existing, False
        if status in TERMINAL_STATUSES:
            if status not in ALLOWED_TRANSITIONS[existing.status]:
                raise_error(409, ERR_PRINT_JOB_REPLAY_CONFLICT)
            existing.status = status
            existing.source_payload_hash = payload_hash
            existing.actual_duration_s = actual_duration_s
            existing.finished_at = occurred_at
        elif status != existing.status:
            if status not in ALLOWED_TRANSITIONS[existing.status]:
                raise_error(409, ERR_PRINT_JOB_REPLAY_CONFLICT)
            existing.status = status
            if status == PrintJobStatus.printing and existing.started_at is None:
                existing.started_at = started_at or occurred_at
        if existing.file_name_snapshot is None and file_name is not None:
            existing.file_name_snapshot = file_name
        if existing.started_at is None and started_at is not None:
            existing.started_at = started_at
        await _ensure_provider_job_materials(db, job=existing, materials=materials)
        if status != previous_status:
            # Lifecycle events stay compact: periodic/tool checkpoints do not
            # duplicate the current state, while pause/resume/terminal do.
            db.add(
                PrintJobEvent(
                    print_job_id=existing.id,
                    user_id=user_id,
                    status=status,
                    source=source,
                    event_key=event_key,
                    payload_hash=payload_hash,
                    details=details,
                    occurred_at=occurred_at,
                )
            )
        await db.flush()
        return existing, True

    if status in TERMINAL_STATUSES:
        source_payload_hash = payload_hash
        finished_at = occurred_at
    else:
        source_payload_hash = _hash_payload({"source": source, "source_ref": source_ref})
        finished_at = None
    if started_at is None and status in {PrintJobStatus.printing, PrintJobStatus.paused}:
        started_at = occurred_at
    job = PrintJob(
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        title=title,
        status=status,
        source=source,
        source_ref=source_ref,
        source_payload_hash=source_payload_hash,
        printer_name_snapshot=printer_name,
        file_name_snapshot=file_name,
        actual_duration_s=actual_duration_s,
        started_at=started_at,
        finished_at=finished_at,
    )
    db.add(job)
    await db.flush()
    await _ensure_provider_job_materials(db, job=job, materials=materials)
    db.add(
        PrintJobEvent(
            print_job_id=job.id,
            user_id=user_id,
            status=status,
            source=source,
            event_key=event_key,
            payload_hash=payload_hash,
            details=details,
            occurred_at=occurred_at,
        )
    )
    await db.flush()
    return job, True


async def confirmed_consumption_for_job(db: AsyncSession, job_id: int) -> float:
    value = await db.scalar(
        select(func.coalesce(func.sum(PresetUsageEvent.delta_weight_g), 0.0)).where(
            PresetUsageEvent.print_job_id == job_id
        )
    )
    return float(value or 0.0)
