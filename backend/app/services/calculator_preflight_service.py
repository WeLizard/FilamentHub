"""Read-only material readiness for calculator jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isclose
from typing import Literal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.core.errors import ERR_SPOOL_NOT_ACCESSIBLE, raise_error
from app.models.calculator_profile import UserCalculatorProfile
from app.models.filament import Filament
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.calculator import (
    CalculatorPreflightLineResponse,
    CalculatorPreflightRequest,
    CalculatorPreflightResponse,
    CalculatorPreflightSpoolAllocation,
    CalculatorPreflightSpoolSuggestion,
    CalculatorPreflightStatus,
    CalculatorRemainingEvidence,
    CalculatorRemainingStatus,
)
from app.services.calculator_printer_compatibility_service import (
    calculate_printer_compatibility,
)
from app.services.crm_spool_reservation_service import active_reserved_weights

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


def _purchase_currency(spool: UserSpool, owner_currency: str | None) -> str | None:
    """Currency of what the spool cost, or ``None`` when it cannot be told.

    A spool recorded without one is priced in the money its owner works in. Calling it
    roubles instead adds a euro-priced spool to the rouble total and reports a number
    nobody can spend.
    """
    if spool.price is None:
        return None
    raw_currency = (spool.extra or {}).get("currency")
    if isinstance(raw_currency, str) and raw_currency:
        return raw_currency
    return owner_currency


def _normalized_material_type(value: str) -> str:
    return value.strip().casefold()


def _suggestion_relation(
    target: Filament,
    candidate: Filament,
) -> Literal[
    "same_filament", "same_line", "same_type_and_color", "same_material_type"
] | None:
    if candidate.id == target.id:
        return "same_filament"
    # A different diameter cannot go into the same printer at all: this is a cutoff,
    # not a sign of similarity.
    if not isclose(candidate.diameter, target.diameter, abs_tol=0.01):
        return None
    if target.line_id is not None and candidate.line_id == target.line_id:
        return "same_line"
    if (
        _normalized_material_type(candidate.material_type)
        == _normalized_material_type(target.material_type)
        and candidate.required_nozzle_hrc == target.required_nozzle_hrc
    ):
        # A part printed in another colour is a remake for anything the customer looks at,
        # so the same colour group ranks above a bare type match.
        if target.color_group is not None and candidate.color_group == target.color_group:
            return "same_type_and_color"
        return "same_material_type"
    return None


async def _suggestion_spool_ids_by_filament(
    db: AsyncSession,
    *,
    user_id: int,
    target_filament_ids: set[int],
) -> dict[int, list[int]]:
    if not target_filament_ids:
        return {}

    target = aliased(Filament)
    candidate = aliased(Filament)
    exact_match = candidate.id == target.id
    diameter_match = func.abs(candidate.diameter - target.diameter) <= 0.01
    same_line = and_(target.line_id.is_not(None), candidate.line_id == target.line_id)
    same_material_type = and_(
        func.lower(func.trim(candidate.material_type))
        == func.lower(func.trim(target.material_type)),
        candidate.required_nozzle_hrc.is_not_distinct_from(target.required_nozzle_hrc),
    )
    compatible = or_(
        exact_match,
        and_(diameter_match, or_(same_line, same_material_type)),
    )
    relation_rank = case(
        (exact_match, 0),
        (same_line, 1),
        (same_material_type, 2),
        else_=3,
    )
    reslice_group = case((exact_match, 0), else_=1)
    remaining = UserSpool.initial_weight_g - UserSpool.used_weight_g
    ranked = (
        select(
            target.id.label("target_filament_id"),
            UserSpool.id.label("spool_id"),
            reslice_group.label("reslice_group"),
            func.row_number()
            .over(
                partition_by=(target.id, reslice_group),
                order_by=(relation_rank, remaining.desc(), UserSpool.id),
            )
            .label("candidate_rank"),
        )
        .select_from(target)
        .join(candidate, compatible)
        .join(UserSpool, UserSpool.filament_id == candidate.id)
        .where(
            target.id.in_(target_filament_ids),
            UserSpool.user_id == user_id,
            UserSpool.state.in_((UserSpoolState.active, UserSpoolState.shelf)),
            remaining > 0,
        )
        .subquery()
    )
    rows = await db.execute(
        select(ranked.c.target_filament_id, ranked.c.spool_id).where(
            or_(
                and_(ranked.c.reslice_group == 0, ranked.c.candidate_rank <= 8),
                and_(ranked.c.reslice_group == 1, ranked.c.candidate_rank <= 6),
            )
        )
    )
    result: dict[int, list[int]] = {}
    for target_filament_id, spool_id in rows:
        result.setdefault(target_filament_id, []).append(spool_id)
    return result


def _spool_suggestions(
    *,
    target: Filament | None,
    candidate_spools: list[UserSpool],
    selected_spool_ids: set[int],
    expected_remaining: dict[int, float],
    reserved_by_spool: dict[int, float],
    remaining_evidence_by_spool: dict[int, _RemainingEvidence],
    selected_remaining_g: float,
    required_planned_g: float,
) -> list[CalculatorPreflightSpoolSuggestion]:
    if target is None or selected_remaining_g >= required_planned_g:
        return []

    exact_target = max(required_planned_g - selected_remaining_g, 0.0)
    suggestions: list[CalculatorPreflightSpoolSuggestion] = []
    for spool in candidate_spools:
        if (
            spool.id in selected_spool_ids
            or spool.filament is None
            or spool.state not in {UserSpoolState.active, UserSpoolState.shelf}
            or expected_remaining[spool.id] <= 0
        ):
            continue
        relation = _suggestion_relation(target, spool.filament)
        if relation is None:
            continue
        requires_reslice = relation != "same_filament"
        coverage_target = required_planned_g if requires_reslice else exact_target
        evidence = remaining_evidence_by_spool[spool.id]
        suggestions.append(
            CalculatorPreflightSpoolSuggestion(
                spool_id=spool.id,
                filament_id=spool.filament.id,
                relation=relation,
                requires_reslice=requires_reslice,
                remaining_g=_rounded(expected_remaining[spool.id]),
                reserved_elsewhere_g=_rounded(reserved_by_spool.get(spool.id, 0)),
                coverage_target_g=_rounded(coverage_target),
                covers_target=(
                    evidence.status == "known"
                    and expected_remaining[spool.id] >= coverage_target
                ),
                remaining_status=evidence.status,
                remaining_evidence=evidence.evidence,
                remaining_confidence=evidence.confidence,
                remaining_updated_at=evidence.observed_at,
            )
        )

    relation_priority = {
        "same_filament": 0,
        "same_line": 1,
        "same_type_and_color": 2,
        "same_material_type": 3,
    }
    remaining_priority = {"known": 0, "stale": 1, "unknown": 2}
    suggestions.sort(
        key=lambda item: (
            item.requires_reslice,
            relation_priority[item.relation],
            remaining_priority[item.remaining_status],
            not item.covers_target,
            -item.remaining_g,
            item.spool_id,
        )
    )
    exact = [item for item in suggestions if not item.requires_reslice][:8]
    replacements = [item for item in suggestions if item.requires_reslice][:6]
    return [*exact, *replacements]


async def calculate_material_preflight(
    db: AsyncSession,
    *,
    user_id: int,
    payload: CalculatorPreflightRequest,
) -> CalculatorPreflightResponse:
    """Check selected user spools without reserving or consuming them."""
    owner_currency = await db.scalar(
        select(UserCalculatorProfile.currency).where(
            UserCalculatorProfile.user_id == user_id
        )
    )
    requested_spool_ids = {spool_id for line in payload.lines for spool_id in line.spool_ids}
    requested_filament_ids = {
        line.filament_id for line in payload.lines if line.filament_id is not None
    }
    target_filaments: dict[int, Filament] = {}
    if requested_filament_ids:
        filament_rows = await db.execute(
            select(Filament).where(Filament.id.in_(requested_filament_ids))
        )
        target_filaments = {
            filament.id: filament for filament in filament_rows.scalars().all()
        }

    suggestion_ids_by_filament = await _suggestion_spool_ids_by_filament(
        db,
        user_id=user_id,
        target_filament_ids=set(target_filaments),
    )
    relevant_spool_ids = requested_spool_ids | {
        spool_id
        for spool_ids in suggestion_ids_by_filament.values()
        for spool_id in spool_ids
    }
    spools_by_id: dict[int, UserSpool] = {}
    if relevant_spool_ids:
        spool_rows = await db.execute(
            select(UserSpool)
            .options(selectinload(UserSpool.filament))
            .where(
                UserSpool.id.in_(relevant_spool_ids),
                UserSpool.user_id == user_id,
            )
        )
        spools_by_id = {spool.id: spool for spool in spool_rows.scalars().all()}
    missing = requested_spool_ids - set(spools_by_id)
    if missing:
        raise_error(
            404,
            ERR_SPOOL_NOT_ACCESSIBLE,
            params={"spool_id": min(missing)},
        )
    suggestion_spools_by_filament = {
        filament_id: [
            spools_by_id[spool_id]
            for spool_id in spool_ids
            if spool_id in spools_by_id
        ]
        for filament_id, spool_ids in suggestion_ids_by_filament.items()
    }

    repeats_by_job = {job.job_key: job.repeats for job in payload.print_jobs}
    latest_events = await _latest_usage_events(
        db,
        user_id=user_id,
        spool_ids=relevant_spool_ids,
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
    reserved_by_spool = await active_reserved_weights(
        db,
        user_id=user_id,
        spool_ids=relevant_spool_ids,
    )
    expected_remaining = {
        spool_id: max(
            0.0,
            spool.remaining_weight_g - reserved_by_spool.get(spool_id, 0),
        )
        for spool_id, spool in spools_by_id.items()
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
                    spool_suggestions=_spool_suggestions(
                        target=target_filaments.get(line.filament_id or 0),
                        candidate_spools=suggestion_spools_by_filament.get(
                            line.filament_id or 0, []
                        ),
                        selected_spool_ids=set(),
                        expected_remaining=expected_remaining,
                        reserved_by_spool=reserved_by_spool,
                        remaining_evidence_by_spool=remaining_evidence_by_spool,
                        selected_remaining_g=0,
                        required_planned_g=required_planned,
                    ),
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
                    reserved_elsewhere_g=_rounded(reserved_by_spool.get(spool.id, 0)),
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
                    spool_suggestions=_spool_suggestions(
                        target=target_filaments.get(line.filament_id or 0),
                        candidate_spools=suggestion_spools_by_filament.get(
                            line.filament_id or 0, []
                        ),
                        selected_spool_ids=set(line.spool_ids),
                        expected_remaining=expected_remaining,
                        reserved_by_spool=reserved_by_spool,
                        remaining_evidence_by_spool=remaining_evidence_by_spool,
                        selected_remaining_g=selected_remaining,
                        required_planned_g=required_planned,
                    ),
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
                purchase_currency = _purchase_currency(spool, owner_currency)
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
                spool_suggestions=_spool_suggestions(
                    target=target_filaments.get(line.filament_id or 0),
                    candidate_spools=suggestion_spools_by_filament.get(
                        line.filament_id or 0, []
                    ),
                    selected_spool_ids=set(line.spool_ids),
                    expected_remaining=expected_remaining,
                    reserved_by_spool=reserved_by_spool,
                    remaining_evidence_by_spool=remaining_evidence_by_spool,
                    selected_remaining_g=selected_remaining,
                    required_planned_g=required_planned,
                ),
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
    printer_compatibility = await calculate_printer_compatibility(
        db,
        user_id=user_id,
        payload=payload,
        target_filaments=target_filaments,
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
        printer_compatibility=printer_compatibility,
        lines=results,
    )
