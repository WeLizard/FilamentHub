#!/usr/bin/env python3
"""
Mock Orca test bridge for local MCP smoke tests.

Protocol:
- TCP server, UTF-8 JSON per line.
- Request fields: command (str), params (object), request_id (str optional).
- Response: JSON object per line.
"""

from __future__ import annotations

import argparse
import json
import socketserver
import threading
import time
import uuid
from typing import Any


def handle_command(command: str, params: dict[str, Any]) -> dict[str, Any]:
    if command == "ping":
        return {"ok": True, "pong": True, "ts": time.time()}

    if command == "get_status":
        return {
            "ok": True,
            "status": {
                "connected": True,
                "logged_in": False,
                "sync_running": False,
                "active_tab": "filamenthub",
            },
        }

    if command == "trigger_sync":
        return {
            "ok": True,
            "accepted": True,
            "job_id": str(uuid.uuid4()),
            "mode": params.get("mode", "incremental"),
        }

    if command == "login_with_token":
        token = params.get("access_token")
        return {"ok": bool(token), "message": "mock login accepted" if token else "missing access_token"}

    return {"ok": False, "error": f"unknown command '{command}'"}


class BridgeHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        while True:
            raw = self.rfile.readline()
            if not raw:
                return

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                req = json.loads(line)
                command = req.get("command")
                params = req.get("params") or {}
                request_id = req.get("request_id")

                if not isinstance(command, str):
                    response = {
                        "ok": False,
                        "error": "field 'command' must be string",
                        "request_id": request_id,
                    }
                elif not isinstance(params, dict):
                    response = {
                        "ok": False,
                        "error": "field 'params' must be object",
                        "request_id": request_id,
                    }
                else:
                    response = handle_command(command, params)
                    response["request_id"] = request_id

            except json.JSONDecodeError:
                response = {"ok": False, "error": "invalid json"}
            except Exception as exc:  # pragma: no cover
                response = {"ok": False, "error": f"internal error: {exc!r}"}

            encoded = (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
            self.wfile.write(encoded)
            self.wfile.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock Orca test bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=45454)
    args = parser.parse_args()

    server = socketserver.ThreadingTCPServer((args.host, args.port), BridgeHandler)
    server.daemon_threads = True
    server.allow_reuse_address = True

    stop_event = threading.Event()
    print(f"[mock-bridge] listening on {args.host}:{args.port}", flush=True)
    try:
        while not stop_event.is_set():
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[mock-bridge] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
