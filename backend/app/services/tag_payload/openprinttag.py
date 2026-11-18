"""OpenPrintTag: the open NFC-V filament tag (https://openprinttag.org).

A tag's memory is a Type 5 capability container followed by TLV blocks. One
of them holds an NDEF message, and one record in it, of MIME type
``application/vnd.openprinttag``, carries three CBOR maps keyed by integers:

- *meta* at the start of the record says where the other two begin;
- *main* describes the material and does not change over the roll's life;
- *aux* holds what a printer updates, such as the weight already consumed.

Written against the specification at prusa3d/OpenPrintTag (commit 060e4208,
2026-10-09). Unknown keys are skipped, as the specification requires, and a
value outside a physically sensible range is left out on its own instead of
discarding the whole tag.
"""

from __future__ import annotations

import hashlib
import math
import uuid

from .cbor import read_item

FORMAT = "openprinttag"
MIME_TYPE = b"application/vnd.openprinttag"

_CC_MAGIC = {0xE1, 0xE2}
_TLV_NULL, _TLV_NDEF, _TLV_TERMINATOR = 0x00, 0x03, 0xFE
_NDEF_MEDIA_TYPE = 0x02

_META_MAIN_OFFSET, _META_AUX_OFFSET = 0, 2
_INSTANCE_UUID, _GTIN, _MATERIAL_CLASS, _MATERIAL_TYPE = 0, 4, 8, 9
_MATERIAL_NAME, _BRAND_NAME = 10, 11
_NOMINAL_WEIGHT, _ACTUAL_WEIGHT, _CONTAINER_WEIGHT, _PRIMARY_COLOR = 16, 17, 18, 19
_DENSITY, _DIAMETER = 29, 30
_MIN_PRINT, _MAX_PRINT, _MIN_BED, _MAX_BED = 34, 35, 37, 38
_ABBREVIATION = 52
_AUX_CONSUMED_WEIGHT = 0

_INSTANCE_NAMESPACE = uuid.UUID("31062f81-b5bd-4f86-a5f8-46367e841508")
_DEFAULT_DIAMETER = 1.75  # "If not present, 1.75 mm is assumed."

_MATERIAL_CLASSES = {0: "FFF", 1: "SLA"}
_MATERIAL_TYPES = {
    0: "PLA", 1: "PETG", 2: "TPU", 3: "ABS", 4: "ASA", 5: "PC", 6: "PCTG", 7: "PP", 8: "PA6",
    9: "PA11", 10: "PA12", 11: "PA66", 12: "CPE", 13: "TPE", 14: "HIPS", 15: "PHA", 16: "PET",
    17: "PEI", 18: "PBT", 19: "PVB", 20: "PVA", 21: "PEKK", 22: "PEEK", 23: "BVOH", 24: "TPC",
    25: "PPS", 26: "PPSU", 27: "PVC", 28: "PEBA", 29: "PVDF", 30: "PPA", 31: "PCL", 32: "PES",
    33: "PMMA", 34: "POM", 35: "PPE", 36: "PS", 37: "PSU", 38: "TPI", 39: "SBS", 40: "OBC",
    41: "EVA", 42: "PA612",
}


def _ndef_message(memory: bytes) -> bytes:
    """Return the NDEF message held in a Type 5 tag's memory."""
    if not memory or memory[0] not in _CC_MAGIC:
        # Some readers hand over the NDEF message itself, without the tag's framing.
        return memory
    # The capability container is 4 bytes, or 8 when its size byte is zero.
    position = 8 if len(memory) > 2 and memory[2] == 0 else 4
    while position < len(memory):
        kind = memory[position]
        position += 1
        if kind == _TLV_NULL:
            continue
        if kind == _TLV_TERMINATOR:
            break
        length = memory[position]
        position += 1
        if length == 0xFF:
            length = int.from_bytes(memory[position : position + 2], "big")
            position += 2
        if kind == _TLV_NDEF:
            return memory[position : position + length]
        position += length
    raise ValueError("no NDEF message")


def _record_payload(message: bytes) -> bytes:
    """Return the payload of the OpenPrintTag record of an NDEF message."""
    position = 0
    while position < len(message):
        header = message[position]
        type_length = message[position + 1]
        position += 2
        if header & 0x10:  # short record: one length byte
            payload_length = message[position]
            position += 1
        else:
            payload_length = int.from_bytes(message[position : position + 4], "big")
            position += 4
        id_length = 0
        if header & 0x08:
            id_length = message[position]
            position += 1
        record_type = message[position : position + type_length]
        position += type_length + id_length
        payload = message[position : position + payload_length]
        position += payload_length
        # The specification forbids splitting this record into chunks (0x20).
        if header & 0x07 == _NDEF_MEDIA_TYPE and record_type == MIME_TYPE and not header & 0x20:
            if len(payload) != payload_length:
                raise ValueError("truncated record")
            return payload
        if header & 0x40:  # last record of the message
            break
    raise ValueError("no OpenPrintTag record")


def _section(payload: bytes, offset: int) -> tuple[dict, int]:
    value, end = read_item(payload, offset)
    if not isinstance(value, dict):
        raise ValueError("section is not a map")
    return value, end


def _number(value: object, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        return None
    # Tags store fractions as half-floats: 1.24 arrives as 1.240234375.
    return round(number, 3)


def _text(value: object, limit: int = 120) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:limit] or None


def _midpoint(low: float | None, high: float | None) -> int | None:
    """One recommended temperature out of the range a tag states."""
    if low is not None and high is not None:
        return round((low + high) / 2) if low <= high else None
    chosen = low if low is not None else high
    return round(chosen) if chosen is not None else None


def _color(value: object) -> str | None:
    if not isinstance(value, bytes) or len(value) not in (3, 4):
        return None
    # A fully opaque colour is written without its alpha channel.
    return (value[:3] if value[3:] in (b"", b"\xff") else value).hex().upper()


def _instance_uuid(main: dict, uid: bytes | None) -> str | None:
    stated = main.get(_INSTANCE_UUID)
    if isinstance(stated, bytes) and len(stated) == 16:
        return str(uuid.UUID(bytes=stated))
    if uid is None or len(uid) != 8:
        return None
    # Readers report NFC-V UIDs in either byte order; the derivation wants 0xE0 first.
    ordered = uid if uid[0] == 0xE0 else uid[::-1]
    if ordered[0] != 0xE0:
        return None
    # UUIDv5 over raw bytes, spelled out: uuid.uuid5 accepts bytes only from Python 3.12.
    digest = hashlib.sha1(_INSTANCE_NAMESPACE.bytes + ordered, usedforsecurity=False).digest()
    return str(uuid.UUID(bytes=digest[:16], version=5))


def decode(memory: bytes, uid: bytes | None = None) -> dict:
    """Decode a tag's memory into the fields of ``DecodedTag``."""
    payload = _record_payload(_ndef_message(memory))
    meta, meta_end = _section(payload, 0)
    main_offset = meta.get(_META_MAIN_OFFSET, meta_end)
    if isinstance(main_offset, bool) or not isinstance(main_offset, int):
        raise ValueError("bad main region offset")
    main, _end = _section(payload, main_offset)
    aux: dict = {}
    aux_offset = meta.get(_META_AUX_OFFSET)
    if isinstance(aux_offset, int) and not isinstance(aux_offset, bool):
        try:
            aux, _end = _section(payload, aux_offset)
        except ValueError:
            # A printer writes this region in the field; damage there must not hide the material.
            aux = {}

    material_class = _MATERIAL_CLASSES.get(main.get(_MATERIAL_CLASS))
    gtin = main.get(_GTIN)
    nominal = _number(main.get(_NOMINAL_WEIGHT), 0.001, 100_000)
    actual = _number(main.get(_ACTUAL_WEIGHT), 0.001, 100_000)
    fields = {
        "material_class": material_class,
        "material": _MATERIAL_TYPES.get(main.get(_MATERIAL_TYPE)) or _text(main.get(_ABBREVIATION), 16),
        "name": _text(main.get(_MATERIAL_NAME)),
        "vendor_name": _text(main.get(_BRAND_NAME)),
        "article_number": (
            str(gtin) if isinstance(gtin, int) and not isinstance(gtin, bool) and 0 < gtin < 10**14
            else None
        ),
        "color_hex": _color(main.get(_PRIMARY_COLOR)),
        "density": _number(main.get(_DENSITY), 0.01, 30),
        "weight": nominal,
        # "If not present, nominal_netto_full_weight SHALL be used as a fallback."
        "initial_weight": actual if actual is not None else nominal,
        "spool_weight": _number(main.get(_CONTAINER_WEIGHT), 0, 100_000),
        "used_weight": _number(aux.get(_AUX_CONSUMED_WEIGHT), 0, 100_000),
        "instance_uuid": _instance_uuid(main, uid),
    }
    if material_class == "FFF":
        fields["diameter"] = _number(main.get(_DIAMETER), 0.1, 10) or _DEFAULT_DIAMETER
        fields["extruder_temp"] = _midpoint(
            _number(main.get(_MIN_PRINT), 0, 600), _number(main.get(_MAX_PRINT), 0, 600)
        )
        fields["bed_temp"] = _midpoint(
            _number(main.get(_MIN_BED), 0, 250), _number(main.get(_MAX_BED), 0, 250)
        )
    return {key: value for key, value in fields.items() if value is not None}
