"""TigerTag: the open NTAG21x filament tag (https://tigertag.io).

A chip holds a fixed binary layout in user pages 0x04-0x17, 80 bytes, all
big-endian. It stores ids, not names: which material, brand, diameter and
unit an id means comes from the reference tables the protocol publishes. A
reduced copy ships in ``app/data/tigertag_registry.json`` so a tag is read
with no network (refresh it with ``scripts/sync_tigertag_registry.py``).

Written against the specification at TigerTag-Project/TigerTag-RFID-Guide
(commit ca90a093, 2026-11-18). An id the registry does not know is left out
instead of being guessed, and the optional ECDSA signature of a TigerTag+ chip
is not verified here: decoding says what a tag claims, not who wrote it.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

FORMAT = "tigertag"

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "tigertag_registry.json"
# ``ID TigerTag`` values of chips that carry material data: TigerTag and TigerTag+.
_MAGIC = {0x5BF59264, 0xBC0FCB97}
_SYSTEM_BYTES = 16  # pages 0x00-0x03 precede the payload in a full chip dump
_PAYLOAD_BYTES = 80
_TYPE_FILAMENT, _TYPE_RESIN = 0x8E, 0xAD
_GRAMS_PER_UNIT = {"mg": 0.001, "g": 1.0, "kg": 1000.0}
# Aspects that say nothing a person would put in a filament's name.
_PLAIN_ASPECTS = {"-", "None", "Basic"}


@lru_cache(maxsize=1)
def _registry() -> dict:
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def _payload(contents: bytes) -> bytes:
    """Return the 80 payload bytes from a full chip dump or from the user pages alone."""
    for offset in (_SYSTEM_BYTES, 0):
        payload = contents[offset : offset + _PAYLOAD_BYTES]
        if len(payload) == _PAYLOAD_BYTES and int.from_bytes(payload[:4], "big") in _MAGIC:
            return payload
    raise ValueError("not a TigerTag payload")


def _midpoint(low: int, high: int, limit: int) -> int | None:
    """One recommended temperature out of a stated range; zero means not stated."""
    stated = [value for value in (low, high) if 0 < value <= limit]
    if len(stated) == 2 and low > high:
        return None
    # Half a degree rounds up, the same way for every tag format.
    return math.floor(sum(stated) / len(stated) + 0.5) if stated else None


def _color(rgba: bytes) -> str | None:
    if rgba[3] == 0:
        # Fully transparent is how an unset colour reads.
        return None
    return (rgba[:3] if rgba[3] == 0xFF else rgba).hex().upper()


def decode(contents: bytes, uid: bytes | None = None) -> dict:
    """Decode a chip's contents into the fields of ``DecodedTag``."""
    payload = _payload(contents)
    registry = _registry()
    material = registry["materials"].get(str(int.from_bytes(payload[8:10], "big")))
    kind = payload[12]
    if kind not in (_TYPE_FILAMENT, _TYPE_RESIN):
        raise ValueError("not a material tag")
    aspects = [
        label
        for label in (registry["aspects"].get(str(payload[index])) for index in (10, 11))
        if label and label not in _PLAIN_ASPECTS
    ]
    fields: dict = {
        "material_class": "FFF" if kind == _TYPE_FILAMENT else "SLA",
        "material": material["material"] if material else None,
        "name": " ".join([material["label"], *aspects]) if material else None,
        "vendor_name": registry["brands"].get(str(int.from_bytes(payload[14:16], "big"))),
        "color_hex": _color(payload[16:20]),
        "density": material.get("density") if material else None,
    }
    grams = _GRAMS_PER_UNIT.get(registry["units"].get(str(payload[23]), ""))
    measure = int.from_bytes(payload[20:23], "big")
    if grams is not None and measure > 0:
        full = round(measure * grams, 3)
        fields["weight"] = fields["initial_weight"] = full
        # "Measure Available" is what is left; a scale keeps it current. A zero
        # is also how a field nobody wrote reads, so it says nothing either way.
        available = int.from_bytes(payload[76:79], "big")
        if 0 < available <= measure:
            fields["used_weight"] = round((measure - available) * grams, 3)
    if kind == _TYPE_FILAMENT:
        fields["diameter"] = registry["diameters"].get(str(payload[13]))
        fields["extruder_temp"] = _midpoint(
            int.from_bytes(payload[24:26], "big"), int.from_bytes(payload[26:28], "big"), 600
        )
        fields["bed_temp"] = _midpoint(payload[30], payload[31], 250)
    return {key: value for key, value in fields.items() if value is not None}
