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
SERVER_VERSION = "0.3.0"


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


_transport_uses_content_length: bool | None = None


def _write_framed_json(message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def _write_line_json(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def write_json(message: dict[str, Any]) -> None:
    # Match client transport mode once detected from incoming traffic.
    if _transport_uses_content_length:
        _write_framed_json(message)
    else:
        _write_line_json(message)


def _read_content_length_message(first_line: bytes) -> dict[str, Any]:
    global _transport_uses_content_length

    header_line = first_line.decode("ascii", errors="replace").strip()
    if ":" not in header_line:
        raise JsonRpcError(-32700, "Invalid header line.")

    key, value = header_line.split(":", 1)
    if key.strip().lower() != "content-length":
        raise JsonRpcError(-32700, f"Unexpected header: {key.strip()}")

    try:
        content_length = int(value.strip())
    except ValueError as exc:
        raise JsonRpcError(-32700, "Invalid Content-Length value.") from exc

    if content_length < 0:
        raise JsonRpcError(-32700, "Negative Content-Length is not allowed.")

    # Consume remaining headers up to the empty line.
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            raise EOFError
        if line in (b"\r\n", b"\n"):
            break

    payload = sys.stdin.buffer.read(content_length)
    if len(payload) != content_length:
        raise EOFError

    _transport_uses_content_length = True
    return json.loads(payload.decode("utf-8", errors="replace"))


def read_message() -> dict[str, Any] | None:
    global _transport_uses_content_length

    first_line = sys.stdin.buffer.readline()
    if not first_line:
        return None

    stripped = first_line.strip()
    if not stripped:
        return read_message()

    if stripped.startswith(b"{"):
        _transport_uses_content_length = False
        return json.loads(first_line.decode("utf-8", errors="replace"))

    # Assume framed transport.
    return _read_content_length_message(first_line)


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
    log_debug(cfg, f"Bridge request -> {payload!r}")

    try:
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
    except TimeoutError as exc:
        raise JsonRpcError(-32001, f"Bridge timeout after {round(timeout_s, 3)}s.") from exc
    except OSError as exc:
        raise JsonRpcError(-32001, f"Bridge connection failed: {exc}") from exc

    if not chunks:
        raise JsonRpcError(-32001, "No response from Orca bridge.")

    line = chunks.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
    if not line:
        raise JsonRpcError(-32001, "Empty response from Orca bridge.")
    log_debug(cfg, f"Bridge response <- {line}")

    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"raw": line}


def tool_orca_bridge_ping(args: dict[str, Any], cfg: BridgeConfig) -> dict[str, Any]:
    if args:
        raise JsonRpcError(-32602, "orca_bridge_ping does not accept arguments.")

    t0 = time.monotonic()
    try:
        with socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout_s):
            pass
    except TimeoutError as exc:
        raise JsonRpcError(-32001, f"Bridge timeout after {round(cfg.timeout_s, 3)}s.") from exc
    except OSError as exc:
        raise JsonRpcError(-32001, f"Bridge connection failed: {exc}") from exc
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


def _extract_path_value(payload: Any, path: str) -> tuple[bool, Any]:
    """Extract dotted path from nested dict/list.

    Rules:
    - dict key access by token name
    - list access by numeric token (e.g. "items.0.id")
    """
    if not path:
        return True, payload

    current = payload
    for token in path.split("."):
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
            continue

        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError:
                return False, None
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
            continue

        return False, None

    return True, current


def tool_orca_bridge_wait_for(args: dict[str, Any], cfg: BridgeConfig) -> dict[str, Any]:
    command = args.get("command", "get_status")
    if not isinstance(command, str) or not command.strip():
        raise JsonRpcError(-32602, "Argument 'command' must be a non-empty string.")

    params = args.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise JsonRpcError(-32602, "Argument 'params' must be an object.")

    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        raise JsonRpcError(-32602, "Argument 'path' must be a non-empty dotted string.")

    if "equals" not in args:
        raise JsonRpcError(-32602, "Argument 'equals' is required.")
    expected = args.get("equals")
    if isinstance(expected, (dict, list)):
        raise JsonRpcError(-32602, "Argument 'equals' must be a scalar (string/number/bool/null).")

    timeout_ms = args.get("timeout_ms", 10_000)
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise JsonRpcError(-32602, "Argument 'timeout_ms' must be a positive integer.")

    interval_ms = args.get("interval_ms", 300)
    if not isinstance(interval_ms, int) or interval_ms <= 0:
        raise JsonRpcError(-32602, "Argument 'interval_ms' must be a positive integer.")

    deadline = time.monotonic() + timeout_ms / 1000.0
    attempts = 0
    last_response: Any = None
    last_actual: Any = None
    matched = False
    t0 = time.monotonic()

    while time.monotonic() < deadline:
        attempts += 1
        request_id = str(uuid.uuid4())
        payload = {"command": command, "params": params, "request_id": request_id}
        response = bridge_exchange(cfg, payload, timeout_ms=timeout_ms)
        last_response = response
        found, actual = _extract_path_value(response, path)
        last_actual = actual if found else None
        if found and actual == expected:
            matched = True
            break
        time.sleep(interval_ms / 1000.0)

    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    if not matched:
        raise JsonRpcError(
            -32003,
            "Bridge condition was not met before timeout.",
            {
                "command": command,
                "path": path,
                "expected": expected,
                "last_actual": last_actual,
                "attempts": attempts,
                "elapsed_ms": elapsed_ms,
                "last_response": last_response,
            },
        )

    return content_text(
        json.dumps(
            {
                "ok": True,
                "command": command,
                "path": path,
                "expected": expected,
                "actual": last_actual,
                "attempts": attempts,
                "elapsed_ms": elapsed_ms,
                "response": last_response,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _parse_bridge_json_text(payload: dict[str, Any], field_name: str) -> dict[str, Any]:
    content = payload.get("content")
    if not isinstance(content, list) or not content:
        raise JsonRpcError(-32603, f"{field_name} returned invalid MCP content payload.")

    first_chunk = content[0]
    if not isinstance(first_chunk, dict):
        raise JsonRpcError(-32603, f"{field_name} returned malformed content chunk.")

    text = first_chunk.get("text")
    if not isinstance(text, str):
        raise JsonRpcError(-32603, f"{field_name} returned non-text content.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonRpcError(-32603, f"{field_name} returned non-JSON text payload.") from exc

    if not isinstance(parsed, dict):
        raise JsonRpcError(-32603, f"{field_name} JSON payload must be an object.")
    return parsed


def tool_orca_bridge_smoke_test(args: dict[str, Any], cfg: BridgeConfig) -> dict[str, Any]:
    timeout_ms = args.get("timeout_ms", 15_000)
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise JsonRpcError(-32602, "Argument 'timeout_ms' must be a positive integer.")

    interval_ms = args.get("interval_ms", 250)
    if not isinstance(interval_ms, int) or interval_ms <= 0:
        raise JsonRpcError(-32602, "Argument 'interval_ms' must be a positive integer.")

    strict = args.get("strict", False)
    if not isinstance(strict, bool):
        raise JsonRpcError(-32602, "Argument 'strict' must be boolean.")

    trigger_sync = args.get("trigger_sync", True)
    if not isinstance(trigger_sync, bool):
        raise JsonRpcError(-32602, "Argument 'trigger_sync' must be boolean.")

    sync_mode = args.get("sync_mode", "incremental")
    if not isinstance(sync_mode, str) or not sync_mode.strip():
        raise JsonRpcError(-32602, "Argument 'sync_mode' must be a non-empty string.")

    sync_duration_ms = args.get("sync_duration_ms")
    if sync_duration_ms is not None and (not isinstance(sync_duration_ms, int) or sync_duration_ms <= 0):
        raise JsonRpcError(-32602, "Argument 'sync_duration_ms' must be a positive integer when provided.")

    steps: list[dict[str, Any]] = []
    ok = True

    # Step 1: TCP ping.
    try:
        ping_result = json.loads(tool_orca_bridge_ping({}, cfg)["content"][0]["text"])
        steps.append({"name": "bridge_ping", "ok": True, "result": ping_result})
    except Exception as exc:
        ok = False
        steps.append({"name": "bridge_ping", "ok": False, "error": str(exc)})
        if strict:
            raise

    # Step 2: get_status.
    status_payload: dict[str, Any] | None = None
    try:
        status_mcp = tool_orca_bridge_command(
            {"command": "get_status", "timeout_ms": timeout_ms},
            cfg,
        )
        status_payload = _parse_bridge_json_text(status_mcp, "get_status")
        status_ok = bool(status_payload.get("ok"))
        steps.append({"name": "get_status", "ok": status_ok, "result": status_payload})
        ok = ok and status_ok
        if strict and not status_ok:
            raise JsonRpcError(-32003, "Smoke get_status failed.", {"result": status_payload})
    except Exception as exc:
        ok = False
        steps.append({"name": "get_status", "ok": False, "error": str(exc)})
        if strict:
            raise

    # Step 3: optional sync lifecycle check.
    if trigger_sync:
        trigger_args: dict[str, Any] = {
            "command": "trigger_sync",
            "params": {"mode": sync_mode},
            "timeout_ms": timeout_ms,
        }
        if sync_duration_ms is not None:
            trigger_args["params"]["duration_ms"] = sync_duration_ms

        try:
            trigger_mcp = tool_orca_bridge_command(trigger_args, cfg)
            trigger_payload = _parse_bridge_json_text(trigger_mcp, "trigger_sync")
            trigger_ok = bool(trigger_payload.get("ok")) and bool(trigger_payload.get("accepted", True))

            if trigger_ok:
                wait_mcp = tool_orca_bridge_wait_for(
                    {
                        "path": "status.sync_running",
                        "equals": False,
                        "timeout_ms": timeout_ms,
                        "interval_ms": interval_ms,
                    },
                    cfg,
                )
                wait_payload = _parse_bridge_json_text(wait_mcp, "wait_for")
                steps.append(
                    {
                        "name": "sync_lifecycle",
                        "ok": True,
                        "trigger": trigger_payload,
                        "wait": wait_payload,
                    }
                )
            else:
                trigger_error_text = str(trigger_payload.get("error") or trigger_payload.get("message") or "")
                if "unknown command" in trigger_error_text.lower() and not strict:
                    steps.append(
                        {
                            "name": "sync_lifecycle",
                            "ok": True,
                            "skipped": True,
                            "reason": "trigger_sync not supported by bridge",
                            "trigger": trigger_payload,
                        }
                    )
                else:
                    steps.append(
                        {
                            "name": "sync_lifecycle",
                            "ok": False,
                            "error": "trigger_sync not accepted",
                            "trigger": trigger_payload,
                        }
                    )
                    ok = False
                    if strict:
                        raise JsonRpcError(-32003, "Smoke trigger_sync failed.", {"result": trigger_payload})
        except JsonRpcError:
            raise
        except Exception as exc:
            message = str(exc)
            skipped = "unknown command" in message.lower()
            if skipped and not strict:
                steps.append(
                    {
                        "name": "sync_lifecycle",
                        "ok": True,
                        "skipped": True,
                        "reason": "trigger_sync not supported by bridge",
                    }
                )
            else:
                ok = False
                steps.append({"name": "sync_lifecycle", "ok": False, "error": message})
                if strict:
                    raise

    response_payload = {
        "ok": ok,
        "bridge": {"host": cfg.host, "port": cfg.port},
        "server_version": SERVER_VERSION,
        "steps": steps,
    }

    if strict and not ok:
        raise JsonRpcError(-32003, "Smoke test failed in strict mode.", response_payload)

    return content_text(json.dumps(response_payload, ensure_ascii=False, indent=2), is_error=not ok)


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
        "name": "orca_bridge_wait_for",
        "description": "Poll bridge command until response path equals expected value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Bridge command to poll (default: get_status).",
                    "default": "get_status",
                },
                "params": {"type": "object", "description": "Command payload.", "default": {}},
                "path": {
                    "type": "string",
                    "description": "Dotted path in response, e.g. status.sync_running",
                },
                "equals": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "number"},
                        {"type": "boolean"},
                        {"type": "null"},
                    ],
                    "description": "Expected scalar value at the given path.",
                },
                "timeout_ms": {"type": "integer", "minimum": 1, "default": 10000},
                "interval_ms": {"type": "integer", "minimum": 1, "default": 300},
            },
            "required": ["path", "equals"],
            "additionalProperties": False,
        },
    },
    {
        "name": "orca_bridge_smoke_test",
        "description": "Run a lightweight bridge smoke test (ping/status/sync lifecycle).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trigger_sync": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to test trigger_sync + wait_for lifecycle.",
                },
                "sync_mode": {
                    "type": "string",
                    "default": "incremental",
                    "description": "Value for trigger_sync.params.mode.",
                },
                "sync_duration_ms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional duration override for mock bridge trigger_sync.",
                },
                "timeout_ms": {"type": "integer", "minimum": 1, "default": 15000},
                "interval_ms": {"type": "integer", "minimum": 1, "default": 250},
                "strict": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, fail on any unsupported/failed smoke step.",
                },
            },
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
        "orca_bridge_wait_for": tool_orca_bridge_wait_for,
        "orca_bridge_smoke_test": tool_orca_bridge_smoke_test,
        "orca_orcaslicer_launch": tool_orca_orcaslicer_launch,
    }

    while True:
        request_id: Any = None
        try:
            req = read_message()
            if req is None:
                break

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
        except EOFError:
            break
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
