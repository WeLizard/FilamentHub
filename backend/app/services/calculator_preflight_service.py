"""Read-only material readiness for calculator jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_SPOOL_NOT_ACCESSIBLE, raise_error
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.calculator import (
    CalculatorPreflightLineResponse,
    CalculatorPreflightRequest,
    CalculatorPreflightResponse,
    CalculatorPreflightSpoolAllocation,
    CalculatorPreflightStatus,
    CalculatorRemainingEvidence,
    CalculatorRemainingStatus,
)

_REMAINING_STALE_AFTER = timedelta(days=30)
_IMPORTED_SPOOL_SOURCES = {
    "csv_import",
    "custom_csv",
    "octoprint_spoolmanager",
    "orca_import",
    "spool_compat",
}

_STATUS_PRIORITY: dict[CalculatorPreflightStatus, int] = {
    "ready": 0,
    "ready_with_change": 1,
    "ready_at_risk": 2,
    "needs_clarification": 3,
    "insufficient": 4,
    "conflict": 5,
}


@dataclass(frozen=True)
class _RemainingEvidence:
    status: CalculatorRemainingStatus
    evidence: CalculatorRemainingEvidence
    confidence: Literal["high", "medium", "low"]
    observed_at: datetime


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _remaining_evidence(
    spool: UserSpool,
    event: PresetUsageEvent | None,
    *,
    now: datetime,
) -> _RemainingEvidence:
    if event is None:
        observed_at = _as_utc(spool.updated_at or spool.created_at)
        if spool.source in _IMPORTED_SPOOL_SOURCES:
            evidence: CalculatorRemainingEvidence = "import"
            confidence = "medium"
        else:
            evidence = "intake"
            confidence = "low"
        status: CalculatorRemainingStatus = "known"
    else:
        observed_at = _as_utc(event.created_at)
        if event.event_type == PresetUsageEventType.reconcile_adjust:
            evidence = "measurement"
            confidence = "high"
            status = "known"
        elif event.event_type == PresetUsageEventType.printer_report:
            evidence = "provider_report"
            confidence = "medium"
            status = "known"
        elif event.event_type == PresetUsageEventType.manual_adjust:
            evidence = "manual_update"
            confidence = "medium"
            status = "known"
        else:
            evidence = "estimate"
            confidence = "low"
            status = "unknown"

        if (event.meta or {}).get("possible_repeat"):
            status = "unknown"

    can_drift = spool.used_weight_g > 0 or spool.state == UserSpoolState.active
    if status == "known" and can_drift and now - observed_at > _REMAINING_STALE_AFTER:
        status = "stale"
    return _RemainingEvidence(
        status=status,
        evidence=evidence,
        confidence=confidence,
        observed_at=observed_at,
    )


async def _latest_usage_events(
    db: AsyncSession,
    *,
    user_id: int,
    spool_ids: set[int],
) -> dict[int, PresetUsageEvent]:
    if not spool_ids:
        return {}
    latest_ids = (
        select(
            PresetUsageEvent.spool_id.label("spool_id"),
            func.max(PresetUsageEvent.id).label("event_id"),
        )
        .where(
            PresetUsageEvent.user_id == user_id,
            PresetUsageEvent.spool_id.in_(spool_ids),
        )
        .group_by(PresetUsageEvent.spool_id)
        .subquery()
    )
    rows = await db.execute(
        select(PresetUsageEvent).join(
            latest_ids,
            PresetUsageEvent.id == latest_ids.c.event_id,
        )
    )
    return {event.spool_id: event for event in rows.scalars() if event.spool_id is not None}


def _rounded(value: float) -> float:
    return round(max(0.0, value), 3)


def _purchase_currency(spool: UserSpool) -> str | None:
    if spool.price is None:
        return None
    raw_currency = (spool.extra or {}).get("currency")
    return raw_currency if isinstance(raw_currency, str) and raw_currency else "RUB"


async def calculate_material_preflight(
    db: AsyncSession,
    *,
    user_id: int,
    payload: CalculatorPreflightRequest,
) -> CalculatorPreflightResponse:
    """Check selected user spools without reserving or consuming them."""
    requested_spool_ids = {
        spool_id for line in payload.lines for spool_id in line.spool_ids
    }
    spools_by_id: dict[int, UserSpool] = {}
    if requested_spool_ids:
        rows = await db.execute(
            select(UserSpool).where(
                UserSpool.id.in_(requested_spool_ids),
                UserSpool.user_id == user_id,
            )
        )
        spools_by_id = {spool.id: spool for spool in rows.scalars().all()}
        missing = requested_spool_ids - set(spools_by_id)
        if missing:
            raise_error(
                404,
                ERR_SPOOL_NOT_ACCESSIBLE,
                params={"spool_id": min(missing)},
            )

    repeats_by_job = {job.job_key: job.repeats for job in payload.print_jobs}
    latest_events = await _latest_usage_events(
        db,
        user_id=user_id,
        spool_ids=requested_spool_ids,
    )
    now = datetime.now(timezone.utc)
    remaining_evidence_by_spool = {
        spool_id: _remaining_evidence(
            spool,
            latest_events.get(spool_id),
            now=now,
        )
        for spool_id, spool in spools_by_id.items()
    }
    expected_remaining = {
        spool_id: spool.remaining_weight_g for spool_id, spool in spools_by_id.items()
    }

    results: list[CalculatorPreflightLineResponse] = []
    total_base = 0.0
    total_buffer = 0.0

    for line in payload.lines:
        multiplier = (
            repeats_by_job[line.job_key or ""] if repeats_by_job else payload.quantity
        )
        required_base = line.weight_g * multiplier
        required_length = line.length_mm * multiplier if line.length_mm is not None else None
        required_volume = line.volume_cm3 * multiplier if line.volume_cm3 is not None else None
        safety_buffer = required_base * payload.safety_buffer_percent / 100.0
        required_planned = required_base + safety_buffer
        total_base += required_base
        total_buffer += safety_buffer

        if not line.spool_ids:
            results.append(
                CalculatorPreflightLineResponse(
                    line_id=line.line_id,
                    job_key=line.job_key,
                    tool_index=line.tool_index,
                    label=line.label,
                    filament_id=line.filament_id,
                    status="needs_clarification",
                    evidence_source=line.evidence_source,
                    mapping_source=line.mapping_source,
                    mapping_confidence=line.mapping_confidence,
                    required_base_g=_rounded(required_base),
                    required_length_mm=_rounded(required_length) if required_length is not None else None,
                    required_volume_cm3=_rounded(required_volume) if required_volume is not None else None,
                    safety_buffer_g=_rounded(safety_buffer),
                    required_planned_g=_rounded(required_planned),
                    selected_remaining_g=0,
                    expected_after_g=0,
                    shortfall_base_g=_rounded(required_base),
                    shortfall_buffer_g=_rounded(safety_buffer),
                    change_count=0,
                    requires_spool_change=False,
                    purchase_cost_complete=False,
                )
            )
            continue

        allocations: list[CalculatorPreflightSpoolAllocation] = []
        has_conflict = False
        has_uncertain_remaining = False
        selected_remaining = 0.0
        for spool_id in line.spool_ids:
            spool = spools_by_id[spool_id]
            remaining_evidence = remaining_evidence_by_spool[spool.id]
            issues: list[str] = []
            if line.filament_id is not None and spool.filament_id != line.filament_id:
                issues.append("material_mismatch")
            if spool.state in {UserSpoolState.archived, UserSpoolState.empty}:
                issues.append("unavailable_state")
            if expected_remaining[spool.id] <= 0:
                issues.append("empty")
            structural_issues = bool(issues)
            if remaining_evidence.status == "stale":
                issues.append("stale_remaining")
                has_uncertain_remaining = has_uncertain_remaining or expected_remaining[spool.id] > 0
            elif remaining_evidence.status == "unknown":
                issues.append("unknown_remaining")
                has_uncertain_remaining = has_uncertain_remaining or expected_remaining[spool.id] > 0
            if structural_issues:
                has_conflict = True
            elif remaining_evidence.status == "known":
                selected_remaining += expected_remaining[spool.id]
            allocations.append(
                CalculatorPreflightSpoolAllocation(
                    spool_id=spool.id,
                    filament_id=spool.filament_id,
                    state=spool.state.value,
                    remaining_before_g=_rounded(expected_remaining[spool.id]),
                    planned_coverage_g=0,
                    expected_consumption_g=0,
                    expected_after_g=_rounded(expected_remaining[spool.id]),
                    remaining_status=remaining_evidence.status,
                    remaining_evidence=remaining_evidence.evidence,
                    remaining_confidence=remaining_evidence.confidence,
                    remaining_updated_at=remaining_evidence.observed_at,
                    last_used_at=spool.last_used_at,
                    issues=issues,
                )
            )

        if has_conflict:
            results.append(
                CalculatorPreflightLineResponse(
                    line_id=line.line_id,
                    job_key=line.job_key,
                    tool_index=line.tool_index,
                    label=line.label,
                    filament_id=line.filament_id,
                    status="conflict",
                    evidence_source=line.evidence_source,
                    mapping_source=line.mapping_source,
                    mapping_confidence=line.mapping_confidence,
                    required_base_g=_rounded(required_base),
                    required_length_mm=_rounded(required_length) if required_length is not None else None,
                    required_volume_cm3=_rounded(required_volume) if required_volume is not None else None,
                    safety_buffer_g=_rounded(safety_buffer),
                    required_planned_g=_rounded(required_planned),
                    selected_remaining_g=_rounded(selected_remaining),
                    expected_after_g=_rounded(selected_remaining),
                    shortfall_base_g=_rounded(max(required_base - selected_remaining, 0)),
                    shortfall_buffer_g=_rounded(
                        max(required_planned - max(selected_remaining, required_base), 0)
                    ),
                    change_count=0,
                    requires_spool_change=False,
                    purchase_cost_complete=False,
                    allocations=allocations,
                )
            )
            continue

        planned_left = required_planned
        base_left = required_base
        base_spools_used = 0
        purchase_cost_by_currency: dict[str, float] = {}
        purchase_cost_complete = True
        for allocation in allocations:
            spool_id = allocation.spool_id
            spool = spools_by_id[spool_id]
            if allocation.remaining_status != "known":
                purchase_cost_complete = False
                continue
            remaining_before = expected_remaining[spool_id]
            planned_coverage = min(remaining_before, planned_left)
            expected_consumption = min(remaining_before, base_left)
            expected_remaining[spool_id] -= expected_consumption
            planned_left -= planned_coverage
            base_left -= expected_consumption
            if expected_consumption > 0:
                base_spools_used += 1
                allocation.sequence_index = base_spools_used
                purchase_currency = _purchase_currency(spool)
                if spool.price is None or spool.initial_weight_g <= 0 or purchase_currency is None:
                    purchase_cost_complete = False
                else:
                    unit_cost = spool.price / spool.initial_weight_g
                    expected_cost = unit_cost * expected_consumption
                    allocation.purchase_currency = purchase_currency
                    allocation.unit_purchase_cost_per_g = _rounded(unit_cost)
                    allocation.expected_purchase_cost = _rounded(expected_cost)
                    purchase_cost_by_currency[purchase_currency] = (
                        purchase_cost_by_currency.get(purchase_currency, 0.0) + expected_cost
                    )
            allocation.planned_coverage_g = _rounded(planned_coverage)
            allocation.expected_consumption_g = _rounded(expected_consumption)
            allocation.expected_after_g = _rounded(expected_remaining[spool_id])

        shortfall_base = max(required_base - selected_remaining, 0)
        shortfall_buffer = max(required_planned - max(selected_remaining, required_base), 0)
        if base_left > 0:
            purchase_cost_complete = False
        if selected_remaining < required_base and has_uncertain_remaining:
            line_status: CalculatorPreflightStatus = "needs_clarification"
        elif selected_remaining < required_base:
            line_status = "insufficient"
        elif selected_remaining < required_planned:
            line_status = "ready_at_risk"
        elif base_spools_used > 1:
            line_status = "ready_with_change"
        else:
            line_status = "ready"

        results.append(
            CalculatorPreflightLineResponse(
                line_id=line.line_id,
                job_key=line.job_key,
                tool_index=line.tool_index,
                label=line.label,
                filament_id=line.filament_id,
                status=line_status,
                evidence_source=line.evidence_source,
                mapping_source=line.mapping_source,
                mapping_confidence=line.mapping_confidence,
                required_base_g=_rounded(required_base),
                required_length_mm=_rounded(required_length) if required_length is not None else None,
                required_volume_cm3=_rounded(required_volume) if required_volume is not None else None,
                safety_buffer_g=_rounded(safety_buffer),
                required_planned_g=_rounded(required_planned),
                selected_remaining_g=_rounded(selected_remaining),
                expected_after_g=_rounded(
                    sum(
                        expected_remaining[spool_id]
                        for spool_id in line.spool_ids
                        if remaining_evidence_by_spool[spool_id].status == "known"
                    )
                ),
                shortfall_base_g=_rounded(shortfall_base),
                shortfall_buffer_g=_rounded(shortfall_buffer),
                change_count=max(0, base_spools_used - 1),
                requires_spool_change=base_spools_used > 1,
                purchase_cost_by_currency={
                    currency: _rounded(cost)
                    for currency, cost in purchase_cost_by_currency.items()
                },
                purchase_cost_complete=purchase_cost_complete,
                allocations=allocations,
            )
        )

    overall_status = max(
        (line.status for line in results),
        key=lambda status: _STATUS_PRIORITY[status],
    )
    total_purchase_cost_by_currency: dict[str, float] = {}
    for line in results:
        for currency, cost in line.purchase_cost_by_currency.items():
            total_purchase_cost_by_currency[currency] = (
                total_purchase_cost_by_currency.get(currency, 0.0) + cost
            )
    return CalculatorPreflightResponse(
        status=overall_status,
        safety_buffer_percent=payload.safety_buffer_percent,
        required_base_g=_rounded(total_base),
        safety_buffer_g=_rounded(total_buffer),
        required_planned_g=_rounded(total_base + total_buffer),
        purchase_cost_by_currency={
            currency: _rounded(cost)
            for currency, cost in total_purchase_cost_by_currency.items()
        },
        purchase_cost_complete=all(line.purchase_cost_complete for line in results),
        lines=results,
    )
