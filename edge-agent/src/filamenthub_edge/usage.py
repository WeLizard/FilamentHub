"""Conservative conversion of cumulative provider counters into usage evidence."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from .providers.base import ProviderSnapshot
from .state import EdgeState

ACTIVE_STATES = {"printing", "paused"}
TERMINAL_OUTCOMES = {
    "complete": "completed",
    "cancelled": "cancelled",
    "error": "failed",
}
CHECKPOINT_INTERVAL_S = 300.0
COUNTER_EPSILON_MM = 0.001
LifecycleCheckpointReason = Literal["disconnect", "shutdown"]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _route(state: EdgeState, snapshot: ProviderSnapshot) -> dict[str, int] | None:
    desired = state.desired_snapshot or {}
    desired_slots = desired.get("slots")
    if not isinstance(desired_slots, list):
        return None
    assignments: dict[int, int] = {}
    for slot in desired_slots:
        if not isinstance(slot, dict):
            continue
        index = slot.get("index")
        spool = slot.get("spool")
        spool_id = spool.get("id") if isinstance(spool, dict) else None
        if isinstance(index, int) and isinstance(spool_id, int) and spool_id > 0:
            assignments[index] = spool_id

    active_indices: list[int] = []
    for slot in snapshot.slots:
        if not isinstance(slot, dict) or slot.get("active_feed") is not True:
            continue
        provider_index = slot.get("provider_index")
        if isinstance(provider_index, int) and not isinstance(provider_index, bool):
            active_indices.append(provider_index)
    if len(active_indices) == 1:
        index = active_indices[0]
        spool_id = assignments.get(index)
        return {"slot_index": index, "spool_id": spool_id} if spool_id is not None else None

    # A provider without slot topology is still a complete bridge when the
    # material system has one unambiguous desired feed.
    if not snapshot.slots and len(assignments) == 1:
        index, spool_id = next(iter(assignments.items()))
        return {"slot_index": index, "spool_id": spool_id}
    return None


def _new_tracker(
    state: EdgeState,
    usage: dict[str, Any],
    route: dict[str, int] | None,
    observed_at: str,
    *,
    terminal_emitted: bool = False,
) -> dict[str, Any]:
    return {
        "job_id": f"{state.instance_id}:{uuid.uuid4().hex}",
        "file_name": usage.get("file_name"),
        "started_at": observed_at,
        "last_state": usage.get("state"),
        "last_filament_used_mm": float(usage["filament_used_mm"]),
        "last_print_duration_s": float(usage.get("print_duration_s") or 0.0),
        "last_total_duration_s": float(usage.get("total_duration_s") or 0.0),
        "last_emitted_print_duration_s": float(usage.get("print_duration_s") or 0.0),
        "route": route,
        "pending_length_mm": 0.0,
        "terminal_emitted": terminal_emitted,
    }


def _same_job(tracker: dict[str, Any], usage: dict[str, Any]) -> bool:
    previous_file = tracker.get("file_name")
    current_file = usage.get("file_name")
    if previous_file and current_file and previous_file != current_file:
        return False
    previous_counter = _number(tracker.get("last_filament_used_mm"))
    current_counter = _number(usage.get("filament_used_mm"))
    if previous_counter is None or current_counter is None:
        return False
    return current_counter + COUNTER_EPSILON_MM >= previous_counter


def _event(
    tracker: dict[str, Any],
    *,
    event_type: str,
    observed_at: str,
    route: dict[str, int] | None,
    length_mm: float,
    reasons: list[str],
    outcome: str | None,
    duration_s: float | None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if route is not None and length_mm > COUNTER_EPSILON_MM:
        items.append(
            {
                "slot_index": route["slot_index"],
                "spool_id": route["spool_id"],
                "used_length_mm": length_mm,
            }
        )
    result: dict[str, Any] = {
        "job_id": tracker["job_id"],
        "event_type": event_type,
        "reasons": reasons,
        "observed_at": observed_at,
        "started_at": tracker["started_at"],
        "items": items,
    }
    if tracker.get("file_name"):
        result["file_name"] = tracker["file_name"]
    if outcome is not None:
        result["outcome"] = outcome
    if duration_s is not None:
        result["duration_s"] = duration_s
    return result


def capture_usage_events(
    state: EdgeState,
    snapshot: ProviderSnapshot,
    *,
    observed_at: str,
    checkpoint_reason: LifecycleCheckpointReason | None = None,
) -> list[dict[str, Any]]:
    """Advance local evidence and return only unambiguous usage events.

    A counter delta is attributed only when both ends of the interval point to
    the same desired physical spool. Route changes intentionally drop the one
    ambiguous polling interval instead of charging the wrong spool.
    """
    usage = snapshot.usage
    if not isinstance(usage, dict):
        return []
    raw_state = str(usage.get("state") or "").strip().lower()
    counter = _number(usage.get("filament_used_mm"))
    if counter is None or counter < 0:
        return []
    usage = dict(usage)
    usage["filament_used_mm"] = counter
    current_route = _route(state, snapshot)
    tracker = state.usage_tracker

    if raw_state == "standby":
        state.usage_tracker = None
        return []

    if raw_state not in ACTIVE_STATES and raw_state not in TERMINAL_OUTCOMES:
        return []

    if tracker is None:
        state.usage_tracker = _new_tracker(
            state,
            usage,
            current_route,
            observed_at,
            terminal_emitted=raw_state in TERMINAL_OUTCOMES,
        )
        return []

    if tracker.get("terminal_emitted") or not _same_job(tracker, usage):
        if raw_state in ACTIVE_STATES:
            state.usage_tracker = _new_tracker(state, usage, current_route, observed_at)
        elif raw_state in TERMINAL_OUTCOMES:
            state.usage_tracker = _new_tracker(
                state,
                usage,
                current_route,
                observed_at,
                terminal_emitted=True,
            )
        return []

    previous_counter = float(tracker["last_filament_used_mm"])
    delta = max(counter - previous_counter, 0.0)
    previous_route = tracker.get("route")
    pending = float(tracker.get("pending_length_mm") or 0.0)
    events: list[dict[str, Any]] = []
    route_changed = previous_route != current_route
    current_print_duration = float(usage.get("print_duration_s") or 0.0)
    total_duration = _number(usage.get("total_duration_s"))

    if route_changed:
        if previous_route is not None and pending > COUNTER_EPSILON_MM:
            reason = "spool_change"
            if current_route is None:
                reason = "filament_change"
            elif previous_route.get("slot_index") != current_route.get("slot_index"):
                reason = "tool_change"
            events.append(
                _event(
                    tracker,
                    event_type="checkpoint",
                    observed_at=observed_at,
                    route=previous_route,
                    length_mm=pending,
                    reasons=[reason],
                    outcome=None,
                    duration_s=total_duration,
                )
            )
        # The latest delta spans the unknown route-change moment and is not safe
        # to attribute to either physical spool.
        pending = 0.0
        tracker["last_emitted_print_duration_s"] = current_print_duration
    elif current_route is not None:
        pending += delta

    previous_state = tracker.get("last_state")
    terminal_outcome = TERMINAL_OUTCOMES.get(raw_state)
    if terminal_outcome is not None:
        events.append(
            _event(
                tracker,
                event_type="terminal",
                observed_at=observed_at,
                route=current_route if not route_changed else None,
                length_mm=pending if not route_changed else 0.0,
                reasons=["terminal"],
                outcome=terminal_outcome,
                duration_s=total_duration,
            )
        )
        pending = 0.0
        tracker["terminal_emitted"] = True
    elif checkpoint_reason is not None and pending > COUNTER_EPSILON_MM:
        events.append(
            _event(
                tracker,
                event_type="checkpoint",
                observed_at=observed_at,
                route=current_route,
                length_mm=pending,
                reasons=[checkpoint_reason],
                outcome=None,
                duration_s=total_duration,
            )
        )
        pending = 0.0
        tracker["last_emitted_print_duration_s"] = current_print_duration
    elif (
        raw_state == "paused"
        and previous_state != "paused"
        and pending > COUNTER_EPSILON_MM
    ):
        events.append(
            _event(
                tracker,
                event_type="checkpoint",
                observed_at=observed_at,
                route=current_route,
                length_mm=pending,
                reasons=["paused"],
                outcome=None,
                duration_s=total_duration,
            )
        )
        pending = 0.0
        tracker["last_emitted_print_duration_s"] = current_print_duration
    elif (
        pending > COUNTER_EPSILON_MM
        and current_print_duration
        - float(tracker.get("last_emitted_print_duration_s") or 0.0)
        >= CHECKPOINT_INTERVAL_S
    ):
        events.append(
            _event(
                tracker,
                event_type="checkpoint",
                observed_at=observed_at,
                route=current_route,
                length_mm=pending,
                reasons=["periodic"],
                outcome=None,
                duration_s=total_duration,
            )
        )
        pending = 0.0
        tracker["last_emitted_print_duration_s"] = current_print_duration

    tracker["last_state"] = raw_state
    tracker["last_filament_used_mm"] = counter
    tracker["last_print_duration_s"] = current_print_duration
    tracker["last_total_duration_s"] = float(total_duration or 0.0)
    tracker["route"] = current_route
    tracker["pending_length_mm"] = pending
    state.usage_tracker = tracker
    return events


def capture_pending_usage_event(
    state: EdgeState,
    *,
    observed_at: str,
    reason: LifecycleCheckpointReason,
) -> list[dict[str, Any]]:
    """Flush only evidence already attributed by a previous provider observation."""
    tracker = state.usage_tracker
    if (
        not isinstance(tracker, dict)
        or tracker.get("terminal_emitted") is True
        or tracker.get("last_state") not in ACTIVE_STATES
    ):
        return []
    route = tracker.get("route")
    pending = _number(tracker.get("pending_length_mm"))
    if not isinstance(route, dict) or pending is None or pending <= COUNTER_EPSILON_MM:
        return []
    event = _event(
        tracker,
        event_type="checkpoint",
        observed_at=observed_at,
        route=route,
        length_mm=pending,
        reasons=[reason],
        outcome=None,
        duration_s=_number(tracker.get("last_total_duration_s")),
    )
    tracker["pending_length_mm"] = 0.0
    tracker["last_emitted_print_duration_s"] = float(
        _number(tracker.get("last_print_duration_s")) or 0.0
    )
    state.usage_tracker = tracker
    return [event]
