"""Moonraker printers for the FilamentHub OrcaSlicer plugin: Happy Hare and QIDI Box.

Both material systems are read through Moonraker's printer objects. This file
says what to ask for and what the answer means: gate arrays of a Happy Hare
unit, slot variables and the filament dictionary of a QIDI Box, and the shape
of a Moonraker address. Nothing here sends a request.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

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
