# Copy of orca-plugin/filamenthub_bambu.py. Do not edit: change that file and run
# edge-agent/scripts/mirror_plugin_modules.py.
# ruff: noqa
# mypy: ignore-errors
"""Bambu Lab printers for the FilamentHub OrcaSlicer plugin: reading a status report.

A Bambu printer describes its filament feed in the ``ams`` and ``vt_tray``
parts of its MQTT report: units, trays, presence bits, and a slot numbering
that differs between ordinary AMS units, single-slot AMS HT units and the
external holders. This file turns such a report into slots. Nothing here
opens a connection or sends a command.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import math
import re

BAMBU_EXTERNAL_TRAY_MAIN = 255
BAMBU_EXTERNAL_TRAY_DEPUTY = 254
# Single-slot units (AMS HT) carry their own flat number from 0x80 up instead of
# being addressed as unit*4 + slot, and tray_now reports them that way as well.
BAMBU_WIDE_UNIT_BASE = 128
BAMBU_AMS_TYPE_N3S = 4
BAMBU_AMS_TYPE_MIXED = 5


def _bambu_ams_type(unit_info):
    bits = _bambu_bits(unit_info)
    return None if bits is None else bits & 0xF


def bambu_slot_index(unit_id, slot_id, unit_info=None):
    if unit_id in (BAMBU_EXTERNAL_TRAY_MAIN, BAMBU_EXTERNAL_TRAY_DEPUTY):
        return unit_id
    ams_type = _bambu_ams_type(unit_info)
    if unit_id >= BAMBU_WIDE_UNIT_BASE or ams_type == BAMBU_AMS_TYPE_N3S:
        return unit_id
    if ams_type == BAMBU_AMS_TYPE_MIXED:
        return 24 + slot_id
    return unit_id * 4 + slot_id


def _bambu_presence_bit_index(unit_id, slot_id, unit_info=None):
    ams_type = _bambu_ams_type(unit_info)
    if unit_id >= BAMBU_WIDE_UNIT_BASE or ams_type == BAMBU_AMS_TYPE_N3S:
        return 16 + max(unit_id - BAMBU_WIDE_UNIT_BASE, 0) + slot_id
    if ams_type == BAMBU_AMS_TYPE_MIXED:
        return 24 + slot_id
    return unit_id * 4 + slot_id


def _bambu_int(value, default=None):
    """Bambu sends numbers as strings about as often as it sends them as numbers."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value) if math.isfinite(value) else default
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except (ValueError, OverflowError):
            return default
    return default


def _bambu_bits(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return int(value.strip(), 16)
    except ValueError:
        return None


def _bambu_color(value):
    """tray_color is RRGGBBAA; an unset slot reports it fully transparent."""
    text = (value or "").strip().lstrip("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}([0-9A-F]{2})?", text):
        return None
    if len(text) == 8 and text[6:] == "00":
        return None
    return text[:6]


def _bambu_amount(value):
    """-1 means the printer cannot measure this spool, which is not the same as 0."""
    amount = _bambu_int(value)
    return None if amount is None or amount < 0 else amount


def _bambu_slot(tray, index, present):
    uid = (tray.get("tray_uuid") or tray.get("tag_uid") or "").strip()
    return {
        "index": index,
        "present": present,
        "material": (tray.get("tray_type") or "").strip() or None,
        "color_hex": _bambu_color(tray.get("tray_color")),
        "remaining_pct": _bambu_amount(tray.get("remain")),
        "remaining_g": _bambu_amount(tray.get("remain_g")),
        "reported_capacity_g": _bambu_amount(tray.get("tray_weight")),
        "filament_id": str(tray.get("tray_info_idx") or "").strip() or None,
        "setting_id": str(tray.get("setting_id") or "").strip() or None,
        "nozzle_temp_min": _bambu_int(tray.get("nozzle_temp_min")),
        "nozzle_temp_max": _bambu_int(tray.get("nozzle_temp_max")),
        # A zeroed uuid is how an empty or non-Bambu tray reports "no tag".
        "provider_uid": uid if uid.strip("0") else None,
    }


def _bambu_tag_read_capable(report):
    if not isinstance(report, dict):
        return False
    feed = report.get("ams")
    units = feed.get("ams") if isinstance(feed, dict) else None
    trays = []
    for unit in units or []:
        if isinstance(unit, dict):
            trays.extend(item for item in (unit.get("tray") or []) if isinstance(item, dict))
    holders = report.get("vir_slot")
    if isinstance(holders, list):
        trays.extend(item for item in holders if isinstance(item, dict))
    else:
        holder = report.get("vt_tray")
        if isinstance(holder, dict):
            trays.append(holder)
    return any("tray_uuid" in tray or "tag_uid" in tray for tray in trays)


def _bambu_capabilities(report):
    capabilities = ["read", "write", "presence", "consumption"]
    if _bambu_tag_read_capable(report):
        capabilities.append("tag_read")
    return capabilities


def _bambu_slot_locator(report, provider_index):
    feed = report.get("ams") if isinstance(report, dict) else None
    units = feed.get("ams") if isinstance(feed, dict) else None
    for unit in units or []:
        if not isinstance(unit, dict):
            continue
        unit_id = _bambu_int(unit.get("id"))
        if unit_id is None:
            continue
        for tray in unit.get("tray") or []:
            if not isinstance(tray, dict):
                continue
            slot_id = _bambu_int(tray.get("id"))
            if slot_id is None:
                continue
            if bambu_slot_index(unit_id, slot_id, unit.get("info")) == provider_index:
                return {"ams_id": unit_id, "slot_id": slot_id, "tray": tray}

    holders = report.get("vir_slot") if isinstance(report, dict) else None
    if not isinstance(holders, list):
        holder = report.get("vt_tray") if isinstance(report, dict) else None
        holders = [holder] if isinstance(holder, dict) else []
    for holder in holders:
        if not isinstance(holder, dict):
            continue
        ams_id = _bambu_int(holder.get("id"), BAMBU_EXTERNAL_TRAY_MAIN)
        if ams_id == provider_index:
            return {"ams_id": ams_id, "slot_id": 0, "tray": holder}
    return None


def _bambu_external_slots(report):
    slots = []
    holders = report.get("vir_slot")
    if not isinstance(holders, list):
        holder = report.get("vt_tray")
        holders = [holder] if isinstance(holder, dict) else []
    for holder in holders:
        if not isinstance(holder, dict):
            continue
        index = _bambu_int(holder.get("id"), BAMBU_EXTERNAL_TRAY_MAIN)
        slot = _bambu_slot(holder, index, bool((holder.get("tray_type") or "").strip()))
        slots.append(slot)
    return slots


def parse_bambu_feed(report):
    """Flatten one Bambu status report into the slots FilamentHub talks about.

    Returns None when the report says nothing about the feed: Bambu also pushes
    partial updates, and a partial one must not erase a full one.
    """
    if not isinstance(report, dict):
        return None
    feed = report.get("ams")
    units = feed.get("ams") if isinstance(feed, dict) else None
    external = _bambu_external_slots(report)
    if not isinstance(units, list) and not external:
        return None

    exist_bits = _bambu_bits(feed.get("tray_exist_bits")) if isinstance(feed, dict) else None
    slots = []
    for unit in units or []:
        if not isinstance(unit, dict):
            continue
        unit_id = _bambu_int(unit.get("id"))
        if unit_id is None:
            continue
        for tray in unit.get("tray") or []:
            if not isinstance(tray, dict):
                continue
            slot_id = _bambu_int(tray.get("id"))
            if slot_id is None:
                continue
            unit_info = unit.get("info")
            index = bambu_slot_index(unit_id, slot_id, unit_info)
            if exist_bits is None:
                present = bool((tray.get("tray_type") or "").strip())
            else:
                presence_index = _bambu_presence_bit_index(unit_id, slot_id, unit_info)
                present = bool(exist_bits & (1 << presence_index))
            slots.append(_bambu_slot(tray, index, present))

    slots.extend(external)
    slots.sort(key=lambda slot: slot["index"])
    active = _bambu_int(feed.get("tray_now")) if isinstance(feed, dict) else None
    return {"slots": slots, "active_index": active}
