"""NFC Forum framing shared by the tag formats: TLV blocks and NDEF records.

A tag's memory holds TLV blocks after its capability container; the NDEF TLV
carries a message of records. Truncated or malformed framing raises
``ValueError`` or ``IndexError``, which decoding treats as "not this format".
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

TLV_NULL, TLV_NDEF, TLV_TERMINATOR = 0x00, 0x03, 0xFE
TNF_MEDIA_TYPE = 0x02


def tlv_message(memory: bytes, position: int) -> bytes:
    """Return the NDEF message of the TLV blocks that start at ``position``."""
    while position < len(memory):
        kind = memory[position]
        position += 1
        if kind == TLV_NULL:
            continue
        if kind == TLV_TERMINATOR:
            break
        length = memory[position]
        position += 1
        if length == 0xFF:
            length = int.from_bytes(memory[position : position + 2], "big")
            position += 2
        if kind == TLV_NDEF:
            return memory[position : position + length]
        position += length
    raise ValueError("no NDEF message")


@dataclass(frozen=True)
class Record:
    tnf: int
    type: bytes
    payload: bytes
    chunked: bool
    # What the header promises; a shorter payload means the memory was cut off.
    declared_length: int

    @property
    def complete(self) -> bool:
        return len(self.payload) == self.declared_length


def records(message: bytes) -> Iterator[Record]:
    """Yield the records of an NDEF message in order."""
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
        yield Record(header & 0x07, record_type, payload, bool(header & 0x20), payload_length)
        if header & 0x40:  # last record of the message
            break
