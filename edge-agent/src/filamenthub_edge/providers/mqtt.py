"""MQTT 3.1.1 framing over one socket, shared by the printers that speak it.

Only what a reading client needs: encode a packet, read one back within a
deadline. Connecting, subscribing and what the messages mean stay with each
printer's provider.
"""

from __future__ import annotations

import select
import struct
import time
from typing import Any

MAX_PACKET_BYTES = 2 * 1024 * 1024


def remaining_length(length: int) -> bytes:
    encoded = bytearray()
    while True:
        digit = length & 0x7F
        length >>= 7
        if length:
            digit |= 0x80
        encoded.append(digit)
        if not length:
            return bytes(encoded)


def field(payload: bytes) -> bytes:
    """A length-prefixed MQTT string or binary field."""
    return struct.pack("!H", len(payload)) + payload


def published(header: int, body: bytes) -> tuple[bytes, bytes] | None:
    """The topic and payload of a PUBLISH packet, or None for a malformed one."""
    if len(body) < 2:
        return None
    topic_length = struct.unpack("!H", body[:2])[0]
    offset = 2 + topic_length
    quality = (header >> 1) & 0x03
    if quality == 0x03:
        return None
    if quality:
        offset += 2
    if len(body) < offset:
        return None
    return body[2 : 2 + topic_length], body[offset:]


class MqttLink:
    """MQTT framing over one socket, every read bounded by a deadline."""

    def __init__(self, sock: Any, *, label: str = "MQTT", max_packet: int = MAX_PACKET_BYTES):
        self.sock = sock
        self.label = label
        self.max_packet = max_packet

    def send(self, kind: int, body: bytes = b"") -> None:
        self.sock.sendall(bytes([kind]) + remaining_length(len(body)) + body)

    def readable(self, wait: float) -> bool:
        pending = getattr(self.sock, "pending", None)
        if callable(pending) and pending():
            return True
        return bool(select.select([self.sock], [], [], wait)[0])

    def _receive(self, length: int, deadline: float) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{self.label} timed out")
            self.sock.settimeout(max(0.1, remaining))
            try:
                chunk = self.sock.recv(length - len(chunks))
            except TimeoutError:
                continue
            if not chunk:
                raise ConnectionError(f"{self.label} connection closed")
            chunks.extend(chunk)
        return bytes(chunks)

    def packet(self, deadline: float) -> tuple[int, bytes]:
        header = self._receive(1, deadline)[0]
        length = 0
        multiplier = 1
        for _ in range(4):
            digit = self._receive(1, deadline)[0]
            length += (digit & 0x7F) * multiplier
            if length > self.max_packet:
                raise ValueError(f"{self.label} packet exceeds the limit")
            if not digit & 0x80:
                return header, self._receive(length, deadline) if length else b""
            multiplier *= 128
        raise ValueError("invalid MQTT remaining length")
