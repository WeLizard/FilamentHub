"""OpenSpool: a filament tag as one JSON record on an NTAG21x (https://openspool.io).

The tag's NDEF message holds a record of MIME type ``application/json`` with
an object whose ``protocol`` is ``openspool``: ``type`` names the material,
``color_hex`` the colour, ``brand`` the maker and ``min_temp``/``max_temp``
the nozzle range. Readers and writers in the wild send the numbers as strings
or as numbers, and the colour with or without ``#``; both are accepted.
Optional ``subtype`` and bed temperatures are read when present. A field that
does not make sense is left out on its own.
"""

from __future__ import annotations

import json
import math
import re

from .ndef import TNF_MEDIA_TYPE, records, tlv_message

FORMAT = "openspool"
MIME_TYPE = b"application/json"

# In a full chip dump pages 0x00-0x03 (UID, lock bytes and the capability
# container, whose first byte is 0xE1) precede the TLV blocks.
_TYPE2_DUMP_TLV_START = 16
_TYPE2_CC_AT = 12
_COLOR = re.compile(r"^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")


def _message(contents: bytes) -> bytes:
    if len(contents) > _TYPE2_DUMP_TLV_START and contents[_TYPE2_CC_AT] == 0xE1:
        return tlv_message(contents, _TYPE2_DUMP_TLV_START)
    # User pages alone start with the TLV blocks; a bare NDEF message has no TLV.
    try:
        return tlv_message(contents, 0)
    except (ValueError, IndexError):
        return contents


def _document(contents: bytes) -> dict:
    for record in records(_message(contents)):
        if record.tnf == TNF_MEDIA_TYPE and record.type == MIME_TYPE and record.complete:
            document = json.loads(record.payload.decode("utf-8"))
            if (
                isinstance(document, dict)
                and str(document.get("protocol", "")).lower() == "openspool"
            ):
                return document
    raise ValueError("no OpenSpool record")


def _text(value: object, limit: int = 60) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:limit] or None


def _number(value: object, low: float, high: float) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        return None
    return float(value)


def _midpoint(low: float | None, high: float | None) -> int | None:
    """One recommended temperature out of the range a tag states."""
    if low is not None and high is not None:
        # Half a degree rounds up, the same way for every tag format.
        return math.floor((low + high) / 2 + 0.5) if low <= high else None
    chosen = low if low is not None else high
    return None if chosen is None else math.floor(chosen + 0.5)


def decode(contents: bytes, uid: bytes | None = None) -> dict:
    """Decode a chip's contents into the fields of ``DecodedTag``."""
    document = _document(contents)
    material = _text(document.get("type"), 20)
    material = material.upper() if material else None
    subtype = _text(document.get("subtype"))
    brand = _text(document.get("brand"))
    color = _COLOR.match(str(document.get("color_hex", "")).strip())
    fields = {
        "material_class": "FFF",
        "material": material,
        "name": " ".join(part for part in (material, subtype) if part) or None,
        "vendor_name": brand if brand and brand.lower() != "generic" else None,
        # Fully opaque colours drop their alpha byte, the same way TigerTag reads.
        "color_hex": (
            color.group(1)[:6].upper()
            if color and (len(color.group(1)) == 6 or color.group(1)[6:].upper() == "FF")
            else color.group(1).upper()
            if color
            else None
        ),
        "extruder_temp": _midpoint(
            _number(document.get("min_temp"), 100, 500), _number(document.get("max_temp"), 100, 500)
        ),
        "bed_temp": _midpoint(
            _number(document.get("bed_min_temp"), 0, 150),
            _number(document.get("bed_max_temp"), 0, 150),
        ),
    }
    return {key: value for key, value in fields.items() if value is not None}
