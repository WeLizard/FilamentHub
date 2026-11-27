"""Talking to a printer on the local network: its address, MQTT and WebSocket framing.

Shared by the providers that open a socket to a printer themselves. Edge has
no third-party dependencies, so the two framings it needs are kept here,
small and bounded: every read has a deadline and a size limit.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
import select
import socket
import struct
import time
from typing import Any

from ..errors import ProviderUnavailable

_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WS_TEXT = 0x1
WS_CLOSE = 0x8
WS_PING = 0x9
WS_PONG = 0xA


def resolve_local(host: str, port: int, *, device: str) -> tuple[socket.AddressFamily, Any]:
    """Resolve once and accept only an address inside the local network.

    Credentials go to whatever answers there, so they never go to an address
    on the public internet.
    """
    try:
        candidates = socket.getaddrinfo(
            host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
    except (OSError, UnicodeError) as exc:
        raise ProviderUnavailable(f"{device} address could not be resolved") from exc
    for family, _, _, _, sockaddr in candidates:
        try:
            address = ipaddress.ip_address(str(sockaddr[0]).split("%")[0])
        except ValueError:
            continue
        local = address.is_private or address.is_link_local or address.is_loopback
        if local and not (address.is_multicast or address.is_unspecified):
            return family, sockaddr
    raise ProviderUnavailable(f"{device} address must be inside the local network")


def connect_local(
    host: str, port: int, *, device: str, timeout: float
) -> tuple[socket.socket, Any]:
    """An open TCP socket to a local address, and the address it reached."""
    family, sockaddr = resolve_local(host, port, device=device)
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(sockaddr)
    except BaseException:
        sock.close()
        raise
    return sock, sockaddr


def _receive_exactly(sock: Any, length: int, deadline: float, name: str) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"{name} timed out")
        sock.settimeout(max(0.1, remaining))
        try:
            chunk = sock.recv(length - len(chunks))
        except TimeoutError:
            continue
        if not chunk:
            raise ConnectionError(f"{name} connection closed")
        chunks.extend(chunk)
    return bytes(chunks)


# MQTT 3.1.1 -----------------------------------------------------------------


def mqtt_remaining_length(length: int) -> bytes:
    encoded = bytearray()
    while True:
        digit = length & 0x7F
        length >>= 7
        if length:
            digit |= 0x80
        encoded.append(digit)
        if not length:
            return bytes(encoded)


def mqtt_field(payload: bytes) -> bytes:
    return struct.pack("!H", len(payload)) + payload


def mqtt_publish_body(topic: str, payload: bytes) -> bytes:
    """The body of a QoS 0 PUBLISH."""
    return mqtt_field(topic.encode("utf-8")) + payload


def mqtt_published(header: int, body: bytes) -> tuple[str, bytes, bytes | None] | None:
    """Topic, payload and packet id (QoS 1/2) of a PUBLISH, or None if malformed."""
    if header >> 4 != 3 or len(body) < 2:
        return None
    size = struct.unpack("!H", body[:2])[0]
    offset = 2 + size
    if len(body) < offset:
        return None
    topic = body[2:offset].decode("utf-8", "replace")
    quality = (header >> 1) & 0x03
    if quality == 0x03:
        return None
    packet_id = None
    if quality:
        packet_id = body[offset : offset + 2]
        offset += 2
    return topic, body[offset:], packet_id


class MqttLink:
    """MQTT framing over one socket, every read bounded by a deadline."""

    def __init__(self, sock: Any, *, name: str, max_packet_bytes: int) -> None:
        self.sock = sock
        self.name = name
        self.max_packet_bytes = max_packet_bytes

    def send(self, kind: int, body: bytes = b"") -> None:
        self.sock.sendall(bytes([kind]) + mqtt_remaining_length(len(body)) + body)

    def readable(self, wait: float) -> bool:
        pending = getattr(self.sock, "pending", None)
        if callable(pending) and pending():
            return True
        return bool(select.select([self.sock], [], [], wait)[0])

    def packet(self, deadline: float) -> tuple[int, bytes]:
        label = f"{self.name} MQTT"
        header = _receive_exactly(self.sock, 1, deadline, label)[0]
        length = 0
        multiplier = 1
        for _ in range(4):
            digit = _receive_exactly(self.sock, 1, deadline, label)[0]
            length += (digit & 0x7F) * multiplier
            if length > self.max_packet_bytes:
                raise ValueError(f"{label} packet exceeds the limit")
            if not digit & 0x80:
                body = _receive_exactly(self.sock, length, deadline, label) if length else b""
                return header, body
            multiplier *= 128
        raise ValueError("invalid MQTT remaining length")


# WebSocket (RFC 6455), client side -------------------------------------------


class WebSocketLink:
    """A client WebSocket over one socket: text messages in and out, nothing else."""

    def __init__(self, sock: Any, *, name: str, max_message_bytes: int) -> None:
        self.sock = sock
        self.name = name
        self.max_message_bytes = max_message_bytes

    def open(self, host: str, port: int, path: str, deadline: float) -> None:
        key = base64.b64encode(os.urandom(16))
        authority = f"[{host}]" if ":" in host else host
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {authority}:{port}\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {key.decode('ascii')}\r\n\r\n"
        ).encode("ascii")
        self.sock.sendall(request)
        head = bytearray()
        while not head.endswith(b"\r\n\r\n"):
            if len(head) > 8192:
                raise ValueError(f"{self.name} handshake is too long")
            head.extend(_receive_exactly(self.sock, 1, deadline, self.name))
        lines = bytes(head).decode("latin-1").split("\r\n")
        expected = base64.b64encode(hashlib.sha1(key + _WS_GUID).digest()).decode("ascii")
        headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        status = lines[0].split(" ", 2)
        if (
            len(status) < 2
            or status[1] != "101"
            or headers.get("upgrade", "").lower() != "websocket"
            or headers.get("sec-websocket-accept") != expected
        ):
            raise ValueError(f"{self.name} did not accept the WebSocket")

    def send(self, payload: bytes, opcode: int = WS_TEXT) -> None:
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = bytes([0x80 | opcode, 0x80 | length])
        elif length < 65536:
            header = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack("!H", length)
        else:
            header = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack("!Q", length)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def message(self, deadline: float) -> bytes | None:
        """The next whole text or binary message; None once the printer closes."""
        pending = bytearray()
        while True:
            first, second = _receive_exactly(self.sock, 2, deadline, self.name)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", _receive_exactly(self.sock, 2, deadline, self.name))[0]
            elif length == 127:
                length = struct.unpack("!Q", _receive_exactly(self.sock, 8, deadline, self.name))[0]
            if length > self.max_message_bytes or len(pending) + length > self.max_message_bytes:
                raise ValueError(f"{self.name} message exceeds the limit")
            mask = _receive_exactly(self.sock, 4, deadline, self.name) if second & 0x80 else b""
            payload = _receive_exactly(self.sock, length, deadline, self.name) if length else b""
            if mask:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == WS_CLOSE:
                return None
            if opcode == WS_PING:
                self.send(payload, WS_PONG)
                continue
            if opcode not in (0x0, 0x1, 0x2):
                continue
            pending.extend(payload)
            if first & 0x80:
                return bytes(pending)

    def close(self) -> None:
        try:
            self.send(b"", WS_CLOSE)
        except OSError:
            pass
