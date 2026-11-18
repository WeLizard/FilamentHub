"""Flashforge LAN protocol for the FilamentHub OrcaSlicer plugin.

The stock firmware of the Adventurer 5M / 5M Pro (firmware 2.x+), AD5X and
Creator 5 / 5 Pro answers ``POST http://<printer>:8898/detail`` while LAN mode
is on. The request carries the printer serial number and the check code from
its network screen; OrcaSlicer keeps both in the printer's connection settings
(``flashforge_serial_number`` and ``printhost_apikey``), so the plugin reads
them from there and never asks for them again.

The AD5X and Creator 5 report a four-slot material station; the 5M series
feeds one spool and reports only the material set on the printer. Nothing
here reports per-tool usage or a confirmed active tool, so the connector
claims ``read`` and ``presence`` only and never debits spools.

FH Edge reads the same API (edge-agent ``providers/flashforge.py``). Both
readers are checked against one shared fixture so they cannot drift apart.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import math
import re
import urllib.parse

FLASHFORGE_PROVIDER = "flashforge"
FLASHFORGE_HOST_TYPE = "flashforge"
FLASHFORGE_IDENTITY_KIND = "flashforge_serial"
FLASHFORGE_CAPABILITIES = ("read", "presence")
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
    ordered = [slots[index] for index in sorted(slots)]
    count = _flashforge_integer(_flashforge_field(station, "slotCnt"))
    complete = (
        count is not None
        and count == len(ordered) > 0
        and sorted(slots) == list(range(count))
    )
    return ordered, complete
