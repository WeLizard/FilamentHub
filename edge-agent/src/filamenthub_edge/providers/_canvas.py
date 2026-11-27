"""CANVAS slots, as SDCP printers and Elegoo's MQTT interface report them alike.

CANVAS is Elegoo's four-slot multi-colour unit. A printer describes its units
in the same object over SDCP (command 324) and over the Centauri Carbon 2's
MQTT interface (method 2005); the OrcaSlicer plugin reads it the same way in
``orca-plugin/filamenthub_canvas.py``, and both are held to the fixtures in
``edge-agent/tests/fixtures/sdcp`` and ``elegoo_mqtt``.

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
        into the toolhead; the single spool's ``mono_filament_info``.
[ha]    danielcherubini/elegoo-homeassistant @ ce9c1559,
        ``custom_components/elegoo_printer/sdcp/models/ams.py`` l. 24-29:
        trays are numbered from 0.

Not confirmed by a source: whether ``mono_filament_info`` carries a tray
status; without one the single spool's presence is left unknown.
"""

from __future__ import annotations

import math
import re
from typing import Any

SLOTS_PER_UNIT = 4
MAX_UNITS = 4
SPOOL_HOLDER_INDEX = 255
_COLOR = re.compile(r"#?([0-9A-Fa-f]{6})(?:[0-9A-Fa-f]{2})?")
_TRAY_EMPTY = 0
_TRAY_LOADED = 2


def integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value != int(value):
        return None
    return int(value)


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def job_name(value: Any) -> str:
    """The file name of a job without its folder, or ``""``."""
    if not isinstance(value, str):
        return ""
    return value.replace("\\", "/").rsplit("/", 1)[-1].strip()[:300]


def _text(tray: dict[str, Any], key: str) -> str:
    value = tray.get(key)
    return value.strip() if isinstance(value, str) else ""


def _slot(
    tray: dict[str, Any] | None, index: int, label: str, kind: str, any_loaded: bool
) -> dict[str, Any]:
    slot: dict[str, Any] = {
        "provider_index": index,
        "label": label,
        "kind": kind,
        "present": None,
        "spool_identity_known": False,
    }
    if tray is None:
        return slot
    status = integer(tray.get("status"))
    present = status != _TRAY_EMPTY if status is not None else None
    slot["present"] = present
    if any_loaded and status is not None:
        slot["active_feed"] = bool(present and status == _TRAY_LOADED)
    if present is not False:
        # "?" and a name starting with a dash stand for nothing recognised ([ha]).
        material = _text(tray, "filament_type")
        name = _text(tray, "filament_name")
        material = (material if material != "?" else "") or (
            name if not name.startswith("—") else ""
        )
        if material:
            slot["material"] = material[:80]
        match = _COLOR.fullmatch(_text(tray, "filament_color"))
        if match:
            slot["color_hex"] = match.group(1).upper()
    return slot


def _places(trays: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], bool]:
    """Each tray's place 0-3 in its unit, and whether all four are there."""
    by_id: dict[int, dict[str, Any]] = {}
    for tray in trays:
        tray_id = integer(tray.get("tray_id"))
        if tray_id is not None and tray_id not in by_id:
            by_id[tray_id] = tray
    ids = sorted(by_id)
    # Trays are numbered from 0 ([ha]); a unit described from 1 is read as such.
    if len(ids) == SLOTS_PER_UNIT:
        base = ids[0]
    else:
        base = 1 if SLOTS_PER_UNIT in ids else 0
    places = {
        tray_id - base: tray
        for tray_id, tray in by_id.items()
        if 0 <= tray_id - base < SLOTS_PER_UNIT
    }
    return places, len(places) == SLOTS_PER_UNIT


def connected_units(canvas_info: Any) -> list[dict[str, Any]] | None:
    """The connected units of a CANVAS answer, or None when it lists none at all."""
    units = canvas_info.get("canvas_list") if isinstance(canvas_info, dict) else None
    if not isinstance(units, list):
        return None
    return [
        unit for unit in units if isinstance(unit, dict) and unit.get("connected") in (True, 1)
    ][:MAX_UNITS]


def canvas_slots(canvas_info: Any) -> tuple[list[dict[str, Any]], bool]:
    """Slots of the connected units and whether they are the whole feed.

    The slot that feeds is the one whose filament is loaded into the
    toolhead; when none is, no slot is said to feed.
    """
    units = connected_units(canvas_info) or []
    trays_by_unit = [
        [tray for tray in unit["tray_list"] if isinstance(tray, dict)]
        if isinstance(unit.get("tray_list"), list)
        else []
        for unit in units
    ]
    any_loaded = any(
        integer(tray.get("status")) == _TRAY_LOADED for trays in trays_by_unit for tray in trays
    )
    slots = []
    complete = bool(trays_by_unit)
    for unit, trays in enumerate(trays_by_unit):
        places, full = _places(trays)
        complete = complete and full
        for place in range(SLOTS_PER_UNIT):
            slots.append(
                _slot(
                    places.get(place),
                    unit * SLOTS_PER_UNIT + place,
                    f"CANVAS {unit + 1} slot {place + 1}",
                    "slot",
                    any_loaded,
                )
            )
    return slots, complete


def single_spool(mono_info: Any) -> dict[str, Any]:
    """The printer's own spool holder, with the material set on the printer if known.

    It is the only feed a printer without CANVAS has.
    """
    slot = _slot(
        mono_info if isinstance(mono_info, dict) else None,
        SPOOL_HOLDER_INDEX,
        "Spool holder",
        "external",
        False,
    )
    slot["active_feed"] = True
    return slot


def feed(
    canvas_info: Any, mono_info: Any, *, canvas_answered: bool
) -> tuple[list[dict[str, Any]], bool]:
    """The printer's feed: CANVAS slots, its spool holder, or nothing known.

    ``canvas_answered`` says whether the printer was asked about CANVAS and
    said whether a unit is there; a printer that was asked and did not say
    gets no slots rather than a guessed spool holder.
    """
    if connected_units(canvas_info):
        return canvas_slots(canvas_info)
    if canvas_answered or mono_info is not None:
        return [single_spool(mono_info)], True
    return [], False
