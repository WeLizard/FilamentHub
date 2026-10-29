"""QIDI Box slot reader for Moonraker.

Behaviour is pinned to OrcaSlicer's QidiPrinterAgent
(OrcaSlicer/OrcaSlicer a65ae5fe, src/slic3r/Utils/QidiPrinterAgent.cpp:86-216
for slot variables and presence, 218-330 for the filament dictionary,
390-412 for type normalisation). The variable names and the dictionary file
are undocumented firmware details; this module only reads them.
"""

from __future__ import annotations

import re
from typing import Any

BOX_STEPPER_PREFIX = "box_stepper slot"
SLOTS_PER_BOX = 4
MAX_SLOTS = 16
DICT_PATH = "/server/files/config/officiall_filas_list.cfg"
COLOR_PATTERN = re.compile(r"^[0-9A-F]{6}(?:[0-9A-F]{2})?$")
_TYPE_ORDER = ("PLA", "ABS", "PETG", "TPU", "ASA", "PC", "PVA")


def is_qidi_box(objects: list[Any]) -> bool:
    return any(isinstance(name, str) and name.startswith(BOX_STEPPER_PREFIX) for name in objects)


def query_objects() -> dict[str, list[str] | None]:
    objects: dict[str, list[str] | None] = {"save_variables": ["variables"]}
    for index in range(MAX_SLOTS):
        objects[f"{BOX_STEPPER_PREFIX}{index}"] = ["runout_button"]
    return objects


def parse_dictionary(text: str) -> tuple[dict[int, str], dict[int, str]]:
    """Return (colors, filaments) from the printer's INI-like dictionary file."""
    colors: dict[int, str] = {}
    filaments: dict[int, str] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key, value = key.strip(), value.strip()
        if section == "colordict" and key.isdigit():
            colors[int(key)] = value
        elif section.startswith("fila") and section[4:].isdigit() and key == "filament":
            index = int(section[4:])
            if index > 0:
                filaments[index] = value
    return colors, filaments


def normalize_material(name: str) -> str:
    upper = name.strip().upper()
    for known in _TYPE_ORDER[:5]:
        if known in upper:
            return known
    if "PA" in upper or "NYLON" in upper:
        return "PA"
    for known in _TYPE_ORDER[5:]:
        if known in upper:
            return known
    return upper


def _color(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().lstrip("#").upper()
    if candidate.startswith("0X"):
        candidate = candidate[2:]
    if not COLOR_PATTERN.fullmatch(candidate):
        return None
    return candidate[:6]


def _integer(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_slots(
    status: dict[str, Any],
    colors: dict[int, str],
    filaments: dict[int, str],
) -> list[dict[str, Any]]:
    saved = status.get("save_variables")
    variables = saved.get("variables") if isinstance(saved, dict) else None
    if not isinstance(variables, dict):
        raise ValueError("QIDI Box save_variables are unavailable")
    box_count = max(0, _integer(variables.get("box_count"), 1))
    slot_count = min(box_count * SLOTS_PER_BOX, MAX_SLOTS)
    slots: list[dict[str, Any]] = []
    for index in range(slot_count):
        stepper = status.get(f"{BOX_STEPPER_PREFIX}{index}")
        runout = stepper.get("runout_button") if isinstance(stepper, dict) else None
        present: bool | None = None
        if runout is not None and not isinstance(runout, bool) and isinstance(runout, int | float):
            # A closed runout button (0) means filament is in the slot.
            present = runout == 0
        slot: dict[str, Any] = {
            "provider_index": index,
            "label": f"Box {index // SLOTS_PER_BOX + 1} slot {index % SLOTS_PER_BOX + 1}",
            "kind": "slot",
            "present": present,
            "spool_identity_known": False,
        }
        if present:
            name = filaments.get(_integer(variables.get(f"filament_slot{index}"), 1))
            if name:
                slot["material"] = normalize_material(name)[:80]
            color = _color(colors.get(_integer(variables.get(f"color_slot{index}"), 1)))
            if color:
                slot["color_hex"] = color
        slots.append(slot)
    return slots
