"""What a filament tag says about itself, decoded on the server.

A reader reports a tag's UID and, when it can, the tag's raw contents. The UID
alone resolves a tag that is already linked to a spool. The contents let an
unknown tag describe its filament, so nobody has to type what is already on
the roll.

Decoding is pure and best effort: no database, no network, and an unknown
format or contents that do not parse give ``None`` instead of an error.
Resolving a UID must never fail because enriching it did not work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from . import openprinttag, openspool, tigertag


@dataclass(frozen=True)
class DecodedTag:
    """Filament facts read from a tag, in the shape Spoolman's scan answer uses."""

    material_class: str | None = None
    material: str | None = None
    name: str | None = None
    vendor_name: str | None = None
    article_number: str | None = None
    color_hex: str | None = None
    diameter: float | None = None
    density: float | None = None
    # Net filament weight of a full roll as sold, and of this particular roll.
    weight: float | None = None
    initial_weight: float | None = None
    spool_weight: float | None = None
    used_weight: float | None = None
    extruder_temp: int | None = None
    bed_temp: int | None = None
    instance_uuid: str | None = None

    def as_response(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value is not None}


_DECODERS = {
    openprinttag.FORMAT: openprinttag.decode,
    openspool.FORMAT: openspool.decode,
    tigertag.FORMAT: tigertag.decode,
}

# Formats each chip family carries, tried in this order when a reader reports
# the chip but not the format: NTAG21x (Type 2) and NFC-V (Type 5).
_FORMATS_BY_CHIP = {
    "ntag213": (tigertag.FORMAT, openspool.FORMAT),
    "ntag215": (tigertag.FORMAT, openspool.FORMAT),
    "ntag216": (tigertag.FORMAT, openspool.FORMAT),
    "iso15693": (openprinttag.FORMAT,),
}


def decode_tag(tag_format: str | None, contents: bytes, uid: bytes | None = None) -> DecodedTag | None:
    """Decode a tag's contents when its format is one this server reads."""
    decoder = _DECODERS.get((tag_format or "").strip().lower())
    if decoder is None:
        return None
    try:
        fields = decoder(contents, uid)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        return None
    return DecodedTag(**fields) if fields else None


def identify_tag(chip: str | None, contents: bytes, uid: bytes | None = None) -> tuple[str, DecodedTag] | None:
    """Find which format a tag's contents are in and decode them.

    ``chip`` is what the reader saw (``ntag215``, ``iso15693``); an unknown
    chip tries every format this server reads.
    """
    formats = _FORMATS_BY_CHIP.get((chip or "").strip().lower(), tuple(_DECODERS))
    for tag_format in formats:
        decoded = decode_tag(tag_format, contents, uid)
        if decoded is not None:
            return tag_format, decoded
    return None
