#!/usr/bin/env python3
"""
End-to-end smoke test for OrcaSlicer Test MCP.

Modes:
- mock (default): starts local mock bridge and validates full tool flow.
- external: uses existing bridge endpoint without starting mock bridge.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _wait_for_tcp(host: str, port: int, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _parse_json_lines(stdout: str) -> dict[int, dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        response_id = payload.get("id")
        if isinstance(response_id, int):
            by_id[response_id] = payload
    return by_id


def _require_response(responses: dict[int, dict[str, Any]], response_id: int) -> dict[str, Any]:
    response = responses.get(response_id)
    if response is None:
        raise RuntimeError(f"Missing MCP response id={response_id}")
    if "error" in response:
        raise RuntimeError(f"MCP error for id={response_id}: {response['error']}")
    return response


def _extract_tool_json(response: dict[str, Any], response_id: int) -> dict[str, Any]:
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"Invalid MCP result for id={response_id}")

    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError(f"Missing MCP content for id={response_id}")

    chunk = content[0]
    if not isinstance(chunk, dict):
        raise RuntimeError(f"Invalid MCP content chunk for id={response_id}")

    text = chunk.get("text")
    if not isinstance(text, str):
        raise RuntimeError(f"Missing text content for id={response_id}")

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Tool payload is not an object for id={response_id}")
    return payload


def _build_requests(mode: str) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smoke-test", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "orca_bridge_ping", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "orca_bridge_command",
                "arguments": {"command": "get_status"},
            },
        },
    ]

    if mode == "mock":
        requests.extend(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "orca_bridge_command",
                        "arguments": {"command": "trigger_sync", "params": {"duration_ms": 500}},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "orca_bridge_wait_for",
                        "arguments": {
                            "path": "status.sync_running",
                            "equals": False,
                            "timeout_ms": 5000,
                            "interval_ms": 100,
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "orca_bridge_smoke_test",
                        "arguments": {"strict": True, "sync_duration_ms": 400},
                    },
                },
            ]
        )
    else:
        requests.append(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "orca_bridge_smoke_test",
                    "arguments": {"strict": False, "trigger_sync": False},
                },
            }
        )

    return requests


def _run_mcp_server(
    python_exe: str,
    server_path: Path,
    env: dict[str, str],
    requests: list[dict[str, Any]],
    timeout_s: float,
) -> subprocess.CompletedProcess[str]:
    input_payload = "".join(json.dumps(req, ensure_ascii=False) + "\n" for req in requests)
    return subprocess.run(
        [python_exe, str(server_path)],
        input=input_payload,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout_s,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test OrcaSlicer Test MCP end-to-end.")
    parser.add_argument("--mode", choices=("mock", "external"), default="mock")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=45454)
    parser.add_argument("--python", dest="python_exe", default=sys.executable)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    server_path = base_dir / "server.py"
    mock_path = base_dir / "mock_bridge.py"

    mock_proc: subprocess.Popen[str] | None = None
    try:
        if args.mode == "mock":
            mock_proc = subprocess.Popen(
                [args.python_exe, str(mock_path), "--host", args.host, "--port", str(args.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if not _wait_for_tcp(args.host, args.port, timeout_s=5.0):
                raise RuntimeError("Mock bridge did not start listening in time.")

        env = os.environ.copy()
        env["ORCA_BRIDGE_HOST"] = args.host
        env["ORCA_BRIDGE_PORT"] = str(args.port)
        env.setdefault("ORCA_BRIDGE_TIMEOUT_SECONDS", "5")
        if args.debug:
            env["MCP_DEBUG"] = "1"

        requests = _build_requests(args.mode)
        run = _run_mcp_server(
            python_exe=args.python_exe,
            server_path=server_path,
            env=env,
            requests=requests,
            timeout_s=args.timeout_seconds,
        )

        if args.debug:
            if run.stdout:
                print("[mcp stdout]")
                print(run.stdout)
            if run.stderr:
                print("[mcp stderr]")
                print(run.stderr)

        if run.returncode != 0:
            raise RuntimeError(f"MCP server exited with code {run.returncode}")

        responses = _parse_json_lines(run.stdout)

        init = _require_response(responses, 1)
        protocol_version = init.get("result", {}).get("protocolVersion")
        if protocol_version != "2024-11-05":
            raise RuntimeError(f"Unexpected protocol version: {protocol_version!r}")

        tools_response = _require_response(responses, 2)
        tools = tools_response.get("result", {}).get("tools", [])
        tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
        required_tools = {"orca_bridge_ping", "orca_bridge_command", "orca_bridge_wait_for", "orca_bridge_smoke_test"}
        missing = required_tools - tool_names
        if missing:
            raise RuntimeError(f"Missing required tools: {sorted(missing)}")

        ping_payload = _extract_tool_json(_require_response(responses, 3), 3)
        if not ping_payload.get("ok"):
            raise RuntimeError(f"Bridge ping failed: {ping_payload}")

        status_payload = _extract_tool_json(_require_response(responses, 4), 4)
        if not status_payload.get("ok"):
            raise RuntimeError(f"get_status failed: {status_payload}")

        if args.mode == "mock":
            trigger_payload = _extract_tool_json(_require_response(responses, 5), 5)
            if not trigger_payload.get("ok"):
                raise RuntimeError(f"trigger_sync failed: {trigger_payload}")

            wait_payload = _extract_tool_json(_require_response(responses, 6), 6)
            if not wait_payload.get("ok"):
                raise RuntimeError(f"wait_for failed: {wait_payload}")

        smoke_payload = _extract_tool_json(_require_response(responses, 7), 7)
        if not smoke_payload.get("ok"):
            raise RuntimeError(f"smoke tool failed: {smoke_payload}")

        print("OK: MCP smoke test passed.")
        print(json.dumps({"mode": args.mode, "bridge": {"host": args.host, "port": args.port}}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if mock_proc is not None:
            mock_proc.terminate()
            try:
                mock_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                mock_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

