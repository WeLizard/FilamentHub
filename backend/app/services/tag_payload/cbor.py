"""A small, strict CBOR reader for data read off filament tags (RFC 8949).

Tag contents arrive from readers nobody vouches for, so this reader is built to
refuse rather than to cope: semantic tags, indefinite-length strings, nesting
beyond a few levels and containers larger than a tag could hold are all
errors. It builds plain Python values only and never calls into a general
CBOR library, so nothing here can be steered into resolving shared references
or other features a filament tag has no use for.
"""

from __future__ import annotations

import struct

MAX_DEPTH = 8
MAX_ITEMS = 512
MAX_STRING_BYTES = 1024

_UNSIGNED, _NEGATIVE, _BYTES, _TEXT, _ARRAY, _MAP, _TAG, _SIMPLE = range(8)
_INDEFINITE = 31
_BREAK = 0xFF


class CborError(ValueError):
    """The bytes are not CBOR this reader accepts."""


def read_item(data: bytes, offset: int = 0) -> tuple[object, int]:
    """Decode the one item that starts at ``offset``; return it and where it ends."""
    return _Reader(data).item(offset, 0)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.items = 0

    def _take(self, offset: int, length: int) -> bytes:
        if length < 0 or offset + length > len(self.data):
            raise CborError("truncated")
        return self.data[offset : offset + length]

    def _argument(self, info: int, offset: int) -> tuple[int, int]:
        if info < 24:
            return info, offset
        if info > 27:
            raise CborError("reserved length")
        size = 1 << (info - 24)
        return int.from_bytes(self._take(offset, size), "big"), offset + size

    def item(self, offset: int, depth: int) -> tuple[object, int]:
        if depth > MAX_DEPTH:
            raise CborError("nested too deep")
        self.items += 1
        if self.items > MAX_ITEMS:
            raise CborError("too many items")
        head = self._take(offset, 1)[0]
        major, info = head >> 5, head & 0x1F
        offset += 1
        if major == _TAG:
            raise CborError("semantic tags are not accepted")
        if major == _SIMPLE:
            return self._simple(info, offset)
        if info == _INDEFINITE:
            if major == _ARRAY:
                return self._array(None, offset, depth)
            if major == _MAP:
                return self._map(None, offset, depth)
            raise CborError("indefinite length is accepted for containers only")
        value, offset = self._argument(info, offset)
        if major == _UNSIGNED:
            return value, offset
        if major == _NEGATIVE:
            return -1 - value, offset
        if major in (_BYTES, _TEXT):
            if value > MAX_STRING_BYTES:
                raise CborError("string too long")
            raw = self._take(offset, value)
            if major == _BYTES:
                return raw, offset + value
            try:
                return raw.decode("utf-8"), offset + value
            except UnicodeDecodeError as exc:
                raise CborError("text is not UTF-8") from exc
        if major == _ARRAY:
            return self._array(value, offset, depth)
        return self._map(value, offset, depth)

    def _simple(self, info: int, offset: int) -> tuple[object, int]:
        if info == 20:
            return False, offset
        if info == 21:
            return True, offset
        if info in (22, 23):
            return None, offset
        formats = {25: ">e", 26: ">f", 27: ">d"}
        if info not in formats:
            raise CborError("unsupported simple value")
        size = struct.calcsize(formats[info])
        return struct.unpack(formats[info], self._take(offset, size))[0], offset + size

    def _ended(self, count: int | None, seen: int, offset: int) -> tuple[bool, int]:
        if count is not None:
            return seen >= count, offset
        if self._take(offset, 1)[0] == _BREAK:
            return True, offset + 1
        return False, offset

    def _array(self, count: int | None, offset: int, depth: int) -> tuple[list, int]:
        if count is not None and count > MAX_ITEMS:
            raise CborError("array too long")
        values: list = []
        while True:
            done, offset = self._ended(count, len(values), offset)
            if done:
                return values, offset
            value, offset = self.item(offset, depth + 1)
            values.append(value)

    def _map(self, count: int | None, offset: int, depth: int) -> tuple[dict, int]:
        if count is not None and count > MAX_ITEMS:
            raise CborError("map too long")
        values: dict = {}
        seen = 0
        while True:
            done, offset = self._ended(count, seen, offset)
            if done:
                return values, offset
            key, offset = self.item(offset, depth + 1)
            if isinstance(key, bool) or not isinstance(key, (int, str)):
                raise CborError("map key must be an integer or text")
            value, offset = self.item(offset, depth + 1)
            # A repeated key keeps its first value, so later bytes cannot override earlier ones.
            values.setdefault(key, value)
            seen += 1
