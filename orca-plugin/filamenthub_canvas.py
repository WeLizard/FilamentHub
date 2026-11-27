"""Elegoo CANVAS slots for the FilamentHub OrcaSlicer plugin.

CANVAS is Elegoo's four-slot multi-colour unit. A printer describes its units
in the same object over SDCP (command 324) and over the Centauri Carbon 2's
MQTT API (method 2005), so both adapters turn it into slots here.

Sources:

[link]  elegooofficial/elegoo-link @ ec2d2269: ``handleCanvasStatus`` in
        ``src/lan/adapters/elegoo_fdm_cc/elegoo_fdm_cc_message_adapter.cpp``
        l. 902-947 and in
        ``src/lan/adapters/elegoo_fdm_cc2/elegoo_fdm_cc2_message_adapter.cpp``
        l. 1216-1260 read the same fields: ``canvas_list[].canvas_id``,
        ``connected``, ``tray_list[].tray_id``, ``filament_type``,
        ``filament_name``, ``filament_color``, ``status``.
[orca]  OrcaSlicer/OrcaSlicer @ 7cdc829a,
        ``resources/web/elegoolink/lan_service_web/index.html`` (Elegoo's
        bundled panel): tray status 0 empty, 1 spool in the slot, 2 loaded
        into the toolhead (enum ``Empty`` / ``preViewLoad`` / ``loaded``); the
        single spool's ``mono_filament_info`` (method ``GetMonoFilamentInfo``).
[ha]    danielcherubini/elegoo-homeassistant @ ce9c1559,
        ``custom_components/elegoo_printer/sdcp/models/ams.py`` l. 24-29:
        trays are numbered from 0.

Not confirmed by a source: whether ``mono_filament_info`` carries a tray
status; without one the single spool's presence is left unknown.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import re

CANVAS_SLOTS_PER_UNIT = 4
CANVAS_MAX_UNITS = 4
CANVAS_EXTERNAL_INDEX = 255
_CANVAS_COLOR = re.compile(r"#?([0-9A-Fa-f]{6})(?:[0-9A-Fa-f]{2})?")
_CANVAS_TRAY_EMPTY = 0
_CANVAS_TRAY_LOADED = 2


def _canvas_integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if value == value and value == int(value) else None


def _canvas_text(tray, key):
    value = tray.get(key)
    return value.strip() if isinstance(value, str) else ""


def _canvas_slot(tray, index, label, kind, any_loaded):
    slot = {
        "provider_index": index,
        "label": label,
        "kind": kind,
        "present": None,
        "spool_identity_known": False,
    }
    if not isinstance(tray, dict):
        return slot
    status = _canvas_integer(tray.get("status"))
    present = status != _CANVAS_TRAY_EMPTY if status is not None else None
    slot["present"] = present
    if any_loaded and status is not None:
        slot["active_feed"] = present and status == _CANVAS_TRAY_LOADED
    if present is not False:
        # "?" and a name starting with a dash stand for nothing recognised ([ha] l. 36-42).
        material = _canvas_text(tray, "filament_type")
        name = _canvas_text(tray, "filament_name")
        material = (material if material != "?" else "") or (
            name if not name.startswith("—") else ""
        )
        if material:
            slot["material"] = material[:80]
        match = _CANVAS_COLOR.fullmatch(_canvas_text(tray, "filament_color"))
        if match:
            slot["color_hex"] = match.group(1).upper()
    return slot


def _canvas_places(trays):
    """Each tray's place 0-3 in its unit: ``({place: tray}, complete)``."""
    by_id = {}
    for tray in trays:
        tray_id = _canvas_integer(tray.get("tray_id"))
        if tray_id is not None and tray_id not in by_id:
            by_id[tray_id] = tray
    ids = sorted(by_id)
    # Trays are numbered from 0 ([ha]); a unit described from 1 is read as such.
    base = ids[0] if len(ids) == CANVAS_SLOTS_PER_UNIT else (1 if CANVAS_SLOTS_PER_UNIT in ids else 0)
    places = {
        tray_id - base: tray for tray_id, tray in by_id.items()
        if 0 <= tray_id - base < CANVAS_SLOTS_PER_UNIT
    }
    return places, len(places) == CANVAS_SLOTS_PER_UNIT


def canvas_units(canvas_info):
    """The connected units of a CANVAS answer, or None when it lists none at all."""
    units = canvas_info.get("canvas_list") if isinstance(canvas_info, dict) else None
    if not isinstance(units, list):
        return None
    return [
        unit for unit in units
        if isinstance(unit, dict) and unit.get("connected") in (True, 1)
    ][:CANVAS_MAX_UNITS]


def canvas_slots(canvas_info):
    """Slots of the connected CANVAS units: ``(slots, complete)``.

    Each unit holds four slots. The slot that feeds is the one whose filament
    is loaded into the toolhead; when none is, no slot is said to feed.
    """
    units = canvas_units(canvas_info) or []
    trays_by_unit = [
        [tray for tray in unit["tray_list"] if isinstance(tray, dict)]
        if isinstance(unit.get("tray_list"), list) else []
        for unit in units
    ]
    any_loaded = any(
        _canvas_integer(tray.get("status")) == _CANVAS_TRAY_LOADED
        for trays in trays_by_unit for tray in trays
    )
    slots = []
    complete = bool(trays_by_unit)
    for number, trays in enumerate(trays_by_unit):
        places, full = _canvas_places(trays)
        complete = complete and full
        for place in range(CANVAS_SLOTS_PER_UNIT):
            slots.append(_canvas_slot(
                places.get(place),
                number * CANVAS_SLOTS_PER_UNIT + place,
                "CANVAS %d slot %d" % (number + 1, place + 1),
                "slot",
                any_loaded,
            ))
    return slots, complete


def canvas_single_spool(mono_info):
    """The printer's own spool holder, with the material set on the printer if known."""
    return _canvas_slot(
        mono_info if isinstance(mono_info, dict) else None,
        CANVAS_EXTERNAL_INDEX, "Spool holder", "external", False,
    )
