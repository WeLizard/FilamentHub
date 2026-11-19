# Copy of orca-plugin/filamenthub_plugin.py. Do not edit: change that file and run
# edge-agent/scripts/mirror_plugin_modules.py.
# ruff: noqa
# mypy: ignore-errors
"""Counting a Bambu job's filament, as the OrcaSlicer plugin does it.

Definitions taken from the plugin's main file; nothing here opens a
connection or touches a file on disk.
"""

import datetime
import hashlib
import io
import json
import math
import posixpath
import re
import uuid
import zipfile
from xml.etree import ElementTree

from ._bambu_report import BAMBU_WIDE_UNIT_BASE, _bambu_bits, _bambu_int, parse_bambu_feed


def _bambu_number(report, name):
    value = report.get(name)
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


_MAX_INPUT = 64 * 1024 * 1024


_MAX_METADATA = 1024 * 1024


_MAX_GCODE = 256 * 1024 * 1024


_MAX_RATIO = 1_000


_WEIGHT_VECTOR_RE = re.compile(
    rb"^\s*;\s*filament\s+(?:used|weight)\s*\[g\]\s*[:=]\s*([^\r\n;]+)",
    re.IGNORECASE | re.MULTILINE,
)


_LAYER_CHANGE_RE = re.compile(
    rb"^\s*;\s*(?:(?:CHANGE_LAYER|LAYER_CHANGE)\b|layer\s+num/total_layer_count\s*:)",
    re.IGNORECASE,
)


_TOOL_COMMAND_RE = re.compile(rb"^\s*T(\d+)\b", re.IGNORECASE)


_EXTRUSION_RE = re.compile(
    rb"(?:^|\s)E([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
)


def _finite_positive(value: str) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _weights_from_gcode(data: bytes) -> dict[int, float] | None:
    match = _WEIGHT_VECTOR_RE.search(data)
    if match is None:
        return None
    values: dict[int, float] = {}
    for index, raw in enumerate(re.split(rb"[,\s]+", match.group(1).strip())):
        value = _finite_positive(raw.decode("ascii", "ignore"))
        if value is not None:
            values[index] = value
    return values or None


def _weights_from_gcode_stream(stream) -> dict[int, float] | None:
    scanned = 0
    for line in stream:
        scanned += len(line)
        match = _WEIGHT_VECTOR_RE.match(line)
        if match is not None:
            return _weights_from_gcode(line)
        if scanned >= _MAX_GCODE:
            break
    return None


def _layer_weights_from_gcode_stream(stream, weights: dict[int, float]) -> dict[int, list[float]]:
    """Distribute declared slicer weights over layers using net E advance."""
    if not weights:
        return {}
    only_tool = next(iter(weights)) if len(weights) == 1 else None
    active_tool = only_tool
    relative_extrusion = True
    absolute_e: dict[int, float] = {}
    layer_index = 0
    saw_layer = False
    per_layer: dict[int, dict[int, float]] = {}

    scanned = 0
    for raw_line in stream:
        scanned += len(raw_line)
        if scanned > _MAX_GCODE:
            return {}
        line = raw_line.strip()
        if not line:
            continue
        if _LAYER_CHANGE_RE.match(line):
            if saw_layer:
                layer_index += 1
            else:
                saw_layer = True
            continue
        command = line.split(b";", 1)[0].strip()
        if not command:
            continue
        upper = command.upper()
        if re.match(rb"^M83(?:\s|$)", upper):
            relative_extrusion = True
            continue
        if re.match(rb"^M82(?:\s|$)", upper):
            relative_extrusion = False
            continue
        tool_match = _TOOL_COMMAND_RE.match(command)
        if tool_match is not None:
            candidate = int(tool_match.group(1))
            active_tool = candidate if candidate in weights else only_tool
            continue
        extrusion_match = _EXTRUSION_RE.search(command)
        if extrusion_match is None or active_tool is None:
            continue
        try:
            value = float(extrusion_match.group(1))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        if re.match(rb"^G92(?:\s|$)", upper):
            absolute_e[active_tool] = value
            continue
        if not re.match(rb"^G(?:0|1)(?:\s|$)", upper):
            continue
        if relative_extrusion:
            delta = value
        else:
            previous = absolute_e.get(active_tool)
            absolute_e[active_tool] = value
            if previous is None:
                continue
            delta = value - previous
        if delta != 0:
            layer = per_layer.setdefault(layer_index, {})
            layer[active_tool] = layer.get(active_tool, 0.0) + delta

    if not per_layer:
        return {}
    layer_count = max(per_layer) + 1
    result: dict[int, list[float]] = {}
    for logical, total_weight in weights.items():
        cumulative = 0.0
        peak = 0.0
        advances = []
        for layer in range(layer_count):
            cumulative += per_layer.get(layer, {}).get(logical, 0.0)
            peak = max(peak, cumulative)
            advances.append(peak)
        if not math.isfinite(peak) or peak <= 0:
            continue
        curve = [total_weight * advance / peak for advance in advances]
        curve[-1] = total_weight
        result[logical] = curve
    return result


def _layer_weights_from_gcode(data: bytes, weights: dict[int, float]) -> dict[int, list[float]]:
    return _layer_weights_from_gcode_stream(io.BytesIO(data), weights)


def _safe_zip_info(info: zipfile.ZipInfo, limit: int) -> bool:
    uncompressed = int(info.file_size)
    compressed = int(info.compress_size)
    if uncompressed < 0 or uncompressed > limit:
        return False
    if uncompressed and (compressed <= 0 or uncompressed > compressed * _MAX_RATIO):
        return False
    return True


def _normal_name(name: str) -> str:
    candidate = name.replace("\\", "/")
    if candidate.startswith("/") or any(part == ".." for part in candidate.split("/")):
        return ""
    normalized = posixpath.normpath(candidate)
    return "" if normalized in {"", "."} or normalized.startswith("../") else normalized


def _plate_number(path: str) -> int | None:
    match = re.fullmatch(r"metadata/plate_(\d+)\.gcode", _normal_name(path), re.IGNORECASE)
    return int(match.group(1)) if match else None


def _weights_from_slice_info(payload: bytes, plate_index: int) -> dict[int, float] | None:
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        return None
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return None
    for plate in root.findall(".//plate"):
        metadata = {
            item.get("key"): item.get("value")
            for item in plate.findall("metadata")
            if item.get("key")
        }
        try:
            current = int(metadata.get("index", ""))
        except (TypeError, ValueError):
            continue
        if current != plate_index:
            continue
        weights: dict[int, float] = {}
        for item in plate.findall("filament"):
            try:
                logical = int(item.get("id", "")) - 1
            except (TypeError, ValueError):
                continue
            if logical < 0:
                continue
            value = _finite_positive(item.get("used_g", ""))
            if value is not None:
                weights[logical] = value
        return weights or None
    return None


def parse_bambu_consumption_file(data: bytes, plate_path: str | None = None) -> dict | None:
    """Extract positive per-logical-filament slicer weights from G-code/3MF.

    A multi-plate 3MF requires ``plate_path``; no implicit plate 1 selection is
    made.  The function never treats printer telemetry as consumption evidence.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        return None
    payload = bytes(data)
    if not payload.startswith(b"PK\x03\x04"):
        if len(payload) > _MAX_GCODE:
            return None
        weights = _weights_from_gcode(payload)
        if not weights:
            return None
        result = {"source": "slicer_gcode", "weights": weights}
        layer_weights = _layer_weights_from_gcode(payload, weights)
        if layer_weights:
            result["layer_weights"] = layer_weights
        return result
    if len(payload) > _MAX_INPUT:
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > 4096:
                return None
            names = [_normal_name(item.filename) for item in infos]
            if len(names) != len(set(names)) or "" in names:
                return None
            plates = [item for item in infos if _plate_number(item.filename) is not None]
            if not plates:
                return None
            requested = _normal_name(plate_path) if plate_path else None
            if requested is None and len(plates) != 1:
                return None
            selected = next(
                (item for item in plates if _normal_name(item.filename) == requested),
                plates[0] if requested is None else None,
            )
            if selected is None:
                return None
            metadata = next(
                (item for item in infos if _normal_name(item.filename).lower() == "metadata/slice_info.config"),
                None,
            )
            if metadata is not None and not _safe_zip_info(metadata, _MAX_METADATA):
                return None
            plate_index = _plate_number(selected.filename)
            if plate_index is None:
                return None
            metadata_bytes = archive.read(metadata) if metadata is not None else b""
            if b"<!DOCTYPE" in metadata_bytes.upper() or b"<!ENTITY" in metadata_bytes.upper():
                return None
            safe_gcode = _safe_zip_info(selected, _MAX_GCODE)
            weights = _weights_from_slice_info(metadata_bytes, plate_index)
            if weights is None:
                if not safe_gcode:
                    return None
                with archive.open(selected) as gcode_stream:
                    weights = _weights_from_gcode_stream(gcode_stream)
            if not weights:
                return None
            result = {
                "source": "slicer_3mf",
                "weights": weights,
                "plate_index": plate_index,
                "plate_path": _normal_name(selected.filename),
            }
            if safe_gcode:
                with archive.open(selected) as gcode_stream:
                    layer_weights = _layer_weights_from_gcode_stream(gcode_stream, weights)
                if layer_weights:
                    result["layer_weights"] = layer_weights
            return result
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return None


def _bambu_job_key(report):
    identifiers = [str(report.get(key) or "") for key in ("task_id", "subtask_id", "project_id")]
    keys = ("gcode_file",) if any(value not in {"", "0"} for value in identifiers) else (
        "gcode_file", "subtask_name"
    )
    fields = identifiers + [str(report.get(key) or "") for key in keys]
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def _bambu_file_candidates(report):
    candidates = set()
    for field in ("gcode_file", "subtask_name"):
        value = report.get(field)
        if not isinstance(value, str) or len(value) > 500:
            continue
        value = value.replace("\\", "/")
        if any(ord(char) < 32 for char in value) or ":" in value:
            continue
        if any(part == ".." for part in value.split("/")):
            continue
        if value.lower().startswith("metadata/"):
            continue
        name = posixpath.basename(value)
        if not name:
            continue
        if name.lower().endswith((".3mf", ".gcode")):
            candidates.add(name)
        else:
            candidates.update((name + ".3mf", name + ".gcode.3mf", name + ".gcode"))
    return candidates


def _bambu_usage_routes(desired):
    result = {}
    for slot in desired.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        spool = slot.get("spool")
        proof = slot.get("usage_route_proof")
        index = slot.get("index")
        if (isinstance(spool, dict) and isinstance(spool.get("id"), int)
                and isinstance(index, int) and isinstance(proof, str) and proof):
            result[index] = {
                "slot_index": index, "spool_id": spool["id"],
                "usage_route_proof": proof, "evidence": "route_proof",
                "initial_weight_g": spool.get("initial_weight_g"),
            }
    return result


def _bambu_progress(report):
    if report.get("gcode_state") == "FINISH":
        return 1.0
    percent = _bambu_number(report, "mc_percent")
    return min(max(percent / 100, 0), 1) if percent is not None else None


def _bambu_usage_counters(report, routes, estimate):
    """Return comparable per-slot estimates with a source and physical identity."""
    feed = parse_bambu_feed(report) or {}
    slots = {item["index"]: item for item in feed.get("slots") or []}
    progress = _bambu_progress(report)
    weights = (estimate or {}).get("weights") or {}
    layer_weights = (estimate or {}).get("layer_weights") or {}
    current_layer = _bambu_int(report.get("layer_num"))
    finished = str(report.get("gcode_state") or "").upper() == "FINISH"
    mapping = report.get("ams_mapping")
    totals = {}
    if weights and (progress is not None or current_layer is not None):
        for logical, weight in weights.items():
            logical = int(logical)
            index = None
            if isinstance(mapping, list) and logical < len(mapping):
                flat = _bambu_int(mapping[logical])
                # Bambu's task mapping uses flat 16..23 for HT units 128..135.
                if flat is not None:
                    index = BAMBU_WIDE_UNIT_BASE + flat - 16 if 16 <= flat < 24 else flat
                    if flat == -1 and len(weights) == 1 and feed.get("active_index") in {254, 255}:
                        index = feed["active_index"]
            elif len(weights) == 1:
                index = feed.get("active_index")
            if index in routes:
                curve = layer_weights.get(str(logical), layer_weights.get(logical))
                layer_point = None
                if isinstance(curve, list) and curve and (current_layer or finished):
                    layer_point = float(weight) if finished else _finite_positive(
                        curve[min(max(current_layer, 1), len(curve)) - 1]
                    )
                entry = totals.setdefault(index, {
                    "counter": 0.0,
                    "total": 0.0,
                    "all_layer_based": True,
                })
                if layer_point is not None:
                    entry["counter"] += layer_point
                elif progress is not None:
                    entry["counter"] += float(weight) * progress
                    entry["all_layer_based"] = False
                else:
                    totals.pop(index, None)
                    continue
                entry["total"] += float(weight)
    result = {}
    for index, route in routes.items():
        slot = slots.get(index) or {}
        if slot.get("present") is False:
            continue
        identity = slot.get("provider_uid")
        if index in totals:
            total = totals[index]
            result[index] = {
                "counter": total["counter"],
                "source": "slicer_gcode" if total["all_layer_based"] else "slicer_progress",
                "identity": identity,
                "scale": [estimate.get("sha256"), total["total"]],
            }
        else:
            remaining = slot.get("remaining_g")
            if remaining is None:
                percent = slot.get("remaining_pct")
                capacity = _finite_positive(slot.get("reported_capacity_g"))
                if percent is not None and 0 <= percent <= 100 and capacity is not None:
                    remaining = capacity * percent / 100
            reading = _bambu_bits((report.get("ams") or {}).get("tray_reading_bits"))
            if (not reading and identity and remaining is not None
                    and math.isfinite(remaining) and remaining >= 0):
                result[index] = {
                    "counter": -remaining, "source": "ams_remaining",
                    "identity": identity, "scale": slot.get("reported_capacity_g"),
                }
    return result


def capture_bambu_usage(state, report, desired, estimate, observed_at):
    """Persistable deltas start at the observed spool binding, including late binds."""
    status = str(report.get("gcode_state") or "").upper()
    active = status in {"RUNNING", "PAUSE", "PREPARE"}
    terminal = status in {"FINISH", "FAILED"}
    key = _bambu_job_key(report)
    progress = _bambu_progress(report)
    tracker = state.get("tracker")
    new_run = (tracker is None or tracker.get("key") != key
               or (active and (tracker.get("terminal") or tracker.get("inactive")))
               or (active and progress is not None and tracker.get("progress") is not None
                   and progress + 0.02 < tracker["progress"]))
    events = []

    def emit(current, *, outcome=None, reason="periodic"):
        pending = current.get("pending") or {}
        if not pending and outcome is None:
            return
        sequence = current["segment_sequence"]
        events.append({
            "contract_version": 2,
            "event_id": current["job_id"] + ":%d" % sequence,
            "job_id": current["job_id"], "segment_sequence": sequence,
            "event_type": "terminal" if outcome is not None else "checkpoint",
            "reasons": ["terminal" if outcome is not None else reason],
            "started_at": current["started_at"], "observed_at": observed_at,
            "file_name": current.get("file_name"),
            "items": list(pending.values()),
            **({"outcome": outcome} if outcome is not None else {}),
        })
        current["pending"] = {}
        current["segment_sequence"] += 1
        current["last_emit"] = observed_at

    if not active and not terminal:
        if tracker is not None:
            emit(tracker, reason="disconnect")
            tracker["previous"] = {}
            tracker["inactive"] = True
        return events
    if new_run:
        if tracker is not None and not tracker.get("terminal"):
            emit(tracker, reason="disconnect")
        tracker = {
            "key": key, "job_id": "bambu:" + uuid.uuid4().hex,
            "file_name": str(report.get("subtask_name") or report.get("gcode_file") or "")[:500],
            "started_at": observed_at, "last_emit": observed_at,
            "segment_sequence": 1, "previous": {}, "pending": {},
            "terminal": terminal,
        }
        state["tracker"] = tracker
    if tracker.get("terminal"):
        return events
    if isinstance(report.get("ams_mapping"), list):
        tracker["ams_mapping"] = report["ams_mapping"]
    elif tracker.get("ams_mapping") is not None:
        report = {**report, "ams_mapping": tracker["ams_mapping"]}
    routes = _bambu_usage_routes(desired)
    counters = _bambu_usage_counters(report, routes, estimate)
    previous = tracker["previous"]
    proofs = {route["usage_route_proof"] for route in routes.values()}
    tag_bindings = {
        proof: identity for proof, identity in state.get("tag_bindings", {}).items()
        if proof in proofs
    }
    state["tag_bindings"] = tag_bindings
    current = {}
    for index, counter in counters.items():
        route = dict(routes[index])
        route.pop("initial_weight_g", None)
        proof = route["usage_route_proof"]
        identity = counter.get("identity")
        if identity is not None:
            bound = tag_bindings.setdefault(proof, identity)
            if bound != identity:
                # A replacement physical tag cannot inherit the old desired
                # spool merely because it occupies the same printer slot.
                continue
        point = {**counter, "route": route, "observed_at": observed_at}
        before = previous.get(str(index))
        remaps = tracker.setdefault("counter_remaps", {})
        remap = remaps.get(str(index))
        if (remap is not None and remap.get("source") == point["source"]
                and remap.get("scale") == point.get("scale")):
            raw_start = float(remap["raw_start"])
            adjusted_start = float(remap["adjusted_start"])
            total = float(remap["total"])
            raw = max(raw_start, float(point["counter"]))
            if total > raw_start:
                point["counter"] = min(total, adjusted_start + (
                    (raw - raw_start) * (total - adjusted_start) / (total - raw_start)
                ))
            else:
                point["counter"] = max(adjusted_start, raw)
        same_slicer_job = (
            before is not None
            and before.get("source") in {"slicer_progress", "slicer_gcode"}
            and point.get("source") in {"slicer_progress", "slicer_gcode"}
            and before.get("scale") == point.get("scale")
        )
        if same_slicer_job and before["source"] != point["source"]:
            raw = float(counter["counter"])
            total = float(point["scale"][1])
            remaps[str(index)] = {
                "source": point["source"],
                "scale": point["scale"],
                "raw_start": raw,
                "adjusted_start": float(before["counter"]),
                "total": total,
            }
            point["counter"] = float(before["counter"])
        elif before is not None and (
            before.get("route") != route
            or before.get("identity") != point.get("identity")
            or before.get("scale") != point.get("scale")
        ):
            remaps.pop(str(index), None)
        current[str(index)] = point
        if (before is None or before["route"] != route
                or before["source"] != point["source"]
                or before.get("identity") != point.get("identity")
                or before.get("scale") != point.get("scale")):
            continue
        delta = point["counter"] - before["counter"]
        if delta <= 0 or not math.isfinite(delta):
            if point["source"] == "ams_remaining" and delta < 0:
                # A sensor rebound must not charge the same decrease again.
                # A new tag, route or calibrated capacity has its own baseline.
                point["counter"] = before["counter"]
            continue
        pending_key = str(route["spool_id"])
        pending = tracker["pending"].get(pending_key)
        if pending is not None and (
            pending["estimate_source"] != point["source"] or pending["slot_index"] != index
            or pending["usage_route_proof"] != proof
        ):
            emit(tracker, reason="slot_change")
            pending = None
        if pending is None:
            pending = {
                **route, "used_weight_g": 0.0, "consumption_kind": "estimated",
                "estimate_source": point["source"],
                "usage_started_at": before["observed_at"],
            }
            tracker["pending"][pending_key] = pending
        pending["used_weight_g"] += delta
    tracker["previous"] = current
    tracker["progress"] = progress
    elapsed = (datetime.datetime.fromisoformat(observed_at)
               - datetime.datetime.fromisoformat(tracker["last_emit"])).total_seconds()
    if terminal:
        emit(tracker, outcome="completed" if status == "FINISH" else "failed")
        tracker["terminal"] = True
    elif elapsed >= 300 or status == "PAUSE":
        emit(tracker, reason="paused" if status == "PAUSE" else "periodic")
    return events


def _buffer_bambu_usage_report(stream, report, observed_at):
    """Keep accounting transitions until the journal has accepted them."""
    feed = parse_bambu_feed(report) or {}
    signature = json.dumps([
        _bambu_job_key(report), report.get("gcode_state"), _bambu_progress(report),
        report.get("ams_mapping"),
        [{name: slot.get(name) for name in (
            "index", "present", "provider_uid", "remaining_g", "remaining_pct",
            "reported_capacity_g",
        )} for slot in feed.get("slots", [])],
    ], sort_keys=True)
    if signature == stream.get("usage_signature") and not stream.get("usage_gap_pending"):
        return
    stream["usage_signature"] = signature
    pending = stream.setdefault("usage_reports", [])
    observation = {"report": json.loads(json.dumps(report)), "observed_at": observed_at}
    if stream.pop("usage_gap_pending", False):
        observation["report"]["_fh_observation_gap"] = True
    if len(pending) >= 256:
        # Do not infer consumption across a lost observation interval. Already
        # journaled deltas remain intact, and the newest point starts a baseline.
        pending.clear()
        observation["report"]["_fh_observation_gap"] = True
    pending.append(observation)
