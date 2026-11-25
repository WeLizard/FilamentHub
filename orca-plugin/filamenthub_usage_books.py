"""Usage books for a printer that reports one running filament counter.

A Flashforge printer gives the slicer's estimate scaled by progress; Klipper
gives the length its extruder has moved. Either way the plugin sees one number
that grows during a job and has to decide which spool each stretch of it is
charged to. This file keeps those books; it does not know which printer the
number came from.

A reading is a dictionary: ``state`` (``standby``, ``printing``, ``paused``,
``complete``, ``cancelled`` or ``error``), ``filament_used_mm``, and optionally
``file_name``, ``duration_s`` (time spent printing) and ``estimate_source``
(set when nothing measured the figure).

FH Edge keeps the same books (edge-agent ``usage.py``). The two are held to one
shared print scenario so they cannot drift apart.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import uuid

_COUNTER_USAGE_OUTCOMES = {
    "complete": "completed",
    "cancelled": "cancelled",
    "error": "failed",
}
# A long print is charged in parts, so a lost end does not lose all of it.
COUNTER_USAGE_CHECKPOINT_S = 300.0
_COUNTER_USAGE_EPSILON_MM = 0.001


def counter_usage_route(slots, desired):
    """The spool the site put in the one slot that is feeding, and why not.

    Returns ``(route, issue)``; exactly one of them is None.
    """
    assignments = {}
    for slot in (desired.get("slots") if isinstance(desired, dict) else None) or []:
        if not isinstance(slot, dict):
            continue
        index = slot.get("index")
        spool = slot.get("spool")
        spool_id = spool.get("id") if isinstance(spool, dict) else None
        if type(index) is int and type(spool_id) is int and spool_id > 0:
            route = {"slot_index": index, "spool_id": spool_id}
            for key in ("usage_route_proof", "assignment_revision"):
                if slot.get(key) is not None:
                    route[key] = slot[key]
            assignments[index] = route
    feeding = [
        slot["provider_index"] for slot in slots or [] if slot.get("active_feed") is True
    ]
    if not assignments:
        return None, {"reason": "no_spool_assigned"}
    if len(feeding) == 1:
        if feeding[0] in assignments:
            return assignments[feeding[0]], None
        return None, {"reason": "slot_without_spool", "slot_index": feeding[0]}
    # A printer whose feed could not be read still has one unambiguous spool
    # when the site knows of exactly one.
    if not slots and len(assignments) == 1:
        return next(iter(assignments.values())), None
    return None, {"reason": "active_slot_unknown"}


def _counter_usage_feed(route):
    """What must stay the same for a stretch to belong to one spool.

    ``feed_mark`` is whatever the printer offers that moves when the feed was
    switched, such as a count of tool changes: a switch away and back between
    two readings leaves the slot the same and the mark different.
    """
    if route is None:
        return None
    return route["slot_index"], route["spool_id"], route.get("feed_mark")


def _counter_usage_event(tracker, event_type, observed_at, route, length_mm, reason, outcome):
    sequence = tracker["segment_sequence"]
    tracker["segment_sequence"] = sequence + 1
    items = []
    if route is not None and length_mm > _COUNTER_USAGE_EPSILON_MM:
        proof = route.get("usage_route_proof")
        item = {
            "slot_index": route["slot_index"],
            "spool_id": route["spool_id"],
            "used_length_mm": length_mm,
            "evidence": "route_proof" if proof is not None else "current_assignment",
        }
        if proof is not None:
            item["usage_route_proof"] = proof
        if tracker.get("estimate_source"):
            # The printer computed this figure; nothing measured it.
            item["consumption_kind"] = "estimated"
            item["estimate_source"] = tracker["estimate_source"]
        items.append(item)
        tracker["charged"] = True
    event = {
        "contract_version": 2,
        "job_id": tracker["job_id"],
        "segment_sequence": sequence,
        "event_type": event_type,
        "reasons": [reason],
        "observed_at": observed_at,
        "started_at": tracker["started_at"],
        "items": items,
    }
    if tracker.get("file_name"):
        event["file_name"] = tracker["file_name"]
    if outcome is not None:
        event["outcome"] = outcome
    if tracker.get("duration_s") is not None:
        event["duration_s"] = tracker["duration_s"]
    return event


def flush_counter_usage(state, observed_at, reason):
    """Hand over what is already charged to a spool; nothing new is inferred."""
    tracker = state.get("tracker")
    if (
        not isinstance(tracker, dict)
        or tracker.get("terminal")
        or tracker.get("status") not in ("printing", "paused")
        or not isinstance(tracker.get("route"), dict)
        or tracker["pending_mm"] <= _COUNTER_USAGE_EPSILON_MM
    ):
        return []
    event = _counter_usage_event(
        tracker, "checkpoint", observed_at, tracker["route"], tracker["pending_mm"], reason, None
    )
    tracker["pending_mm"] = 0.0
    tracker["emitted_at_s"] = tracker["printed_s"]
    return [event]


def capture_counter_usage(state, usage, route, observed_at, issue=None, job_prefix="job"):
    """Advance the books in ``state`` by one reading; return the usage that is certain.

    ``issue`` says why ``route`` is missing; a job that ends having charged
    nothing reports it instead of looking like a print that used no filament.
    ``job_prefix`` names the kind of printer in the identifier of a new job.

    A stretch of the job is charged only when the same spool was feeding at both
    ends of it and the feed was not switched in between (``feed_mark`` of the
    route). The stretch in which the feed changed, and any stretch without a
    reading, is charged to nobody. The books start at the first
    reading, so the part of a job printed before that is not charged either.
    """
    tracker = state.get("tracker")
    if not isinstance(usage, dict):
        if isinstance(tracker, dict):
            tracker["suspended"] = True
        return []
    status = usage["state"]
    counter = usage["filament_used_mm"]
    printed_s = usage.get("duration_s") or 0.0
    same_job = (
        isinstance(tracker, dict)
        and not (
            tracker.get("file_name")
            and usage.get("file_name")
            and tracker["file_name"] != usage["file_name"]
        )
        and counter + _COUNTER_USAGE_EPSILON_MM >= tracker["counter_mm"]
    )
    if isinstance(tracker, dict) and usage.get("estimate_source"):
        # Books written before the source was recorded take it from the reading.
        tracker["estimate_source"] = usage["estimate_source"]
    if isinstance(tracker, dict) and tracker.get("suspended"):
        events = flush_counter_usage(state, observed_at, "disconnect")
        if same_job:
            tracker.pop("suspended")
            tracker["counter_mm"] = counter
            tracker["printed_s"] = tracker["emitted_at_s"] = printed_s
            tracker["duration_s"] = usage.get("duration_s")
            tracker["route"] = route
        else:
            state["tracker"] = None
        return events + capture_counter_usage(
            state, usage, route, observed_at, issue, job_prefix
        )
    if status == "standby":
        state["tracker"] = None
        return []
    outcome = _COUNTER_USAGE_OUTCOMES.get(status)
    if not isinstance(tracker, dict) or tracker.get("terminal") or not same_job:
        state["tracker"] = {
            "job_id": job_prefix + ":" + uuid.uuid4().hex,
            "file_name": usage.get("file_name"),
            "started_at": observed_at,
            "status": status,
            "counter_mm": counter,
            "printed_s": printed_s,
            "emitted_at_s": printed_s,
            "duration_s": usage.get("duration_s"),
            "route": route,
            "estimate_source": usage.get("estimate_source"),
            "segment_sequence": 1,
            "pending_mm": 0.0,
            # A job first seen finished has nothing left to charge.
            "terminal": outcome is not None,
        }
        return []

    previous = tracker.get("route")
    pending = tracker["pending_mm"]
    changed = _counter_usage_feed(previous) != _counter_usage_feed(route)
    tracker["duration_s"] = usage.get("duration_s")
    events = []
    if changed:
        if previous is not None and pending > _COUNTER_USAGE_EPSILON_MM:
            reason = "spool_change"
            if route is None:
                reason = "filament_change"
            elif previous.get("slot_index") != route.get("slot_index"):
                reason = "tool_change"
            events.append(_counter_usage_event(
                tracker, "checkpoint", observed_at, previous, pending, reason, None
            ))
        pending = 0.0
        tracker["emitted_at_s"] = printed_s
    elif route is not None:
        pending += max(counter - tracker["counter_mm"], 0.0)

    def checkpoint(reason):
        nonlocal pending
        events.append(_counter_usage_event(
            tracker, "checkpoint", observed_at, route, pending, reason, None
        ))
        pending = 0.0
        tracker["emitted_at_s"] = printed_s

    if outcome is not None:
        events.append(_counter_usage_event(
            tracker,
            "terminal",
            observed_at,
            None if changed else route,
            0.0 if changed else pending,
            "terminal",
            outcome,
        ))
        if issue is not None and not tracker.get("charged"):
            events[-1]["skipped"] = [issue]
        pending = 0.0
        tracker["terminal"] = True
    elif pending > _COUNTER_USAGE_EPSILON_MM:
        if status == "paused" and tracker.get("status") != "paused":
            checkpoint("paused")
        elif printed_s - tracker["emitted_at_s"] >= COUNTER_USAGE_CHECKPOINT_S:
            checkpoint("periodic")
    tracker["status"] = status
    tracker["counter_mm"] = counter
    tracker["printed_s"] = printed_s
    tracker["route"] = route
    tracker["pending_mm"] = pending
    return events
