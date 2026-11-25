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

A station slot's material and colour can be set (``msConfig_cmd``), within
what the printer can show: a fixed list of material names and a palette of
24 colours, which differ between the AD5X and the Creator 5. The command is
documented by the community reference and not confirmed on a printer; the
caller reads the slot back and believes only that.

FH Edge reads the same API (edge-agent ``providers/flashforge.py``). The two
are held to one shared reading so they cannot drift apart. The books that turn
successive readings into usage are in ``filamenthub_usage_books.py``.

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
FLASHFORGE_CAPABILITIES = ("read", "presence", "consumption")
# Product IDs whose station slots can be set, with what each can show. The
# two palettes follow the same hues but differ by a few units per swatch, and
# the Creator 5 stores white for any colour that is not exactly its own.
FLASHFORGE_AD5X_PID = 38
_FLASHFORGE_AD5X_COLORS = (
    "#FFFFFF", "#FEF043", "#DCF478", "#0ACC38", "#067749", "#0C6283",
    "#0DE2A0", "#75D9F3", "#45A8F9", "#2750E0", "#46328E", "#A03CF7",
    "#F330F9", "#D4B0DC", "#F95D73", "#F72224", "#7C4B00", "#F98D33",
    "#FDEBD5", "#D3C4A3", "#AF7836", "#898989", "#BCBCBC", "#161616",
)
_FLASHFORGE_CREATOR5_COLORS = (
    "#FFFFFF", "#FFF245", "#DEF578", "#21CC3D", "#167A4B", "#156682",
    "#24E4A0", "#7BD9F0", "#4CAAF8", "#2E54DD", "#48358C", "#A341F7",
    "#F435F6", "#D5B4DE", "#FA6173", "#F82D29", "#805003", "#F9903B",
    "#FCEBD7", "#D5C5A1", "#B17C38", "#8C8C89", "#BEBEBE", "#1B1B1B",
)
_FLASHFORGE_AD5X_MATERIALS = (
    "PLA", "PETG", "PLA-CF", "PETG-CF", "ABS", "SILK", "PET-CF", "PAHT-CF",
    "PA-CF", "TPU", "PC", "PA", "PC-ABS", "PPS-CF",
)
_FLASHFORGE_CREATOR5_MATERIALS = (
    "PLA", "PETG", "PLA-CF", "PETG-CF", "ABS", "ASA", "SILK", "PET-CF",
    "PAHT-CF", "S-PAHT", "S-Multi", "PA-CF", "HIPS", "PVA", "TPU-90A",
    "TPU-95A", "TPU-64D", "PC", "PA", "PC-ABS", "PPS-CF",
)
# Names a spool may carry for something the printer lists under another name.
_FLASHFORGE_MATERIAL_ALIASES = {"PLA-SILK": "SILK", "SILK-PLA": "SILK"}
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
FLASHFORGE_MAX_JOB_LENGTH_MM = 10_000_000.0


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
    usage = {
        "state": state,
        "file_name": job,
        "filament_used_mm": total * progress,
        # The printer computed nothing and measured nothing: this is the
        # slicer's figure.
        "estimate_source": "slicer_progress",
    }
    duration = _flashforge_number(detail.get("printDuration"))
    if duration is not None and 0 <= duration <= 31_536_000:
        usage["duration_s"] = duration
    return usage


def flashforge_can_set_slots(detail):
    """Whether this printer has a station whose slots the command can set."""
    return flashforge_product_id(detail) in FLASHFORGE_STATION_PIDS and isinstance(
        _flashforge_field(detail, "matlStationInfo"), dict
    )


def flashforge_capabilities(detail):
    """What this printer's connection can do; only a station takes a slot's material."""
    capabilities = list(FLASHFORGE_CAPABILITIES)
    if flashforge_can_set_slots(detail):
        capabilities.append("write")
    return capabilities


def flashforge_material_name(detail, material):
    """The printer's own name for a spool's material, or None when it lists none.

    A name the printer does not list is not sent: the Creator 5 matches names
    exactly, and a made-up one would leave the slot saying something else.
    """
    if not isinstance(material, str):
        return None
    wanted = re.sub(r"[\s_]+", "-", material.strip()).upper()
    wanted = _FLASHFORGE_MATERIAL_ALIASES.get(wanted, wanted)
    names = (
        _FLASHFORGE_AD5X_MATERIALS
        if flashforge_product_id(detail) == FLASHFORGE_AD5X_PID
        else _FLASHFORGE_CREATOR5_MATERIALS
    )
    return next((name for name in names if name.upper() == wanted), None)


def _flashforge_lab(color):
    """CIE L*a*b* (D65) of an ``RRGGBB`` colour."""
    channels = []
    for offset in (0, 2, 4):
        value = int(color[offset:offset + 2], 16) / 255.0
        channels.append(
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    axes = []
    for value, white in (
        (0.4124564 * red + 0.3575761 * green + 0.1804375 * blue, 0.95047),
        (0.2126729 * red + 0.7151522 * green + 0.0721750 * blue, 1.0),
        (0.0193339 * red + 0.1191920 * green + 0.9503041 * blue, 1.08883),
    ):
        ratio = value / white
        axes.append(
            ratio ** (1.0 / 3.0) if ratio > 216.0 / 24389.0
            else (24389.0 / 27.0 * ratio + 16.0) / 116.0
        )
    return 116.0 * axes[1] - 16.0, 500.0 * (axes[0] - axes[1]), 200.0 * (axes[1] - axes[2])


def flashforge_color_difference(first, second):
    """CIEDE2000 difference of two L*a*b* colours: how unlike they look."""
    light_1, a_1, b_1 = first
    light_2, a_2, b_2 = second
    chroma_mean = (math.hypot(a_1, b_1) + math.hypot(a_2, b_2)) / 2.0
    boost = 0.5 * (1.0 - math.sqrt(chroma_mean ** 7 / (chroma_mean ** 7 + 25.0 ** 7)))
    a_1, a_2 = a_1 * (1.0 + boost), a_2 * (1.0 + boost)
    chroma_1, chroma_2 = math.hypot(a_1, b_1), math.hypot(a_2, b_2)
    hue_1 = math.degrees(math.atan2(b_1, a_1)) % 360.0 if chroma_1 else 0.0
    hue_2 = math.degrees(math.atan2(b_2, a_2)) % 360.0 if chroma_2 else 0.0
    turn = hue_2 - hue_1
    if not chroma_1 * chroma_2:
        turn = 0.0
    elif turn > 180.0:
        turn -= 360.0
    elif turn < -180.0:
        turn += 360.0
    hue_step = 2.0 * math.sqrt(chroma_1 * chroma_2) * math.sin(math.radians(turn) / 2.0)
    light_mean = (light_1 + light_2) / 2.0
    chroma_mean = (chroma_1 + chroma_2) / 2.0
    if not chroma_1 * chroma_2:
        hue_mean = hue_1 + hue_2
    elif abs(hue_1 - hue_2) <= 180.0:
        hue_mean = (hue_1 + hue_2) / 2.0
    elif hue_1 + hue_2 < 360.0:
        hue_mean = (hue_1 + hue_2 + 360.0) / 2.0
    else:
        hue_mean = (hue_1 + hue_2 - 360.0) / 2.0
    tone = (
        1.0
        - 0.17 * math.cos(math.radians(hue_mean - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * hue_mean))
        + 0.32 * math.cos(math.radians(3.0 * hue_mean + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * hue_mean - 63.0))
    )
    light_scale = 1.0 + 0.015 * (light_mean - 50.0) ** 2 / math.sqrt(
        20.0 + (light_mean - 50.0) ** 2
    )
    chroma_scale = 1.0 + 0.045 * chroma_mean
    hue_scale = 1.0 + 0.015 * chroma_mean * tone
    rotation = (
        -2.0
        * math.sqrt(chroma_mean ** 7 / (chroma_mean ** 7 + 25.0 ** 7))
        * math.sin(math.radians(60.0 * math.exp(-(((hue_mean - 275.0) / 25.0) ** 2))))
    )
    light_term = (light_2 - light_1) / light_scale
    chroma_term = (chroma_2 - chroma_1) / chroma_scale
    hue_term = hue_step / hue_scale
    return math.sqrt(
        light_term ** 2 + chroma_term ** 2 + hue_term ** 2 + rotation * chroma_term * hue_term
    )


def flashforge_palette_color(detail, color_hex):
    """The printer's swatch that looks most like a spool's colour, as it must be sent."""
    match = _FLASHFORGE_COLOR.fullmatch(color_hex.strip()) if isinstance(color_hex, str) else None
    if match is None:
        return None
    wanted = _flashforge_lab(match.group(1))
    palette = (
        _FLASHFORGE_AD5X_COLORS
        if flashforge_product_id(detail) == FLASHFORGE_AD5X_PID
        else _FLASHFORGE_CREATOR5_COLORS
    )
    return min(
        palette,
        key=lambda swatch: flashforge_color_difference(wanted, _flashforge_lab(swatch[1:])),
    )


def flashforge_control_url(address):
    host = "[%s]" % address if ":" in address else address
    return "http://%s:%d/control" % (host, FLASHFORGE_API_PORT)


def flashforge_slot_command(serial, check_code, provider_index, material, color):
    """The request that sets one station slot; slots are numbered from 1 on the wire."""
    return {
        "serialNumber": serial,
        "checkCode": check_code,
        "payload": {
            "cmd": "msConfig_cmd",
            "args": {"slot": provider_index + 1, "mt": material, "rgb": color},
        },
    }


def flashforge_slot_settings(detail):
    """What every station slot says now: ``{provider_index: (material, colour)}``.

    Read from the printer's own fields whether or not filament is loaded, so a
    slot can be compared before and after it is set.
    """
    station = _flashforge_field(detail, "matlStationInfo")
    entries = _flashforge_field(station, "slotInfos") if isinstance(station, dict) else None
    settings = {}
    for entry in entries if isinstance(entries, list) else []:
        slot_id = _flashforge_integer(entry.get("slotId")) if isinstance(entry, dict) else None
        if slot_id is None or not 1 <= slot_id <= FLASHFORGE_MAX_SLOTS:
            continue
        color = entry.get("materialColor")
        settings[slot_id - 1] = (
            entry.get("materialName") if isinstance(entry.get("materialName"), str) else None,
            color.strip().upper() if isinstance(color, str) else None,
        )
    return settings
