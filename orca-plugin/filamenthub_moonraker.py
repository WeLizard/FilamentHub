"""Moonraker printers for the FilamentHub OrcaSlicer plugin: Happy Hare and QIDI Box.

Both material systems are read through Moonraker's printer objects. This file
says what to ask for and what the answer means: gate arrays of a Happy Hare
unit, slot variables and the filament dictionary of a QIDI Box, the length of
filament a job has used so far, and the shape of a Moonraker address. Nothing
here sends a request.

Klipper counts the filament its extruder moves (``print_stats.filament_used``).
The plugin charges it to the spool in the slot that is feeding, unless
Moonraker's own Spoolman link points at FilamentHub: that link reports the same
print itself, and counting it here as well would deduct it twice. A link to
some other Spoolman tells FilamentHub nothing, so the plugin counts.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import math
import re
import urllib.parse


def _moonraker_base_url(value):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Moonraker address is empty")
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urllib.parse.urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)*/?", parsed.path)
        or any(part in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise ValueError("Moonraker address or route prefix is invalid")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Moonraker port is invalid") from exc
    host = parsed.hostname
    if ":" in host:
        host = "[" + host + "]"
    return "%s://%s%s%s" % (
        parsed.scheme,
        host,
        (":" + str(port)) if port is not None else "",
        parsed.path.rstrip("/"),
    )


_HH_ARRAY_FIELDS = (
    "gate_status",
    "gate_material",
    "gate_color",
    "gate_temperature",
    "gate_spool_id",
    "gate_spool_rfid",
)


def _physical_tag_uid(value):
    """Normalize raw provider evidence without assigning provider ownership."""
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[\s:_.-]+", "", value).strip().upper()
    if normalized.startswith("0X"):
        normalized = normalized[2:]
    if (
        len(normalized) < 2
        or len(normalized) > 64
        or len(normalized) % 2
        or re.fullmatch(r"[0-9A-F]+", normalized) is None
    ):
        return None
    return normalized


# What one read of a Happy Hare unit asks Moonraker for.
HAPPY_HARE_STATUS_OBJECTS = {
    "mmu": [
        "num_gates",
        "gate_status",
        "gate_material",
        "gate_color",
        "gate_temperature",
        "gate_spool_id",
        "gate_spool_rfid",
        "spoolman_support",
        "has_bypass",
        "tool",
        "gate",
        "filament_pos",
    ],
    "print_stats": ["state"],
}


def parse_happy_hare_status(status_map):
    """Turn the queried printer objects into one complete Happy Hare topology.

    The printer's host name and the inventory key digest come from other
    requests; the caller fills them in.
    """
    mmu = status_map.get("mmu") if isinstance(status_map, dict) else None
    if not isinstance(mmu, dict):
        raise ValueError("Happy Hare object 'mmu' is unavailable")

    arrays = {}
    lengths = set()
    for key in _HH_ARRAY_FIELDS:
        value = mmu.get(key)
        if value is None:
            arrays[key] = None
            continue
        if not isinstance(value, list):
            raise ValueError("Happy Hare %s is not an array" % key)
        arrays[key] = value
        lengths.add(len(value))

    raw_count = mmu.get("num_gates")
    if isinstance(raw_count, bool):
        raw_count = None
    try:
        gate_count = int(raw_count) if raw_count is not None else None
    except (TypeError, ValueError):
        gate_count = None
    if gate_count is None:
        if len(lengths) != 1:
            raise ValueError("Happy Hare gate count cannot be determined safely")
        gate_count = next(iter(lengths))
    if gate_count < 1 or gate_count > 256:
        raise ValueError("Happy Hare gate count is outside 1..256")
    if any(length != gate_count for length in lengths):
        raise ValueError("Happy Hare gate arrays disagree with num_gates")

    def value_at(key, index, default):
        values = arrays.get(key)
        return values[index] if values is not None else default

    gates = []
    actual_spool_ids = []
    for gate in range(gate_count):
        try:
            hh_status = int(value_at("gate_status", gate, -1))
        except (TypeError, ValueError):
            hh_status = -1
        if hh_status not in {-1, 0, 1, 2}:
            hh_status = -1
        material = str(value_at("gate_material", gate, "") or "")[:50]
        color = str(value_at("gate_color", gate, "") or "").lstrip("#").upper()
        if not re.fullmatch(r"[0-9A-F]{6}", color):
            color = ""
        try:
            temperature = max(0, int(value_at("gate_temperature", gate, 0) or 0))
        except (TypeError, ValueError):
            temperature = 0
        try:
            spool_id = int(value_at("gate_spool_id", gate, -1))
        except (TypeError, ValueError):
            spool_id = -1
        actual_spool_ids.append(spool_id if spool_id > 0 else None)
        rfid_uid = _physical_tag_uid(value_at("gate_spool_rfid", gate, ""))
        gate_item = {
            "gate": gate,
            "status": hh_status,
            "material": material,
            "color_hex": color,
            "temperature": temperature,
        }
        if rfid_uid is not None:
            gate_item["rfid_uid"] = rfid_uid
        gates.append(gate_item)

    print_stats = (
        status_map.get("print_stats") if isinstance(status_map, dict) else None
    )
    print_state = (
        str(print_stats.get("state") or "").strip().lower()
        if isinstance(print_stats, dict)
        else ""
    )
    raw_has_bypass = mmu.get("has_bypass")
    has_bypass = raw_has_bypass if isinstance(raw_has_bypass, bool) else None
    raw_tool = mmu.get("tool")
    try:
        selected_tool = int(raw_tool) if not isinstance(raw_tool, bool) else None
    except (TypeError, ValueError):
        selected_tool = None
    raw_gate = mmu.get("gate")
    selected_gate = raw_gate if type(raw_gate) is int and -2 <= raw_gate < gate_count else None
    bypass_selected = selected_gate == -2 or selected_tool == -2
    raw_filament_pos = mmu.get("filament_pos")
    try:
        filament_pos = float(raw_filament_pos) if not isinstance(raw_filament_pos, bool) else None
    except (TypeError, ValueError):
        filament_pos = None
    if bypass_selected:
        # A selected bypass is stronger evidence than an omitted capability
        # field from an older Happy Hare build.
        has_bypass = True
    bypass = None
    if has_bypass is True:
        bypass_present = None
        if bypass_selected and filament_pos is not None and filament_pos >= 0:
            bypass_present = filament_pos > 0
        bypass = {
            "selected": bypass_selected,
            "present": bypass_present,
        }
    return {
        "gate_count": gate_count,
        "gates": gates,
        "actual_spool_ids": actual_spool_ids,
        "spool_ids_known": arrays.get("gate_spool_id") is not None,
        "tag_read_capable": arrays.get("gate_spool_rfid") is not None,
        "spoolman_support": str(mmu.get("spoolman_support") or "").strip().lower(),
        "print_state": print_state,
        "printer_hostname": "",
        "has_bypass": has_bypass,
        "bypass": bypass,
        "selected_gate": selected_gate,
        "filament_loaded": filament_pos > 0 if filament_pos is not None and filament_pos >= 0 else None,
        "inventory_key_digest": None,
    }


# QIDI Box through Moonraker. Pinned to OrcaSlicer's QidiPrinterAgent
# (OrcaSlicer/OrcaSlicer a65ae5fe, src/slic3r/Utils/QidiPrinterAgent.cpp:86-216
# slot variables and presence, 218-330 dictionary, 390-412 type normalisation).
_QIDI_STEPPER_PREFIX = "box_stepper slot"
_QIDI_SLOTS_PER_BOX = 4
_QIDI_MAX_SLOTS = 16
_QIDI_DICT_PATH = "/server/files/config/officiall_filas_list.cfg"


def _qidi_box_present(objects):
    return any(
        isinstance(name, str) and name.startswith(_QIDI_STEPPER_PREFIX)
        for name in objects
    )


def _qidi_parse_dictionary(text):
    colors, filaments, section = {}, {}, ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator:
            continue
        if section == "colordict" and key.isdigit():
            colors[int(key)] = value
        elif section.startswith("fila") and section[4:].isdigit() and key == "filament":
            if int(section[4:]) > 0:
                filaments[int(section[4:])] = value
    return colors, filaments


def _qidi_material(name):
    upper = name.strip().upper()
    for known in ("PLA", "ABS", "PETG", "TPU", "ASA"):
        if known in upper:
            return known
    if "PA" in upper or "NYLON" in upper:
        return "PA"
    for known in ("PC", "PVA"):
        if known in upper:
            return known
    return upper


def _qidi_int(value, default):
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def qidi_box_loaded_slot(variables):
    """The Box slot whose filament is loaded into the extruder.

    The Box's own macros keep it in ``last_load_slot``: ``"slotN"``, or
    ``"slot-1"`` when nothing is loaded (qidi-community/Plus4-Wiki,
    ``customisable_qidibox_firmware/box_macros.cfg``). Returns the slot index,
    -1 when nothing is loaded and None when the printer does not say.
    """
    value = variables.get("last_load_slot") if isinstance(variables, dict) else None
    if value == "slot-1":
        return -1
    match = re.fullmatch(r"slot(\d{1,2})", value) if isinstance(value, str) else None
    if match is None or int(match.group(1)) >= _QIDI_MAX_SLOTS:
        return None
    return int(match.group(1))


def qidi_box_query():
    """What one read of a QIDI Box asks Moonraker for."""
    query = {"save_variables": ["variables"]}
    for index in range(_QIDI_MAX_SLOTS):
        query["%s%d" % (_QIDI_STEPPER_PREFIX, index)] = ["runout_button"]
    return query


def qidi_box_variables(state):
    """Return the box's saved variables from the queried printer objects."""
    saved = state.get("save_variables") if isinstance(state, dict) else None
    variables = saved.get("variables") if isinstance(saved, dict) else None
    if not isinstance(variables, dict):
        raise ValueError("QIDI Box save_variables are unavailable")
    return variables


def parse_qidi_box_slots(state, variables, dictionary_text):
    """Turn the queried objects and the printer's filament dictionary into slots."""
    colors, filaments = _qidi_parse_dictionary(dictionary_text)
    slot_count = min(
        max(0, _qidi_int(variables.get("box_count"), 1)) * _QIDI_SLOTS_PER_BOX,
        _QIDI_MAX_SLOTS,
    )
    loaded = qidi_box_loaded_slot(variables)
    slots = []
    for index in range(slot_count):
        stepper = state.get("%s%d" % (_QIDI_STEPPER_PREFIX, index))
        runout = stepper.get("runout_button") if isinstance(stepper, dict) else None
        present = None
        if isinstance(runout, (int, float)) and not isinstance(runout, bool):
            # A closed runout button (0) means filament is in the slot.
            present = runout == 0
        slot = {
            "provider_index": index,
            "label": "Box %d slot %d" % (
                index // _QIDI_SLOTS_PER_BOX + 1, index % _QIDI_SLOTS_PER_BOX + 1
            ),
            "kind": "slot",
            "present": present,
            "spool_identity_known": False,
        }
        if loaded is not None:
            slot["active_feed"] = index == loaded
        if present:
            name = filaments.get(_qidi_int(variables.get("filament_slot%d" % index), 1))
            if name:
                slot["material"] = _qidi_material(name)[:80]
            color = str(colors.get(_qidi_int(variables.get("color_slot%d" % index), 1)) or "")
            color = color.strip().lstrip("#").upper()
            if re.fullmatch(r"[0-9A-F]{6}([0-9A-F]{2})?", color):
                slot["color_hex"] = color[:6]
        slots.append(slot)
    return slots


# Filament usage through Moonraker. ``happy_hare`` is a printer with that MMU;
# ``legacy`` is any other Klipper printer.
MOONRAKER_USAGE_PROVIDERS = ("happy_hare", "legacy")
# The slot index FilamentHub gives the Happy Hare bypass.
MOONRAKER_BYPASS_PROVIDER_INDEX = 1023
_MOONRAKER_USAGE_STATES = frozenset(
    {"standby", "printing", "paused", "complete", "cancelled", "error"}
)
_MOONRAKER_MAX_JOB_LENGTH_MM = 10_000_000.0


# What a reading asks for to show the printer's state on FilamentHub. Sources,
# Klipper 7558e8c2: print_stats.py:113 (state, filename, info layers),
# display_status.py:22 (progress 0..1), heaters.py:153 and heater_bed.py:12
# (temperature, target), kinematics/extruder.py:192 (an extruder reports its
# heater). An object the printer lacks comes back empty (webhooks.py:506).
MOONRAKER_STATUS_OBJECTS = {
    "print_stats": ["state", "filename", "info"],
    "display_status": ["progress"],
    "extruder": ["temperature", "target"],
    "heater_bed": ["temperature", "target"],
}
# Klipper's print_stats.py sets exactly these states. The bridge contract has no
# "cancelled"; it is a job that did not finish, as for Creality.
_MOONRAKER_PRINTER_STATES = {
    "standby": "idle",
    "printing": "printing",
    "paused": "paused",
    "complete": "finished",
    "cancelled": "failed",
    "error": "failed",
}


def moonraker_usage_query(provider):
    """What one reading asks Moonraker for: the print's filament and its state."""
    objects = {name: list(fields) for name, fields in MOONRAKER_STATUS_OBJECTS.items()}
    objects["print_stats"] += ["filament_used", "print_duration"]
    if provider == "happy_hare":
        objects["mmu"] = list(HAPPY_HARE_STATUS_OBJECTS["mmu"]) + ["num_toolchanges"]
    else:
        # Where a QIDI Box says which of its slots is loaded; absent elsewhere.
        objects["save_variables"] = ["variables"]
    return objects


def moonraker_feed_mark(status_map):
    """Happy Hare's count of tool changes in this print, or None when it gives none.

    Two readings can show the same gate with a switch to another gate and back
    between them. The count tells such a stretch from one fed by a single spool.
    """
    mmu = status_map.get("mmu") if isinstance(status_map, dict) else None
    count = mmu.get("num_toolchanges") if isinstance(mmu, dict) else None
    return count if type(count) is int and count >= 0 else None


def moonraker_usage(status_map):
    """The job's filament so far, as the usage books read it, or None."""
    stats = status_map.get("print_stats") if isinstance(status_map, dict) else None
    if not isinstance(stats, dict):
        return None
    state = str(stats.get("state") or "").strip().lower()
    used = stats.get("filament_used")
    if (
        state not in _MOONRAKER_USAGE_STATES
        or isinstance(used, bool)
        or not isinstance(used, (int, float))
        or not 0 <= used <= _MOONRAKER_MAX_JOB_LENGTH_MM
    ):
        return None
    usage = {"state": state, "filament_used_mm": float(used)}
    name = stats.get("filename")
    if isinstance(name, str) and name.strip():
        usage["file_name"] = name.strip()[:300]
    duration = stats.get("print_duration")
    if (
        isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and 0 <= duration <= 31_536_000
    ):
        usage["duration_s"] = float(duration)
    return usage


def _moonraker_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def moonraker_printer(status_map):
    """The printer's state in the provider-neutral bridge contract, or None.

    Klipper does not say how long a print has left, so no remaining time is
    sent rather than an estimate.
    """
    stats = status_map.get("print_stats") if isinstance(status_map, dict) else None
    if not isinstance(stats, dict) or "state" not in stats:
        return None
    state = _MOONRAKER_PRINTER_STATES.get(str(stats.get("state") or "").strip().lower(), "unknown")
    printer: dict = {"state": state}
    job = stats.get("filename")
    if state not in {"idle", "unknown"} and isinstance(job, str) and job.strip():
        printer["job_name"] = job.strip()[:300]
    if state in {"printing", "paused"}:
        display = status_map.get("display_status")
        progress = _moonraker_number(display.get("progress")) if isinstance(display, dict) else None
        if progress is not None and 0 <= progress <= 1:
            printer["progress_percent"] = round(progress * 100)
        info = stats.get("info")
        if isinstance(info, dict):
            for key, field in (("current_layer", "current_layer"), ("total_layers", "total_layer")):
                value = info.get(field)
                # Klipper keeps None until a slicer's SET_PRINT_STATS_INFO says otherwise.
                if type(value) is int and 0 <= value <= 10_000_000:
                    printer[key] = value
    for key, name, field, low, high in (
        ("nozzle_temperature", "extruder", "temperature", -50, 600),
        ("nozzle_target_temperature", "extruder", "target", 0, 600),
        ("bed_temperature", "heater_bed", "temperature", -50, 250),
        ("bed_target_temperature", "heater_bed", "target", 0, 250),
    ):
        source = status_map.get(name)
        value = _moonraker_number(source.get(field)) if isinstance(source, dict) else None
        if value is not None and low <= value <= high:
            printer[key] = round(value, 1)
    return printer


def moonraker_spoolman_server(server_config):
    """The address in Moonraker's ``[spoolman]`` section, as ``/server/config`` gives it.

    Returns ``{"server": address}``; the address is None when there is no such
    section. Returns None when the answer cannot be read.
    """
    config = server_config.get("config") if isinstance(server_config, dict) else None
    if not isinstance(config, dict):
        return None
    if "spoolman" not in config:
        return {"server": None}
    spoolman = config["spoolman"]
    server = spoolman.get("server") if isinstance(spoolman, dict) else None
    return {"server": server} if isinstance(server, str) else None


def moonraker_reports_usage_itself(spoolman, own_hosts):
    """Whether Moonraker's own Spoolman link reports this printer's prints to FilamentHub.

    ``spoolman`` is what ``moonraker_spoolman_server`` returned and ``own_hosts``
    the host names FilamentHub answers on. An answer that cannot be read counts
    as yes: deducting nothing is recoverable, deducting twice is not.
    """
    if not isinstance(spoolman, dict):
        return True
    server = spoolman.get("server")
    if server is None:
        return False
    try:
        parsed = urllib.parse.urlsplit(server if "://" in server else "http://" + server)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return True
    # The path also gives FilamentHub away behind a proxy under another name.
    return not host or host in own_hosts or "/spool_compat/" in parsed.path


def moonraker_loaded_slot(status_map):
    """The slot a printer without Happy Hare says is loaded, or None when it says nothing."""
    saved = status_map.get("save_variables") if isinstance(status_map, dict) else None
    return qidi_box_loaded_slot(saved.get("variables") if isinstance(saved, dict) else None)


def moonraker_feed_slots(happy_hare, desired, loaded_slot=None):
    """Which slot is feeding, in the shape the usage books read.

    Happy Hare names the selected gate, and a QIDI Box the slot it loaded
    (``loaded_slot``). Another Klipper printer names nothing: with one slot on
    the site there is nothing to choose, and with several the slot is unknown,
    so nothing is charged.
    """
    if happy_hare is not None:
        loaded = happy_hare.get("filament_loaded") is True
        slots = [
            {
                "provider_index": gate,
                "active_feed": loaded and happy_hare.get("selected_gate") == gate,
            }
            for gate in range(happy_hare["gate_count"])
        ]
        bypass = happy_hare.get("bypass")
        if isinstance(bypass, dict):
            slots.append({
                "provider_index": MOONRAKER_BYPASS_PROVIDER_INDEX,
                "active_feed": loaded and bypass.get("selected") is True,
            })
        return slots
    known = [
        slot for slot in (desired.get("slots") if isinstance(desired, dict) else None) or []
        if isinstance(slot, dict) and type(slot.get("index")) is int
    ]
    if len(known) <= 1:
        return []
    return [
        {
            "provider_index": slot["index"],
            "active_feed": None if loaded_slot is None else slot["index"] == loaded_slot,
        }
        for slot in known
    ]


def moonraker_usage_capabilities(reports_itself):
    """What the plugin's usage link can do for this printer right now."""
    return ["read"] if reports_itself else ["read", "consumption"]
