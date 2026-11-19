"""Flashforge LAN protocol for the FilamentHub OrcaSlicer plugin.

The stock firmware of the Adventurer 5M / 5M Pro (firmware 2.x+), AD5X and
Creator 5 / 5 Pro answers ``POST http://<printer>:8898/detail`` while LAN mode
is on. The request carries the printer serial number and the check code from
its network screen; OrcaSlicer keeps both in the printer's connection settings
(``flashforge_serial_number`` and ``printhost_apikey``), so the plugin reads
them from there and never asks for them again.

The AD5X and Creator 5 report a four-slot material station; the 5M series
feeds one spool and reports only the material set on the printer.

The printer measures no filament. It reports the slicer's estimate for the
whole job and the print progress; the two give a running figure, marked as
an estimate, that is charged to the spool in the slot that is feeding. Where
the printer leaves a doubt about that slot, nothing is charged.

FH Edge reads the same API and keeps the same books (edge-agent
``providers/flashforge.py`` and ``usage.py``). The two are held to one shared
reading and one shared print scenario so they cannot drift apart.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import math
import re
import urllib.parse
import uuid

FLASHFORGE_PROVIDER = "flashforge"
FLASHFORGE_HOST_TYPE = "flashforge"
FLASHFORGE_IDENTITY_KIND = "flashforge_serial"
FLASHFORGE_CAPABILITIES = ("read", "presence", "consumption")
FLASHFORGE_API_PORT = 8898
FLASHFORGE_MAX_SLOTS = 16
# Product IDs from /detail: the 5M series feeds one spool, the others a station.
FLASHFORGE_SINGLE_SPOOL_PIDS = frozenset({35, 36})  # Adventurer 5M, 5M Pro
FLASHFORGE_STATION_PIDS = frozenset({38, 40, 41})  # AD5X, Creator 5, Creator 5 Pro
# Response codes documented for credential and mode failures.
FLASHFORGE_AUTH_FAILED = 1
FLASHFORGE_LAN_MODE_OFF = -2
_FLASHFORGE_SERIAL = re.compile(r"[A-Za-z0-9_-]{4,64}")
_FLASHFORGE_CHECK_CODE = re.compile(r"[\x21-\x7e]{1,64}")
_FLASHFORGE_COLOR = re.compile(r"#?([0-9A-Fa-f]{6})")
_FLASHFORGE_STATES = {
    "ready": "idle",
    "heating": "preparing",
    "calibrate_doing": "preparing",
    "printing": "printing",
    "pausing": "paused",
    "paused": "paused",
    "completed": "finished",
    "cancel": "failed",
    "error": "failed",
}
# What the usage books understand; other states carry no usage evidence.
_FLASHFORGE_USAGE_STATES = {
    "ready": "standby",
    "printing": "printing",
    "pausing": "paused",
    "paused": "paused",
    "completed": "complete",
    "cancel": "cancelled",
    "error": "error",
}
_FLASHFORGE_USAGE_OUTCOMES = {
    "complete": "completed",
    "cancelled": "cancelled",
    "error": "failed",
}
FLASHFORGE_MAX_JOB_LENGTH_MM = 10_000_000.0
# A long print is charged in parts, so a lost end does not lose all of it.
FLASHFORGE_USAGE_CHECKPOINT_S = 300.0
_FLASHFORGE_USAGE_EPSILON_MM = 0.001


def flashforge_serial(value):
    """Return the canonical serial number, or an empty string when unusable."""
    serial = str(value or "").strip()
    return serial.upper() if _FLASHFORGE_SERIAL.fullmatch(serial) else ""


def flashforge_check_code(value):
    """Return the check code as entered, or an empty string when unusable."""
    code = str(value or "").strip()
    return code if _FLASHFORGE_CHECK_CODE.fullmatch(code) else ""


def flashforge_host(print_host):
    """Return only the host name or address from Orca's print_host setting.

    OrcaSlicer always talks to port 8898 whatever the setting says, so a
    scheme or port written there is ignored the same way.
    """
    raw = str(print_host or "").strip()
    if not raw or len(raw) > 500 or any(ch in raw for ch in "\\\r\n?#@"):
        return ""
    try:
        parsed = urllib.parse.urlsplit(
            raw if "://" in raw else "//" + raw, allow_fragments=False
        )
        host = parsed.hostname or ""
    except (TypeError, ValueError):
        return ""
    if parsed.path not in {"", "/"}:
        return ""
    host = host.strip().rstrip(".")
    if not host or len(host) > 253 or any(ch in host for ch in "/\\?#@ "):
        return ""
    return host


def flashforge_detail_url(address):
    """Build the /detail URL for one already resolved LAN address."""
    host = "[%s]" % address if ":" in address else address
    return "http://%s:%d/detail" % (host, FLASHFORGE_API_PORT)


def flashforge_detail_body(serial, check_code):
    return {"serialNumber": serial, "checkCode": check_code}


def flashforge_detail_result(status, payload):
    """Classify one /detail answer as ``(detail, failure)``.

    ``failure`` is ``None`` on success, otherwise ``"auth"`` (wrong serial
    number or check code), ``"lan_mode"`` (LAN mode is off) or ``"invalid"``.
    """
    if status != 200 or not isinstance(payload, dict):
        return None, "invalid"
    code = _flashforge_integer(payload.get("code"))
    if code == FLASHFORGE_AUTH_FAILED:
        return None, "auth"
    if code == FLASHFORGE_LAN_MODE_OFF:
        return None, "lan_mode"
    detail = payload.get("detail")
    if code != 0 or not isinstance(detail, dict):
        return None, "invalid"
    return detail, None


def _flashforge_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _flashforge_integer(value):
    number = _flashforge_number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _flashforge_temperature(value, low, high):
    number = _flashforge_number(value)
    if number is None or number < low or number > high:
        # Creator 5 reports -108 for a missing chamber sensor.
        return None
    return round(number, 1)


def _flashforge_text(value, maximum):
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:maximum] or None


def _flashforge_color(value):
    if not isinstance(value, str):
        return None
    match = _FLASHFORGE_COLOR.fullmatch(value.strip())
    return match.group(1).upper() if match else None


def _flashforge_field(source, name):
    """Read a field the way Orca's client does: some firmware capitalizes keys."""
    return source.get(name, source.get(name[:1].upper() + name[1:]))


def _flashforge_flag(value):
    """Firmware reports flags as booleans or as 0/1 numbers."""
    if isinstance(value, bool):
        return value
    number = _flashforge_integer(value)
    return number != 0 if number in {0, 1} else None


def _flashforge_material(value):
    material = _flashforge_text(value, 80)
    return material if material and material.strip("?-") else None


def flashforge_product_id(detail):
    """Return the model PID; the 5M sends an integer, newer models a hex string."""
    value = detail.get("pid")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9A-Fa-f]{1,4}", value.strip()):
        return int(value.strip(), 16)
    return None


def _flashforge_nozzle(detail):
    """Return one nozzle reading only when it is unambiguous."""
    temps = detail.get("nozzleTemps")
    targets = detail.get("nozzleTargetTemps")
    if (
        isinstance(temps, list)
        and isinstance(targets, list)
        and temps
        and len(temps) == len(targets)
    ):
        heated = [
            index for index, target in enumerate(targets)
            if (_flashforge_number(target) or 0) > 0
        ]
        if len(temps) == 1:
            heated = [0]
        if len(heated) != 1:
            # Several heated tools or none: no single "the nozzle" exists.
            return None, None
        index = heated[0]
        return (
            _flashforge_temperature(temps[index], -50, 600),
            _flashforge_temperature(targets[index], 0, 600),
        )
    return (
        _flashforge_temperature(detail.get("rightTemp"), -50, 600),
        _flashforge_temperature(detail.get("rightTargetTemp"), 0, 600),
    )


def flashforge_printer(detail):
    """Normalize printer status into the provider-neutral bridge contract."""
    state = _FLASHFORGE_STATES.get(
        str(detail.get("status") or "").strip().lower(), "unknown"
    )
    printer = {}
    printer["state"] = state
    if state in {"printing", "paused", "preparing", "finished", "failed"}:
        job = _flashforge_text(detail.get("printFileName"), 300)
        if job:
            printer["job_name"] = job
        progress = _flashforge_number(detail.get("printProgress"))
        if progress is not None and 0 <= progress <= 1:
            printer["progress_percent"] = round(progress * 100)
        if state in {"printing", "paused", "preparing"}:
            remaining = _flashforge_number(detail.get("estimatedTime"))
            if remaining is not None and 0 <= remaining <= 2_592_000:
                printer["remaining_seconds"] = int(remaining)
        layer = _flashforge_integer(detail.get("printLayer"))
        total = _flashforge_integer(detail.get("targetPrintLayer"))
        if layer is not None and 0 <= layer <= 10_000_000:
            printer["current_layer"] = layer
        if total is not None and 0 < total <= 10_000_000:
            printer["total_layers"] = total
    nozzle, nozzle_target = _flashforge_nozzle(detail)
    for key, value in (
        ("nozzle_temperature", nozzle),
        ("nozzle_target_temperature", nozzle_target),
        ("bed_temperature", _flashforge_temperature(detail.get("platTemp"), -50, 250)),
        ("bed_target_temperature", _flashforge_temperature(detail.get("platTargetTemp"), 0, 250)),
        ("chamber_temperature", _flashforge_temperature(detail.get("chamberTemp"), -50, 150)),
    ):
        if value is not None:
            printer[key] = value
    error = _flashforge_text(detail.get("errorCode"), 80)
    if error and error not in {"0", "E0000"}:
        printer["error_code"] = error
    return printer


def _flashforge_active_slot(detail, station, slots):
    """The slot feeding the nozzle now, or None when the printer leaves a doubt."""
    current = _flashforge_integer(_flashforge_field(station, "currentSlot"))
    if current is None or slots.get(current - 1, {}).get("present") is not True:
        return None
    targets = detail.get("nozzleTargetTemps")
    if isinstance(targets, list) and len(targets) > 1:
        heated = [
            index
            for index, target in enumerate(targets)
            if (_flashforge_number(target) or 0) > 0
        ]
        # A printer with a nozzle per slot heats the one in use. A second hot
        # nozzle, or a hot nozzle that is not this slot's, is a doubt.
        if len(heated) > 1 or (heated and heated[0] != current - 1):
            return None
    return current - 1


def flashforge_slots(detail):
    """Return the feed slots and whether they form the printer's complete feed."""
    pid = flashforge_product_id(detail)
    station = _flashforge_field(detail, "matlStationInfo")
    if pid in FLASHFORGE_SINGLE_SPOOL_PIDS:
        # One spool on the extruder; the printer knows only its set material.
        spool = {
            "provider_index": 0,
            "label": "Spool",
            "kind": "external",
            "present": None,
            "spool_identity_known": False,
            # The only feed this printer has.
            "active_feed": True,
        }
        material = _flashforge_material(detail.get("rightFilamentType"))
        if material:
            spool["material"] = material
        return [spool], True
    if not isinstance(station, dict) or (
        pid is not None and pid not in FLASHFORGE_STATION_PIDS
    ):
        # An unknown model or a missing station is not guessed into a topology.
        return [], False
    entries = _flashforge_field(station, "slotInfos")
    if not isinstance(entries, list) or len(entries) > FLASHFORGE_MAX_SLOTS:
        return [], False
    slots = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return [], False
        slot_id = _flashforge_integer(entry.get("slotId"))
        if (
            slot_id is None
            or slot_id < 1
            or slot_id > FLASHFORGE_MAX_SLOTS
            or slot_id - 1 in slots
        ):
            return [], False
        present = _flashforge_flag(entry.get("hasFilament"))
        slot = {
            "provider_index": slot_id - 1,
            "label": "Slot %d" % slot_id,
            "kind": "slot",
            "present": present,
            "spool_identity_known": False,
        }
        if present is True:
            material = _flashforge_material(entry.get("materialName"))
            if material:
                slot["material"] = material
            color = _flashforge_color(entry.get("materialColor"))
            if color:
                slot["color_hex"] = color
        slots[slot_id - 1] = slot
    active = _flashforge_active_slot(detail, station, slots)
    for index, slot in slots.items():
        slot["active_feed"] = index == active
    ordered = [slots[index] for index in sorted(slots)]
    count = _flashforge_integer(_flashforge_field(station, "slotCnt"))
    complete = (
        count is not None
        and count == len(ordered) > 0
        and sorted(slots) == list(range(count))
    )
    return ordered, complete


def flashforge_usage(detail):
    """The job's filament so far: the slicer's estimate scaled by progress."""
    state = _FLASHFORGE_USAGE_STATES.get(str(detail.get("status") or "").strip().lower())
    if state is None:
        return None
    if state == "standby":
        return {"state": state, "filament_used_mm": 0.0}
    total = _flashforge_number(detail.get("estimatedRightLen"))
    progress = _flashforge_number(detail.get("printProgress"))
    job = _flashforge_text(detail.get("printFileName"), 300)
    if (
        total is None
        or not 0 < total <= FLASHFORGE_MAX_JOB_LENGTH_MM
        or progress is None
        or not 0 <= progress <= 1
        or not job
    ):
        return None
    if state == "complete":
        # A finished job used its whole estimate, whatever the last reading said.
        progress = 1.0
    usage = {"state": state, "file_name": job, "filament_used_mm": total * progress}
    duration = _flashforge_number(detail.get("printDuration"))
    if duration is not None and 0 <= duration <= 31_536_000:
        usage["duration_s"] = duration
    return usage


def flashforge_usage_route(slots, desired):
    """The spool the site put in the one slot that is feeding, or None."""
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
    if len(feeding) == 1:
        return assignments.get(feeding[0])
    # A printer whose feed could not be read still has one unambiguous spool
    # when the site knows of exactly one.
    if not slots and len(assignments) == 1:
        return next(iter(assignments.values()))
    return None


def _flashforge_usage_event(tracker, event_type, observed_at, route, length_mm, reason, outcome):
    sequence = tracker["segment_sequence"]
    tracker["segment_sequence"] = sequence + 1
    items = []
    if route is not None and length_mm > _FLASHFORGE_USAGE_EPSILON_MM:
        proof = route.get("usage_route_proof")
        item = {
            "slot_index": route["slot_index"],
            "spool_id": route["spool_id"],
            "used_length_mm": length_mm,
            "evidence": "route_proof" if proof is not None else "current_assignment",
        }
        if proof is not None:
            item["usage_route_proof"] = proof
        # The printer computed nothing and measured nothing: this is the
        # slicer's figure.
        item["consumption_kind"] = "estimated"
        item["estimate_source"] = "slicer_progress"
        items.append(item)
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


def flush_flashforge_usage(state, observed_at, reason):
    """Hand over what is already charged to a spool; nothing new is inferred."""
    tracker = state.get("tracker")
    if (
        not isinstance(tracker, dict)
        or tracker.get("terminal")
        or tracker.get("status") not in ("printing", "paused")
        or not isinstance(tracker.get("route"), dict)
        or tracker["pending_mm"] <= _FLASHFORGE_USAGE_EPSILON_MM
    ):
        return []
    event = _flashforge_usage_event(
        tracker, "checkpoint", observed_at, tracker["route"], tracker["pending_mm"], reason, None
    )
    tracker["pending_mm"] = 0.0
    tracker["emitted_at_s"] = tracker["printed_s"]
    return [event]


def capture_flashforge_usage(state, usage, route, observed_at):
    """Advance the books in ``state`` by one reading; return the usage that is certain.

    A stretch of the job is charged only when the same spool was feeding at both
    ends of it. The stretch in which the feeding slot changed, and any stretch
    without a reading, is charged to nobody. The books start at the first
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
        and counter + _FLASHFORGE_USAGE_EPSILON_MM >= tracker["counter_mm"]
    )
    if isinstance(tracker, dict) and tracker.get("suspended"):
        events = flush_flashforge_usage(state, observed_at, "disconnect")
        if same_job:
            tracker.pop("suspended")
            tracker["counter_mm"] = counter
            tracker["printed_s"] = tracker["emitted_at_s"] = printed_s
            tracker["duration_s"] = usage.get("duration_s")
            tracker["route"] = route
        else:
            state["tracker"] = None
        return events + capture_flashforge_usage(state, usage, route, observed_at)
    if status == "standby":
        state["tracker"] = None
        return []
    outcome = _FLASHFORGE_USAGE_OUTCOMES.get(status)
    if not isinstance(tracker, dict) or tracker.get("terminal") or not same_job:
        state["tracker"] = {
            "job_id": "flashforge:" + uuid.uuid4().hex,
            "file_name": usage.get("file_name"),
            "started_at": observed_at,
            "status": status,
            "counter_mm": counter,
            "printed_s": printed_s,
            "emitted_at_s": printed_s,
            "duration_s": usage.get("duration_s"),
            "route": route,
            "segment_sequence": 1,
            "pending_mm": 0.0,
            # A job first seen finished has nothing left to charge.
            "terminal": outcome is not None,
        }
        return []

    previous = tracker.get("route")
    pending = tracker["pending_mm"]
    changed = previous != route
    tracker["duration_s"] = usage.get("duration_s")
    events = []
    if changed:
        if previous is not None and pending > _FLASHFORGE_USAGE_EPSILON_MM:
            reason = "spool_change"
            if route is None:
                reason = "filament_change"
            elif previous.get("slot_index") != route.get("slot_index"):
                reason = "tool_change"
            events.append(_flashforge_usage_event(
                tracker, "checkpoint", observed_at, previous, pending, reason, None
            ))
        pending = 0.0
        tracker["emitted_at_s"] = printed_s
    elif route is not None:
        pending += max(counter - tracker["counter_mm"], 0.0)

    def checkpoint(reason):
        nonlocal pending
        events.append(_flashforge_usage_event(
            tracker, "checkpoint", observed_at, route, pending, reason, None
        ))
        pending = 0.0
        tracker["emitted_at_s"] = printed_s

    if outcome is not None:
        events.append(_flashforge_usage_event(
            tracker,
            "terminal",
            observed_at,
            None if changed else route,
            0.0 if changed else pending,
            "terminal",
            outcome,
        ))
        pending = 0.0
        tracker["terminal"] = True
    elif pending > _FLASHFORGE_USAGE_EPSILON_MM:
        if status == "paused" and tracker.get("status") != "paused":
            checkpoint("paused")
        elif printed_s - tracker["emitted_at_s"] >= FLASHFORGE_USAGE_CHECKPOINT_S:
            checkpoint("periodic")
    tracker["status"] = status
    tracker["counter_mm"] = counter
    tracker["printed_s"] = printed_s
    tracker["route"] = route
    tracker["pending_mm"] = pending
    return events
