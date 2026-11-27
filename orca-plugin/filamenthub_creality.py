"""Creality LAN protocol for the FilamentHub OrcaSlicer plugin.

The stock firmware of the K1 and K2 families and of the newer Ender-3 models
talks over an unauthenticated WebSocket on port 9999: it sends its whole
status when a client connects, then changes, and answers
``{"method": "get", "params": {"boxsInfo": 1}}`` with the slots of its CFS.
``GET http://<printer>/info`` names the model and the MAC address. OrcaSlicer
keeps the printer's address in its connection settings (host type
``crealityprint``), so the plugin reads it from there and asks for nothing.

What each field means is taken from OrcaSlicer's own Creality code
(OrcaSlicer/OrcaSlicer 808dd7df, ``src/slic3r/Utils/CrealityPrint.cpp`` and
``CrealityPrintAgent.cpp``: the slot query, the heartbeat, the ``boxsInfo``
schema verified on a K2 Combo) and from a status captured from a K1C with a
CFS. The print state codes are the ones the K1 family was observed to send:
1 printing, 5 paused, 2 finished, 3 failed, 4 cancelled.

The printer counts the filament a job has used (``usedMaterialLength``, in
millimetres, one figure for all colours). It is charged to the spool in the
slot the printer marks as selected. Where the printer leaves a doubt about that
slot, nothing is charged.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import codecs
import hashlib
import json
import re
import struct
import urllib.parse

CREALITY_PROVIDER = "creality"
CREALITY_HOST_TYPE = "crealityprint"
CREALITY_IDENTITY_KIND = "creality_mac"
CREALITY_CAPABILITIES = ("read", "presence", "consumption")
CREALITY_WS_PORT = 9999
CREALITY_INFO_PORT = 80
CREALITY_SLOT_QUERY = {"method": "get", "params": {"boxsInfo": 1}}
# The printer drops a client that does not answer its heartbeat with this text.
CREALITY_HEARTBEAT_REPLY = "ok"
CREALITY_SLOTS_PER_BOX = 4
CREALITY_MAX_BOXES = 4
# The spool holder outside the CFS, numbered like the external holder of
# other printers on FilamentHub.
CREALITY_EXTERNAL_INDEX = 255
CREALITY_MAX_FRAME_BYTES = 1024 * 1024
CREALITY_MAX_JOB_LENGTH_MM = 10_000_000.0
_CREALITY_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_CREALITY_MAC = re.compile(r"[0-9A-F]{12}")
_CREALITY_COLOR = re.compile(r"#?[0-9A-Fa-f]?([0-9A-Fa-f]{6})")
# What the usage books understand; other states carry no usage evidence.
# OrcaSlicer 7cdc829a gives host type and printer agent "crealityprint" to the
# profiles of these models only (resources/profiles/Creality/machine): the K1
# and K2 families with their CFS-C variants, and the SPARKX i7.
CREALITY_STOCK_MODEL_PREFIXES = ("Creality K1", "Creality K2", "Creality SPARKX i7")
# A profile saved before OrcaSlicer knew "crealityprint" has no type of its own
# and so the default "octoprint" (src/libslic3r/PrintConfig.cpp:6024); a person
# may also have chosen Moonraker. Such a printer may run the stock firmware or
# Moonraker, so its own answer decides.
_CREALITY_OTHER_HOST_TYPES = frozenset({"octoprint", "moonraker"})
CREALITY_ROUTE_KNOWN = "known"
CREALITY_ROUTE_PROBE = "probe"
_CREALITY_USAGE_STATES = {1: "printing", 5: "paused", 2: "complete", 3: "error", 4: "cancelled"}
_CREALITY_STATES = {1: "printing", 5: "paused", 2: "finished", 3: "failed", 4: "failed"}


def creality_host(print_host):
    """Return only the host name or address from Orca's print_host setting.

    The status channel and ``/info`` have fixed ports, so a scheme or port
    written there is ignored.
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


def creality_profile_route(host_type, printer_agent, printer_model):
    """How an OrcaSlicer profile reaches the stock firmware: ``"known"``, ``"probe"`` or ``""``.

    A profile of type or agent "crealityprint" is a Creality printer outright.
    A K1, K2 or SPARKX i7 profile of another type is offered only once the
    printer answers ``/info`` as a Creality printer.
    """
    kinds = {str(value or "").strip().lower() for value in (host_type, printer_agent)}
    if CREALITY_HOST_TYPE in kinds:
        return CREALITY_ROUTE_KNOWN
    if (
        str(host_type or "").strip().lower() in _CREALITY_OTHER_HOST_TYPES
        and str(printer_model or "").startswith(CREALITY_STOCK_MODEL_PREFIXES)
    ):
        return CREALITY_ROUTE_PROBE
    return ""


def creality_info_url(address):
    host = "[%s]" % address if ":" in address else address
    return "http://%s:%d/info" % (host, CREALITY_INFO_PORT)


def creality_mac(info):
    """The printer's MAC address from ``/info`` as twelve hex digits, or ``""``."""
    value = info.get("mac") if isinstance(info, dict) else None
    if not isinstance(value, str):
        return ""
    compact = re.sub(r"[\s:._-]+", "", value).upper()
    return compact if _CREALITY_MAC.fullmatch(compact) and compact.strip("0") else ""


def _creality_base64(raw):
    return codecs.encode(raw, "base64").replace(b"\n", b"")


def creality_ws_handshake(address, key_bytes, port=CREALITY_WS_PORT, path="/"):
    """The opening request of a WebSocket; ``key_bytes`` is 16 random bytes.

    The plugin's other LAN printers that speak WebSocket open theirs the same
    way on their own port and path.
    """
    host = "[%s]" % address if ":" in address else address
    return (
        b"GET " + path.encode("ascii") + b" HTTP/1.1\r\n"
        b"Host: " + ("%s:%d" % (host, port)).encode("ascii") + b"\r\n"
        b"Upgrade: websocket\r\n"
        b"Connection: Upgrade\r\n"
        b"Sec-WebSocket-Key: " + _creality_base64(key_bytes) + b"\r\n"
        b"Sec-WebSocket-Version: 13\r\n"
        b"\r\n"
    )


def creality_ws_accepted(response_head, key_bytes):
    """Whether the printer's answer to the opening request accepts this very client."""
    try:
        lines = response_head.decode("iso-8859-1").split("\r\n")
    except AttributeError:
        return False
    status = lines[0].split(" ")
    if len(status) < 2 or status[1] != "101":
        return False
    expected = _creality_base64(
        hashlib.sha1(_creality_base64(key_bytes) + _CREALITY_WS_GUID).digest()
    ).decode("ascii")
    for line in lines[1:]:
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() == "sec-websocket-accept":
            return value.strip() == expected
    return False


def creality_ws_frame(text, mask_bytes, opcode=1):
    """One client frame; the K1 family reads text frames only."""
    payload = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    size = len(payload)
    if size < 126:
        head = struct.pack("!BB", 0x80 | opcode, 0x80 | size)
    elif size < 65536:
        head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, size)
    else:
        head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, size)
    masked = bytes(byte ^ mask_bytes[index % 4] for index, byte in enumerate(payload))
    return head + bytes(mask_bytes[:4]) + masked


def creality_ws_frames(buffer):
    """Split received bytes into whole frames: ``([(final, opcode, payload)], rest)``.

    Raises ValueError for a frame larger than a status message can be.
    """
    frames = []
    offset = 0
    while len(buffer) - offset >= 2:
        first, second = buffer[offset], buffer[offset + 1]
        size = second & 0x7F
        head = 2
        if size == 126:
            if len(buffer) - offset < 4:
                break
            size = struct.unpack_from("!H", buffer, offset + 2)[0]
            head = 4
        elif size == 127:
            if len(buffer) - offset < 10:
                break
            size = struct.unpack_from("!Q", buffer, offset + 2)[0]
            head = 10
        if size > CREALITY_MAX_FRAME_BYTES:
            raise ValueError("Creality frame is too large")
        masked = bool(second & 0x80)
        if masked:
            head += 4
        if len(buffer) - offset < head + size:
            break
        payload = bytes(buffer[offset + head:offset + head + size])
        if masked:
            mask = buffer[offset + head - 4:offset + head]
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        frames.append((bool(first & 0x80), first & 0x0F, payload))
        offset += head + size
    return frames, bytes(buffer[offset:])


def creality_message(payload):
    """One received text as a status object, or None for anything else."""
    try:
        message = json.loads(payload.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return None
    return message if isinstance(message, dict) else None


def creality_is_heartbeat(message):
    return isinstance(message, dict) and message.get("ModeCode") == "heart_beat"


def _creality_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if number == number and abs(number) != float("inf") else None


def _creality_integer(value):
    number = _creality_number(value)
    return int(number) if number is not None and number == int(number) else None


def _creality_file_name(status):
    name = status.get("printFileName")
    if not isinstance(name, str):
        return ""
    return name.replace("\\", "/").rsplit("/", 1)[-1].strip()[:300]


def _creality_paused(status):
    return _creality_integer(status.get("state")) == 5 or any(
        _creality_integer(status.get(key)) == 1 for key in ("pause", "isPaused")
    )


def creality_printer(status):
    """Normalize printer status into the provider-neutral bridge contract."""
    code = _creality_integer(status.get("state"))
    job = _creality_file_name(status)
    if code == 1 and _creality_paused(status):
        state = "paused"
    elif code in _CREALITY_STATES:
        state = _CREALITY_STATES[code]
    elif code == 0 and not job:
        state = "idle"
    elif code == 9:
        # The moment between accepting a job and printing it.
        state = "preparing"
    else:
        state = "unknown"
    printer = {"state": state}
    if job and state in {"printing", "paused", "preparing", "finished", "failed"}:
        printer["job_name"] = job
        progress = _creality_number(status.get("printProgress"))
        if progress is not None and 0 <= progress <= 100:
            printer["progress_percent"] = round(progress)
        if state in {"printing", "paused", "preparing"}:
            remaining = _creality_number(status.get("printLeftTime"))
            if remaining is not None and 0 <= remaining <= 2_592_000:
                printer["remaining_seconds"] = int(remaining)
        layer = _creality_integer(status.get("layer"))
        total = _creality_integer(status.get("TotalLayer"))
        if layer is not None and 0 <= layer <= 10_000_000:
            printer["current_layer"] = layer
        if total is not None and 0 < total <= 10_000_000:
            printer["total_layers"] = total
    for key, source, low, high in (
        ("nozzle_temperature", "nozzleTemp", -50, 600),
        ("nozzle_target_temperature", "targetNozzleTemp", 0, 600),
        ("bed_temperature", "bedTemp0", -50, 250),
        ("bed_target_temperature", "targetBedTemp0", 0, 250),
        ("chamber_temperature", "boxTemp", -50, 150),
    ):
        value = _creality_number(status.get(source))
        if value is not None and low <= value <= high:
            printer[key] = round(value, 1)
    return printer


def creality_usage(status):
    """The job's filament so far, as the usage books read it, or None."""
    if not isinstance(status, dict):
        return None
    code = _creality_integer(status.get("state"))
    job = _creality_file_name(status)
    if code == 0 and not job:
        return {"state": "standby", "filament_used_mm": 0.0}
    state = _CREALITY_USAGE_STATES.get(code)
    if state == "printing" and _creality_paused(status):
        state = "paused"
    used = _creality_number(status.get("usedMaterialLength"))
    if (
        state is None
        or not job
        or used is None
        or not 0 <= used <= CREALITY_MAX_JOB_LENGTH_MM
    ):
        return None
    usage = {"state": state, "file_name": job, "filament_used_mm": used}
    duration = _creality_number(status.get("printJobTime"))
    if duration is not None and 0 <= duration <= 31_536_000:
        usage["duration_s"] = duration
    return usage


def _creality_color(value):
    match = _CREALITY_COLOR.fullmatch(value.strip()) if isinstance(value, str) else None
    # The printer writes a colour as "#" + one digit + "RRGGBB".
    return match.group(1).upper() if match else None


def _creality_slot(material, index, label, kind, active_rule):
    state = _creality_integer(material.get("state")) if isinstance(material, dict) else None
    slot = {
        "provider_index": index,
        "label": label,
        "kind": kind,
        "present": None,
        "spool_identity_known": False,
    }
    if state is None:
        return slot
    texts = {
        key: material.get(key).strip() if isinstance(material.get(key), str) else ""
        for key in ("vendor", "type", "color")
    }
    # A slot the printer has filled in says something about its filament.
    present = state != 0 and any(texts.values())
    slot["present"] = present
    if active_rule == "selected":
        slot["active_feed"] = present and _creality_integer(material.get("selected")) == 1
    elif active_rule == "state":
        slot["active_feed"] = present and state == 1
    if present:
        if texts["type"]:
            slot["material"] = texts["type"][:80]
        color = _creality_color(texts["color"])
        if color:
            slot["color_hex"] = color
        percent = _creality_integer(material.get("percent"))
        if percent is not None and 0 <= percent <= 100:
            slot["remaining_percent"] = percent
    return slot


def creality_slots(boxes_info):
    """Turn a ``boxsInfo`` answer into slots; return ``(slots, complete)``.

    A CFS holds four slots and up to four of them are chained; the printer's
    own spool holder is listed as a box of another type. ``complete`` says the
    answer named every slot of every CFS it listed.

    Which slot feeds: firmware that marks it writes ``selected`` on each slot.
    Older K2 Plus firmware has no such field and tells a selected spool (state
    1) from one that is merely loaded (state 2). Firmware that does neither
    leaves the feed unknown.
    """
    info = boxes_info.get("boxsInfo") if isinstance(boxes_info, dict) else None
    boxes = info.get("materialBoxs") if isinstance(info, dict) else None
    if not isinstance(boxes, list):
        return [], False
    boxes = [box for box in boxes if isinstance(box, dict)]
    materials = [
        material
        for box in boxes
        for material in (box.get("materials") if isinstance(box.get("materials"), list) else [])
        if isinstance(material, dict)
    ]
    if any("selected" in material for material in materials):
        active_rule = "selected"
    elif any(_creality_integer(material.get("state")) == 2 for material in materials):
        active_rule = "state"
    else:
        active_rule = None

    slots = []
    complete = True
    cfs_number = 0
    external_seen = False
    for box in boxes:
        box_type = _creality_integer(box.get("type"))
        listed = box.get("materials") if isinstance(box.get("materials"), list) else []
        by_id = {
            _creality_integer(material.get("id")): material
            for material in listed if isinstance(material, dict)
        }
        if box_type == 1:
            if external_seen:
                continue
            external_seen = True
            slots.append(_creality_slot(
                by_id.get(0), CREALITY_EXTERNAL_INDEX, "External spool", "external", active_rule
            ))
        elif box_type == 0:
            # A CFS that is listed and not connected has no slots to show.
            if _creality_integer(box.get("state")) != 1 or cfs_number >= CREALITY_MAX_BOXES:
                continue
            for slot_id in range(CREALITY_SLOTS_PER_BOX):
                if slot_id not in by_id:
                    complete = False
                slots.append(_creality_slot(
                    by_id.get(slot_id),
                    cfs_number * CREALITY_SLOTS_PER_BOX + slot_id,
                    "CFS %d slot %d" % (cfs_number + 1, slot_id + 1),
                    "slot",
                    active_rule,
                ))
            cfs_number += 1
    slots.sort(key=lambda slot: slot["provider_index"])
    return slots, complete and bool(slots)
