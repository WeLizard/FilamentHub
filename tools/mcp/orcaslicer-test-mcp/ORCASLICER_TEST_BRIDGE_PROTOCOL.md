# OrcaSlicer Test Bridge Protocol (PoC Draft)

## Goal

Provide a deterministic, non-UI channel for automated test control of OrcaSlicer.

## Scope

- Localhost-only (`127.0.0.1` by default).
- Enabled in dev/test builds only.
- JSON line protocol over TCP.

## Transport

- Client opens TCP connection to bridge port.
- One request JSON object per line.
- One response JSON object per line.
- UTF-8 encoding.

## Request format

```json
{
  "command": "string",
  "params": {},
  "request_id": "optional-string"
}
```

Fields:

- `command` required.
- `params` optional object.
- `request_id` optional correlation id.

## Response format

Command-specific JSON object, recommended baseline:

```json
{
  "ok": true,
  "request_id": "same-as-request"
}
```

On errors:

```json
{
  "ok": false,
  "error": "human-readable message",
  "code": "optional-machine-code",
  "request_id": "same-as-request"
}
```

## Recommended command set (v1)

### `get_capabilities`

Возвращает версию протокола и список поддерживаемых bridge-команд.

Response example:

```json
{
  "ok": true,
  "protocol_version": "fh-bridge-v1",
  "commands": ["ping", "get_status", "list_filament_profiles"]
}
```

### `ping`

Checks bridge liveness.

Request:

```json
{"command":"ping","params":{}}
```

Response:

```json
{"ok":true,"pong":true}
```

### `get_status`

Returns current Orca state needed by tests.

Response example:

```json
{
  "ok": true,
  "status": {
    "active_tab": "filamenthub",
    "logged_in": false,
    "sync_running": false
  }
}
```

### `login_with_token`

Injects token(s) into Orca test runtime (dev-only helper).

Params:

- `access_token` string
- `refresh_token` string optional

### `trigger_sync`

Starts FilamentHub sync.

Params:

- `mode` enum: `incremental` | `full`
- `duration_ms` integer optional (mock bridge helper for deterministic tests)

Response:

```json
{"ok":true,"accepted":true,"job_id":"..."}
```

### `list_presets`

Returns compact list of loaded presets for verification.

### `list_printers`

Возвращает список принтеров и активный принтер.

### `set_active_printer`

Выставляет активный принтер по `printer_id`.

### `list_filament_profiles`

Возвращает список профилей филамента (с фильтрами `search`, `material_type`, `source`, `limit`).

### `get_active_filament`

Возвращает назначенный профиль филамента по слоту или карту всех слотов.

### `set_active_filament`

Назначает профиль филамента в слот (`profile_id`, optional `slot`).

### `get_filament_section_snapshot`

Комплексный snapshot секции Filament:
- status
- printers
- filament_profiles
- active_filaments
- sync_history

## Mock-only helper commands

These are test helpers implemented by `mock_bridge.py`, not required for Orca bridge:

- `set_status` — set partial status fields (`connected`, `logged_in`, `sync_running`, `active_tab`)
- `reset_state` — сброс состояния mock bridge к дефолтному

## Security constraints (required)

- Bind only to localhost by default.
- Disabled in production builds.
- Optional shared secret in params/header for CI usage.
- Log all incoming test commands in debug mode.

## Versioning

Add `protocol_version` field in `get_status` response for forward compatibility.
