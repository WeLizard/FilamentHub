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


STATE_LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "connected": True,
    "logged_in": False,
    "sync_running": False,
    "active_tab": "filamenthub",
}
ACTIVE_SYNC_JOB: str | None = None
ACTIVE_TIMER: threading.Timer | None = None


def _snapshot_status() -> dict[str, Any]:
    with STATE_LOCK:
        return dict(STATE)


def _set_status(values: dict[str, Any]) -> dict[str, Any]:
    allowed = {"connected", "logged_in", "sync_running", "active_tab"}
    unknown_keys = [key for key in values if key not in allowed]
    if unknown_keys:
        return {"ok": False, "error": f"unsupported status keys: {', '.join(sorted(unknown_keys))}"}

    with STATE_LOCK:
        for key, value in values.items():
            if key == "active_tab":
                if not isinstance(value, str):
                    return {"ok": False, "error": "active_tab must be string"}
                STATE[key] = value
            elif key in {"connected", "logged_in", "sync_running"}:
                if not isinstance(value, bool):
                    return {"ok": False, "error": f"{key} must be boolean"}
                STATE[key] = value
    return {"ok": True, "status": _snapshot_status()}


def _complete_sync(job_id: str) -> None:
    global ACTIVE_SYNC_JOB, ACTIVE_TIMER
    with STATE_LOCK:
        # Ignore stale timer callbacks if another sync started after this one.
        if ACTIVE_SYNC_JOB != job_id:
            return
        STATE["sync_running"] = False
        ACTIVE_SYNC_JOB = None
        ACTIVE_TIMER = None


def _start_sync(duration_ms: int) -> tuple[str, dict[str, Any]]:
    global ACTIVE_SYNC_JOB, ACTIVE_TIMER
    job_id = str(uuid.uuid4())
    timer = threading.Timer(duration_ms / 1000.0, _complete_sync, args=(job_id,))
    with STATE_LOCK:
        if ACTIVE_TIMER is not None:
            ACTIVE_TIMER.cancel()
        STATE["sync_running"] = True
        ACTIVE_SYNC_JOB = job_id
        ACTIVE_TIMER = timer
    timer.start()
    return job_id, _snapshot_status()


def handle_command(command: str, params: dict[str, Any]) -> dict[str, Any]:
    if command == "ping":
        return {"ok": True, "pong": True, "ts": time.time()}

    if command == "get_status":
        return {
            "ok": True,
            "status": _snapshot_status(),
        }

    if command == "trigger_sync":
        raw_duration_ms = params.get("duration_ms", 1500)
        if not isinstance(raw_duration_ms, int) or raw_duration_ms <= 0:
            return {"ok": False, "error": "duration_ms must be a positive integer"}
        job_id, status = _start_sync(raw_duration_ms)
        return {
            "ok": True,
            "accepted": True,
            "job_id": job_id,
            "mode": params.get("mode", "incremental"),
            "duration_ms": raw_duration_ms,
            "status": status,
        }

    if command == "login_with_token":
        token = params.get("access_token")
        if not token:
            with STATE_LOCK:
                STATE["logged_in"] = False
            return {"ok": False, "message": "missing access_token", "status": _snapshot_status()}
        with STATE_LOCK:
            STATE["logged_in"] = True
        return {"ok": True, "message": "mock login accepted", "status": _snapshot_status()}

    if command == "set_status":
        values = params.get("status")
        if not isinstance(values, dict):
            return {"ok": False, "error": "set_status requires object field 'status'"}
        return _set_status(values)

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
