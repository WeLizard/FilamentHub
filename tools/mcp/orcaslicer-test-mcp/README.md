# OrcaSlicer Test MCP (PoC)

Minimal MCP server for automated OrcaSlicer testing via a TCP test bridge.

## What this PoC provides

- MCP stdio server (`server.py`) with tools:
  - `orca_bridge_ping`
  - `orca_bridge_command`
  - `orca_bridge_wait_for`
  - `orca_bridge_smoke_test`
  - `filamenthub_api_request`
  - `orca_orcaslicer_launch`
- Mock TCP bridge (`mock_bridge.py`) for local smoke tests without Orca changes.

## Bridge protocol (PoC)

- Transport: TCP, one JSON object per line, UTF-8.
- Request:
  - `command` (string, required)
  - `params` (object, optional)
  - `request_id` (string, optional)
- Response: any JSON object per line.

Example request:

```json
{"command":"get_status","params":{},"request_id":"abc-1"}
```

Example response:

```json
{"ok":true,"status":{"connected":true,"logged_in":false},"request_id":"abc-1"}
```

Mock bridge also supports:

- `set_status` with payload `{"status": {...}}`
- `trigger_sync` with optional `duration_ms` (ms)

## Run mock bridge

```powershell
python tools/mcp/orcaslicer-test-mcp/mock_bridge.py --host 127.0.0.1 --port 45454
```

## Run MCP server

```powershell
$env:ORCA_BRIDGE_HOST="127.0.0.1"
$env:ORCA_BRIDGE_PORT="45454"
python tools/mcp/orcaslicer-test-mcp/server.py
```

Optional:

```powershell
$env:MCP_DEBUG="1"
$env:ORCA_BRIDGE_TIMEOUT_SECONDS="5"
$env:FILAMENTHUB_API_BASE_URL="http://127.0.0.1:8000"
$env:FILAMENTHUB_API_TOKEN="<optional-bearer-token>"
```

## Quick manual MCP smoke (stdin/stdout)

From another terminal:

```powershell
@'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"manual","version":"0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"orca_bridge_command","arguments":{"command":"get_status"}}}
'@ | python tools/mcp/orcaslicer-test-mcp/server.py
```

Backend API check example:

```powershell
@'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"manual","version":"0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"filamenthub_api_request","arguments":{"method":"GET","path":"/health","use_auth":false}}}
'@ | python tools/mcp/orcaslicer-test-mcp/server.py
```

Wait-until example:

```powershell
@'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"manual","version":"0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"orca_bridge_command","arguments":{"command":"trigger_sync","params":{"duration_ms":1500}}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"orca_bridge_wait_for","arguments":{"path":"status.sync_running","equals":false,"timeout_ms":10000,"interval_ms":250}}}
'@ | python tools/mcp/orcaslicer-test-mcp/server.py
```

## MCP config example (Codex/CLI style)

Use absolute paths for your machine:

```toml
[mcp_servers.orcaslicer_test]
command = "python"
args = ["F:/FilamentHub/tools/mcp/orcaslicer-test-mcp/server.py"]
env = { ORCA_BRIDGE_HOST = "127.0.0.1", ORCA_BRIDGE_PORT = "45454", FILAMENTHUB_API_BASE_URL = "http://127.0.0.1:8000" }
```

## One-command smoke test

Mock mode (starts local mock bridge automatically):

```powershell
python tools/mcp/orcaslicer-test-mcp/smoke_test.py --mode mock
```

External mode (checks existing bridge endpoint):

```powershell
python tools/mcp/orcaslicer-test-mcp/smoke_test.py --mode external --host 127.0.0.1 --port 45454
```

## Next step (Orca side)

Implement a dev-only `TestBridge` in OrcaSlicer that listens on localhost and handles commands:

- `ping`
- `get_status`
- `login_with_token`
- `trigger_sync`
- `list_presets`

Then wire MCP tools to these commands for deterministic regression tests.
