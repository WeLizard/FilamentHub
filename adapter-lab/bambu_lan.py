"""Small stateful Bambu LAN TLS/MQTT surface for local adapter checks."""

from __future__ import annotations

import copy
import json
import os
import socketserver
import ssl
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ACCESS_CODE = os.environ.get("BAMBU_ACCESS_CODE", "adapterlab")
SERIAL = os.environ.get("BAMBU_SERIAL", "FH-BAMBU-LAB")
CERT_FILE = "/run/adapter-lab/bambu.crt"
KEY_FILE = "/run/adapter-lab/bambu.key"
MAX_PACKET_BYTES = 1024 * 1024

_state_lock = threading.Lock()
_report = {
    "gcode_state": "IDLE",
    "mc_percent": 0,
    "mc_remaining_time": 0,
    "nozzle_temper": 24.0,
    "nozzle_target_temper": 0.0,
    "bed_temper": 24.0,
    "bed_target_temper": 0.0,
    "ams": {
        "tray_now": "1",
        "tray_exist_bits": "7",
        "ams": [
            {
                "id": "0",
                "tray": [
                    {
                        "id": "0",
                        "tray_type": "PLA",
                        "tray_color": "FF6A13FF",
                        "tray_info_idx": "GFA00",
                        "setting_id": "GFSA00_01",
                        "nozzle_temp_min": 190,
                        "nozzle_temp_max": 230,
                        "remain": 81,
                        "remain_g": 812,
                        "tray_uuid": "D1E2F3",
                    },
                    {
                        "id": "1",
                        "tray_type": "PETG",
                        "tray_color": "1F8A70FF",
                        "tray_info_idx": "GFG01",
                        "setting_id": "GFSG01_01",
                        "nozzle_temp_min": 220,
                        "nozzle_temp_max": 260,
                        "remain": -1,
                        "remain_g": -1,
                        "tray_uuid": "00000000",
                    },
                    {
                        "id": "2",
                        "tray_type": "ABS",
                        "tray_color": "3366CCFF",
                        "tray_info_idx": "GFB00",
                        "setting_id": "GFSB00_01",
                        "nozzle_temp_min": 240,
                        "nozzle_temp_max": 280,
                        "remain": -1,
                        "remain_g": -1,
                        "tray_uuid": "00000000",
                    },
                    {
                        "id": "3",
                        "tray_type": "",
                        "tray_color": "00000000",
                        "remain": -1,
                        "remain_g": -1,
                        "tray_uuid": "00000000",
                    },
                ],
            }
        ],
    },
    "vir_slot": [
        {
            "id": 255,
            "tray_type": "PLA",
            "tray_color": "E8E8E8FF",
            "tray_info_idx": "GFA00",
            "setting_id": "GFSA00_01",
            "nozzle_temp_min": 190,
            "nozzle_temp_max": 230,
            "remain": -1,
            "remain_g": -1,
            "tray_uuid": "00000000",
        }
    ],
}


def snapshot() -> dict:
    with _state_lock:
        return copy.deepcopy(_report)


def apply_request(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    command = payload.get("print")
    if (
        not isinstance(command, dict)
        or command.get("command") != "ams_filament_setting"
    ):
        return False
    try:
        ams_id = int(command.get("ams_id"))
        slot_id = int(command.get("slot_id"))
    except (TypeError, ValueError):
        return False
    with _state_lock:
        tray = _find_tray(_report, ams_id, slot_id)
        if tray is None:
            return False
        for source, target in (
            ("tray_info_idx", "tray_info_idx"),
            ("setting_id", "setting_id"),
            ("tray_color", "tray_color"),
            ("nozzle_temp_min", "nozzle_temp_min"),
            ("nozzle_temp_max", "nozzle_temp_max"),
            ("tray_type", "tray_type"),
        ):
            if source in command:
                tray[target] = command[source]
    return True


def _find_tray(report: dict, ams_id: int, slot_id: int) -> dict | None:
    if ams_id in {254, 255}:
        for tray in report.get("vir_slot", []):
            if int(tray.get("id", 255)) == ams_id:
                return tray
        return None
    for unit in report.get("ams", {}).get("ams", []):
        if int(unit.get("id", -1)) != ams_id:
            continue
        for tray in unit.get("tray", []):
            if int(tray.get("id", -1)) == slot_id:
                return tray
    return None


def _read_exact(stream, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            raise ConnectionError("connection closed")
        data.extend(chunk)
    return bytes(data)


def _read_packet(stream) -> tuple[int, bytes]:
    header = _read_exact(stream, 1)[0]
    length = 0
    multiplier = 1
    for _ in range(4):
        digit = _read_exact(stream, 1)[0]
        length += (digit & 0x7F) * multiplier
        if length > MAX_PACKET_BYTES:
            raise ValueError("MQTT packet too large")
        if not digit & 0x80:
            return header, _read_exact(stream, length) if length else b""
        multiplier *= 128
    raise ValueError("invalid MQTT length")


def _encode_length(length: int) -> bytes:
    encoded = bytearray()
    while True:
        digit = length & 0x7F
        length >>= 7
        if length:
            digit |= 0x80
        encoded.append(digit)
        if not length:
            return bytes(encoded)


def _field(payload: bytes) -> bytes:
    return struct.pack("!H", len(payload)) + payload


def _take_field(body: bytes, offset: int) -> tuple[bytes, int]:
    if len(body) < offset + 2:
        raise ValueError("truncated MQTT field")
    length = struct.unpack("!H", body[offset : offset + 2])[0]
    start = offset + 2
    end = start + length
    if len(body) < end:
        raise ValueError("truncated MQTT field")
    return body[start:end], end


def _authenticate(body: bytes) -> bool:
    protocol, offset = _take_field(body, 0)
    if protocol != b"MQTT" or len(body) < offset + 4 or body[offset] != 4:
        return False
    flags = body[offset + 1]
    offset += 4
    _client_id, offset = _take_field(body, offset)
    if not flags & 0x80 or not flags & 0x40:
        return False
    username, offset = _take_field(body, offset)
    password, _offset = _take_field(body, offset)
    return username == b"bblp" and password.decode("utf-8", "replace") == ACCESS_CODE


def _publish_report(stream) -> None:
    topic = f"device/{SERIAL}/report".encode("utf-8")
    payload = json.dumps({"print": snapshot()}, separators=(",", ":")).encode("utf-8")
    body = _field(topic) + payload
    stream.write(b"\x30" + _encode_length(len(body)) + body)
    stream.flush()


class BambuMqttHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            header, body = _read_packet(self.rfile)
            if (header & 0xF0) != 0x10 or not _authenticate(body):
                self.wfile.write(b"\x20\x02\x00\x05")
                self.wfile.flush()
                return
            self.wfile.write(b"\x20\x02\x00\x00")
            self.wfile.flush()
            while True:
                header, body = _read_packet(self.rfile)
                packet_type = header & 0xF0
                if packet_type == 0x80:
                    if len(body) < 2:
                        return
                    packet_id = body[:2]
                    self.wfile.write(b"\x90\x03" + packet_id + b"\x00")
                    self.wfile.flush()
                    _publish_report(self.wfile)
                elif packet_type == 0x30:
                    topic, offset = _take_field(body, 0)
                    if (header >> 1) & 0x03:
                        offset += 2
                    if topic != f"device/{SERIAL}/request".encode("utf-8"):
                        continue
                    try:
                        payload = json.loads(body[offset:].decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    pushing = (
                        payload.get("pushing") if isinstance(payload, dict) else None
                    )
                    if (
                        isinstance(pushing, dict)
                        and pushing.get("command") == "pushall"
                    ):
                        _publish_report(self.wfile)
                    else:
                        apply_request(payload)
                elif packet_type == 0xC0:
                    self.wfile.write(b"\xd0\x00")
                    self.wfile.flush()
                elif packet_type == 0xE0:
                    return
        except (ConnectionError, OSError, ssl.SSLError, ValueError):
            return


class ThreadingTlsServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, handler, context: ssl.SSLContext):
        self.context = context
        super().__init__(address, handler)

    def get_request(self):
        socket, address = super().get_request()
        try:
            return self.context.wrap_socket(socket, server_side=True), address
        except Exception:
            socket.close()
            raise


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/healthz":
            self.send_error(404)
            return
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    health = ThreadingHTTPServer(("0.0.0.0", 8884), HealthHandler)
    threading.Thread(target=health.serve_forever, daemon=True).start()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERT_FILE, KEY_FILE)
    server = ThreadingTlsServer(("0.0.0.0", 8883), BambuMqttHandler, context)
    server.serve_forever()


if __name__ == "__main__":
    main()
