"""Deterministic Moonraker/Happy Hare HTTP surface for local adapter checks."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


API_KEY = os.environ.get("MOONRAKER_API_KEY", "adapter-lab-hh-key")
SPOOLMAN_URL = os.environ.get(
    "SPOOLMAN_URL", "https://filamenthub.ru/api/v1/spool_compat/adapter-lab-inventory-key"
)
MAX_BODY_BYTES = 64 * 1024

MMU_STATE = {
    "num_gates": 4,
    "gate_status": [2, 1, 1, 0],
    "gate_material": ["PLA", "PETG", "ABS", ""],
    "gate_color": ["FF6A13", "1F8A70", "3366CC", ""],
    "gate_temperature": [215, 245, 255, 0],
    "gate_spool_id": [101, 102, 103, -1],
    "spoolman_support": "pull",
    "has_bypass": True,
    "tool": -2,
    "gate": -2,
    "filament_pos": 8.0,
}


class MoonrakerHandler(BaseHTTPRequestHandler):
    server_version = "FilamentHubMoonrakerLab/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not API_KEY or self.headers.get("X-Api-Key") == API_KEY:
            return True
        self._json(401, {"error": {"code": 401, "message": "Unauthorized"}})
        return False

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/healthz":
            self._json(200, {"status": "ok"})
            return
        if not self._authorized():
            return
        if self.path == "/printer/objects/list":
            self._json(200, {"result": {"objects": ["mmu", "print_stats"]}})
            return
        if self.path == "/server/database/item?namespace=moonraker&key=instance_id":
            self._json(200, {"result": {
                "namespace": "moonraker", "key": "instance_id",
                "value": "180c0846-5920-4d68-a7eb-71d97ff632ca",
            }})
            return
        if self.path == "/server/config":
            self._json(200, {"result": {"config": {"spoolman": {"server": SPOOLMAN_URL}}}})
            return
        if self.path == "/printer/info":
            self._json(
                200,
                {
                    "result": {
                        "state": "ready",
                        "state_message": "Printer is ready",
                        "hostname": "fh-moonraker-lab",
                        "software_version": "adapter-lab",
                    }
                },
            )
            return
        if self.path == "/server/info":
            self._json(
                200,
                {
                    "result": {
                        "klippy_connected": True,
                        "klippy_state": "ready",
                        "components": ["klippy_connection"],
                    }
                },
            )
            return
        self._json(404, {"error": {"code": 404, "message": "Not Found"}})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self._authorized():
            return
        if self.path != "/printer/objects/query":
            self._json(404, {"error": {"code": 404, "message": "Not Found"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._json(413, {"error": {"code": 413, "message": "Payload Too Large"}})
            return
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
        except (UnicodeDecodeError, ValueError):
            self._json(400, {"error": {"code": 400, "message": "Invalid JSON"}})
            return
        objects = request.get("objects") if isinstance(request, dict) else None
        if not isinstance(objects, dict):
            self._json(400, {"error": {"code": 400, "message": "Missing objects"}})
            return
        status = {}
        if "mmu" in objects:
            status["mmu"] = MMU_STATE
        if "print_stats" in objects:
            status["print_stats"] = {
                "state": "standby",
                "filename": "",
                "filament_used": 0.0,
                "total_duration": 0.0,
                "print_duration": 0.0,
            }
        self._json(200, {"result": {"eventtime": 1.0, "status": status}})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 7125), MoonrakerHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
