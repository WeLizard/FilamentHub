"""Small stateful Bambu LAN TLS/MQTT surface for local adapter checks."""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import socket
import socketserver
import ssl
import struct
import threading
import time
import urllib.parse
import select
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ACCESS_CODE = os.environ.get("BAMBU_ACCESS_CODE", "adapterlab")
SERIAL = os.environ.get("BAMBU_SERIAL", "FH-BAMBU-LAB")
CERT_FILE = "/run/adapter-lab/bambu.crt"
KEY_FILE = "/run/adapter-lab/bambu.key"
MAX_PACKET_BYTES = 1024 * 1024
DISCOVERY_PORT = 2021
DISCOVERY_INTERVAL_SECONDS = 0.5

_state_lock = threading.Lock()
GCODE_FILE_NAME = os.environ.get("BAMBU_GCODE_FILE", "part.gcode")
GCODE_BYTES = (
    b"; filament used [g] : 12.5, 7.5\n"
    b"; adapter-lab synthetic 20g two-filament print\n"
    b"G1 X1 Y1 E1\n"
)
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


def _apply_stage(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    allowed = {"gcode_state", "mc_percent", "remaining_g", "filename",
               "gcode_file", "subtask_name", "task_id", "subtask_id",
               "ams_mapping"}
    if not any(key in payload for key in allowed):
        return False
    mapping = payload.get("ams_mapping")
    if "ams_mapping" in payload and (
        not isinstance(mapping, list) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 255
            for value in mapping
        )
    ):
        return False
    with _state_lock:
        for key in allowed - {"remaining_g", "filename", "gcode_file", "subtask_name"}:
            if key in payload:
                _report[key] = payload[key]
        if "filename" in payload:
            _report["gcode_file"] = str(payload["filename"])
            _report["subtask_name"] = str(payload["filename"])
        for key in ("gcode_file", "subtask_name"):
            if key in payload:
                _report[key] = str(payload[key])
        if "ams_mapping" in payload:
            _report["ams_mapping"] = list(mapping)
        if "remaining_g" in payload:
            _report["ams"]["ams"][0]["tray"][0]["remain_g"] = payload["remaining_g"]
    return True


def discovery_announcement(host: str) -> bytes:
    return (
        "NOTIFY * HTTP/1.1\r\n"
        "NT: urn:bambulab-com:device:3dprinter:1\r\n"
        "NTS: ssdp:alive\r\n"
        "DevName.bambu.com: FilamentHub Bambu Lab\r\n"
        f"USN: {SERIAL}\r\n"
        f"Location: {host}\r\n"
        "\r\n"
    ).encode("utf-8")


def _lan_ipv4() -> str:
    candidates = []
    try:
        candidates.extend(
            item[4][0]
            for item in socket.getaddrinfo(
                socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM
            )
        )
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            candidates.append(probe.getsockname()[0])
    except OSError:
        pass
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.version == 4 and (address.is_private or address.is_link_local):
            if not address.is_loopback and not address.is_unspecified:
                return str(address)
    raise OSError("no private LAN address available for Bambu discovery")


def announce_discovery() -> None:
    while True:
        try:
            host = _lan_ipv4()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sender.bind((host, 0))
                while True:
                    sender.sendto(
                        discovery_announcement(host),
                        ("255.255.255.255", DISCOVERY_PORT),
                    )
                    time.sleep(DISCOVERY_INTERVAL_SECONDS)
        except OSError:
            time.sleep(DISCOVERY_INTERVAL_SECONDS)


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
            subscribed = False
            last_report = 0.0
            while True:
                ready, _, _ = select.select([self.connection], [], [], 1.0)
                if not ready:
                    if subscribed and time.monotonic() - last_report >= 1:
                        _publish_report(self.wfile)
                        last_report = time.monotonic()
                    continue
                header, body = _read_packet(self.rfile)
                packet_type = header & 0xF0
                if packet_type == 0x80:
                    if len(body) < 2:
                        return
                    packet_id = body[:2]
                    self.wfile.write(b"\x90\x03" + packet_id + b"\x00")
                    self.wfile.flush()
                    _publish_report(self.wfile)
                    subscribed = True
                    last_report = time.monotonic()
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
        if urllib.parse.urlsplit(self.path).path != "/healthz":
            self.send_error(404)
            return
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urllib.parse.urlsplit(self.path).path != "/state":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(min(length, 65536)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400)
            return
        if not _apply_stage(payload):
            self.send_error(400)
            return
        body = json.dumps(snapshot(), separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BambuFtpsHandler(socketserver.StreamRequestHandler):
    """Small implicit-FTPS read-only surface for the synthetic print file."""

    def _reply(self, text: str) -> None:
        self.wfile.write((text + "\r\n").encode("ascii"))
        self.wfile.flush()

    def _data_listener(self, extended: bool):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.request.getsockname()[0], 0))
        listener.listen(1)
        host, port = listener.getsockname()
        if extended:
            self._reply("229 Entering Extended Passive Mode (|||%d|)" % port)
        else:
            self._reply("227 Entering Passive Mode (%s)" % ",".join(
                host.split(".") + [str(port // 256), str(port % 256)]
            ))
        return listener

    def _data(self, listener, payload: bytes) -> None:
        listener.settimeout(5)
        connection, _ = listener.accept()
        listener.close()
        try:
            tls = self.server.context.wrap_socket(connection, server_side=True)
            tls.settimeout(5)
            tls.sendall(payload)
            # FTP_TLS clients explicitly call unwrap() after reading the data
            # stream.  Closing the SSLSocket here does not emit the TLS close
            # notify soon enough for that handshake on all Python versions.
            try:
                tls.unwrap()
            except (OSError, ssl.SSLError):
                tls.close()
        finally:
            connection.close()

    def handle(self) -> None:
        self._reply("220 adapter-lab Bambu FTPS")
        data_listener = None
        while True:
            line = self.rfile.readline(4096)
            if not line:
                return
            parts = line.decode("ascii", "replace").strip().split(" ", 1)
            command = parts[0].upper()
            argument = parts[1] if len(parts) == 2 else ""
            if command == "USER":
                self._reply("331 Password required")
            elif command == "PASS":
                self._reply("230 Logged in") if argument == ACCESS_CODE else self._reply("530 Login incorrect")
            elif command in {"PBSZ", "PROT", "TYPE"}:
                self._reply("200 OK")
            elif command in {"PASV", "EPSV"}:
                if data_listener is not None:
                    data_listener.close()
                data_listener = self._data_listener(command == "EPSV")
            elif command == "NLST":
                if data_listener is None:
                    self._reply("425 Use PASV first")
                    continue
                listener, data_listener = data_listener, None
                self._reply("150 Opening data connection")
                directory = argument.rstrip("/") or "/"
                listing = (GCODE_FILE_NAME + "\r\n") if directory == "/cache" else ""
                self._data(listener, listing.encode("ascii"))
                self._reply("226 Transfer complete")
            elif command == "SIZE":
                self._reply("213 %d" % len(GCODE_BYTES))
            elif command == "RETR":
                if data_listener is None:
                    self._reply("425 Use PASV first")
                    continue
                listener, data_listener = data_listener, None
                self._reply("150 Opening data connection")
                self._data(listener, GCODE_BYTES)
                self._reply("226 Transfer complete")
            elif command == "QUIT":
                self._reply("221 Bye")
                return
            else:
                self._reply("502 Command not implemented")


def main() -> None:
    health = ThreadingHTTPServer(("0.0.0.0", 8884), HealthHandler)
    threading.Thread(target=health.serve_forever, daemon=True).start()
    threading.Thread(target=announce_discovery, daemon=True).start()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERT_FILE, KEY_FILE)
    server = ThreadingTlsServer(("0.0.0.0", 8883), BambuMqttHandler, context)
    ftps = ThreadingTlsServer(("0.0.0.0", 990), BambuFtpsHandler, context)
    threading.Thread(target=ftps.serve_forever, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
