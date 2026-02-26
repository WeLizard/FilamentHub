#!/usr/bin/env python3
"""
Minimal MCP server for OrcaSlicer test automation (PoC).

Transport:
- MCP over stdio (JSON-RPC 2.0).

Bridge:
- Talks to an OrcaSlicer test bridge over TCP (JSON line protocol).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from typing import Any, Callable

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "orcaslicer-test-mcp"
SERVER_VERSION = "0.1.0"


@dataclass(frozen=True)
class BridgeConfig:
    host: str
    port: int
    timeout_s: float
    debug: bool


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise JsonRpcError(-32602, f"Environment variable {name} must be an integer.") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise JsonRpcError(-32602, f"Environment variable {name} must be a float.") from exc


def load_config() -> BridgeConfig:
    return BridgeConfig(
        host=os.getenv("ORCA_BRIDGE_HOST", "127.0.0.1"),
        port=_env_int("ORCA_BRIDGE_PORT", 45454),
        timeout_s=_env_float("ORCA_BRIDGE_TIMEOUT_SECONDS", 5.0),
        debug=os.getenv("MCP_DEBUG", "0") in ("1", "true", "TRUE", "yes", "YES"),
    )


def log_debug(cfg: BridgeConfig, message: str) -> None:
    if cfg.debug:
        sys.stderr.write(f"[{SERVER_NAME}] {message}\n")
        sys.stderr.flush()


def make_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(
    request_id: Any,
    code: int,
    message: str,
    data: Any | None = None,
) -> dict[str, Any]:
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error_obj["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error_obj}


def write_json(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def content_text(text: str, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
    }
    if is_error:
        result["isError"] = True
    return result


def bridge_exchange(
    cfg: BridgeConfig,
    payload: dict[str, Any],
    timeout_ms: int | None = None,
) -> Any:
    timeout_s = cfg.timeout_s if timeout_ms is None else max(timeout_ms / 1000.0, 0.001)
    encoded = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")

    with socket.create_connection((cfg.host, cfg.port), timeout=timeout_s) as sock:
        sock.settimeout(timeout_s)
        sock.sendall(encoded)

        chunks = bytearray()
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.extend(chunk)
            if b"\n" in chunk:
                break

    if not chunks:
        raise JsonRpcError(-32001, "No response from Orca bridge.")

    line = chunks.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
    if not line:
        raise JsonRpcError(-32001, "Empty response from Orca bridge.")

    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"raw": line}


def tool_orca_bridge_ping(args: dict[str, Any], cfg: BridgeConfig) -> dict[str, Any]:
    if args:
        raise JsonRpcError(-32602, "orca_bridge_ping does not accept arguments.")

    t0 = time.monotonic()
    with socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout_s):
        pass
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)

    return content_text(
        json.dumps(
            {
                "ok": True,
                "host": cfg.host,
                "port": cfg.port,
                "latency_ms": elapsed_ms,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def tool_orca_bridge_command(args: dict[str, Any], cfg: BridgeConfig) -> dict[str, Any]:
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        raise JsonRpcError(-32602, "orca_bridge_command requires non-empty string argument 'command'.")

    params = args.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise JsonRpcError(-32602, "Argument 'params' must be an object.")

    request_id = args.get("request_id")
    if request_id is None:
        request_id = str(uuid.uuid4())
    if not isinstance(request_id, str):
        raise JsonRpcError(-32602, "Argument 'request_id' must be a string when provided.")

    timeout_ms = args.get("timeout_ms")
    if timeout_ms is not None and (not isinstance(timeout_ms, int) or timeout_ms <= 0):
        raise JsonRpcError(-32602, "Argument 'timeout_ms' must be a positive integer when provided.")

    payload = {
        "command": command,
        "params": params,
        "request_id": request_id,
    }
    response = bridge_exchange(cfg, payload, timeout_ms=timeout_ms)
    return content_text(json.dumps(response, ensure_ascii=False, indent=2))


def _coerce_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise JsonRpcError(-32602, f"Argument '{field_name}' must be an array of strings.")
    return value


def tool_orca_orcaslicer_launch(args: dict[str, Any], cfg: BridgeConfig) -> dict[str, Any]:
    executable_path = args.get("executable_path")
    if not isinstance(executable_path, str) or not executable_path.strip():
        raise JsonRpcError(
            -32602,
            "orca_orcaslicer_launch requires non-empty string argument 'executable_path'.",
        )

    cmd = [executable_path] + _coerce_string_list(args.get("args"), "args")

    cwd = args.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise JsonRpcError(-32602, "Argument 'cwd' must be a string when provided.")

    extra_env = args.get("env")
    if extra_env is None:
        extra_env = {}
    if not isinstance(extra_env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in extra_env.items()
    ):
        raise JsonRpcError(-32602, "Argument 'env' must be an object with string values.")

    merged_env = os.environ.copy()
    merged_env.update(extra_env)

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    log_debug(cfg, f"Launching Orca: cmd={cmd!r}, cwd={cwd!r}")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd or None,
            env=merged_env,
            creationflags=creationflags,
        )
    except OSError as exc:
        raise JsonRpcError(-32002, f"Failed to launch OrcaSlicer: {exc}") from exc

    return content_text(
        json.dumps(
            {
                "ok": True,
                "pid": proc.pid,
                "command": cmd,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


TOOLS: list[dict[str, Any]] = [
    {
        "name": "orca_bridge_ping",
        "description": "Check TCP connectivity to Orca test bridge.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "orca_bridge_command",
        "description": "Send a command to Orca test bridge over TCP and return JSON response.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bridge command name."},
                "params": {"type": "object", "description": "Command payload.", "default": {}},
                "request_id": {"type": "string", "description": "Optional request id."},
                "timeout_ms": {"type": "integer", "minimum": 1, "description": "Optional timeout override."},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "name": "orca_orcaslicer_launch",
        "description": "Launch OrcaSlicer executable (dev/testing only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "executable_path": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}, "default": []},
                "cwd": {"type": "string"},
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
            },
            "required": ["executable_path"],
            "additionalProperties": False,
        },
    },
]


def run() -> int:
    cfg = load_config()
    handlers: dict[str, Callable[[dict[str, Any], BridgeConfig], dict[str, Any]]] = {
        "orca_bridge_ping": tool_orca_bridge_ping,
        "orca_bridge_command": tool_orca_bridge_command,
        "orca_orcaslicer_launch": tool_orca_orcaslicer_launch,
    }

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue

        request_id: Any = None
        try:
            req = json.loads(line)
            request_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                }
                if request_id is not None:
                    write_json(make_response(request_id, result))
                continue

            if method in ("notifications/initialized", "initialized", "$/cancelRequest"):
                # Notification methods do not require responses.
                continue

            if method == "ping":
                if request_id is not None:
                    write_json(make_response(request_id, {}))
                continue

            if method == "tools/list":
                if request_id is not None:
                    write_json(make_response(request_id, {"tools": TOOLS}))
                continue

            if method == "tools/call":
                if not isinstance(params, dict):
                    raise JsonRpcError(-32602, "tools/call params must be an object.")
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                if not isinstance(tool_name, str):
                    raise JsonRpcError(-32602, "tools/call requires string field 'name'.")
                if not isinstance(tool_args, dict):
                    raise JsonRpcError(-32602, "tools/call field 'arguments' must be an object.")

                handler = handlers.get(tool_name)
                if handler is None:
                    raise JsonRpcError(-32601, f"Unknown tool: {tool_name}")

                result = handler(tool_args, cfg)
                if request_id is not None:
                    write_json(make_response(request_id, result))
                continue

            raise JsonRpcError(-32601, f"Method not found: {method}")

        except JsonRpcError as exc:
            if request_id is not None:
                write_json(make_error(request_id, exc.code, exc.message, exc.data))
        except Exception as exc:  # pragma: no cover - safety net for protocol loop
            if request_id is not None:
                details = {
                    "exception": repr(exc),
                    "traceback": traceback.format_exc() if cfg.debug else None,
                }
                write_json(make_error(request_id, -32603, "Internal error", details))

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
