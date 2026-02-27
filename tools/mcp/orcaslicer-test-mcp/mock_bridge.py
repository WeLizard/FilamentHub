#!/usr/bin/env python3
"""
Mock Orca test bridge for local MCP smoke and integration checks.

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
from datetime import datetime, timezone
from typing import Any

PROTOCOL_VERSION = "fh-bridge-v1"

MOCK_PRINTERS: list[dict[str, Any]] = [
    {
        "id": "printer_voron_24",
        "name": "Voron 2.4 R2",
        "vendor": "Voron Design",
        "model": "2.4",
        "nozzle_mm": 0.4,
        "online": True,
    },
    {
        "id": "printer_creality_spirit",
        "name": "Creality The Machine Spirit",
        "vendor": "Creality",
        "model": "K1",
        "nozzle_mm": 0.4,
        "online": True,
    },
]

MOCK_FILAMENT_PROFILES: list[dict[str, Any]] = [
    {
        "id": "fp_generic_pla_black",
        "name": "Generic PLA @System",
        "material_type": "PLA",
        "brand": "Generic",
        "color_name": "Black",
        "color_hex": "#111111",
        "source": "system",
        "updated_at": "2026-02-27T00:00:00Z",
    },
    {
        "id": "fp_generic_petg_white",
        "name": "Generic PETG @System",
        "material_type": "PETG",
        "brand": "Generic",
        "color_name": "White",
        "color_hex": "#F5F5F5",
        "source": "system",
        "updated_at": "2026-02-27T00:00:00Z",
    },
    {
        "id": "fp_htp_abs_black",
        "name": "HTP ABS",
        "material_type": "ABS",
        "brand": "HTP",
        "color_name": "Черный",
        "color_hex": "#101010",
        "source": "filamenthub",
        "updated_at": "2026-02-27T00:00:00Z",
    },
    {
        "id": "fp_creality_cheryomushka_petg",
        "name": "Creality Черёмушка PETG",
        "material_type": "PETG",
        "brand": "Creality",
        "color_name": "Черный",
        "color_hex": "#1E1E1E",
        "source": "filamenthub",
        "updated_at": "2026-02-27T00:00:00Z",
    },
]

MOCK_PRINT_PROFILES: list[dict[str, Any]] = [
    {
        "id": "pp_quality_020",
        "name": "Quality 0.20",
        "layer_height": 0.2,
        "quality_tier": "quality",
    },
    {
        "id": "pp_draft_028",
        "name": "Draft 0.28",
        "layer_height": 0.28,
        "quality_tier": "draft",
    },
]

MOCK_PRINTER_PROFILES: list[dict[str, Any]] = [
    {
        "id": "pr_voron_24_04",
        "name": "Voron 2.4 0.4 nozzle",
        "printer_id": "printer_voron_24",
        "nozzle_mm": 0.4,
    },
    {
        "id": "pr_creality_spirit_04",
        "name": "Creality The Machine Spirit 0.4 nozzle",
        "printer_id": "printer_creality_spirit",
        "nozzle_mm": 0.4,
    },
]

SUPPORTED_COMMANDS: list[str] = [
    "ping",
    "get_status",
    "get_capabilities",
    "set_status",
    "reset_state",
    "trigger_sync",
    "login_with_token",
    "list_printers",
    "set_active_printer",
    "list_filament_profiles",
    "get_active_filament",
    "set_active_filament",
    "list_presets",
    "get_filament_section_snapshot",
]

STATE_LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "connected": True,
    "logged_in": False,
    "sync_running": False,
    "active_tab": "filamenthub",
    "active_printer_id": "printer_voron_24",
    "active_filament_slots": {"0": "fp_generic_pla_black", "1": "fp_generic_petg_white"},
    "sync_history": [],
    "last_sync_completed_at": None,
}
ACTIVE_SYNC_JOB: str | None = None
ACTIVE_TIMER: threading.Timer | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _snapshot_status() -> dict[str, Any]:
    with STATE_LOCK:
        return {
            "connected": STATE["connected"],
            "logged_in": STATE["logged_in"],
            "sync_running": STATE["sync_running"],
            "active_tab": STATE["active_tab"],
            "protocol_version": PROTOCOL_VERSION,
            "active_printer_id": STATE["active_printer_id"],
            "active_filament_slots": dict(STATE["active_filament_slots"]),
            "last_sync_completed_at": STATE["last_sync_completed_at"],
        }


def _find_filament_profile(profile_id: str) -> dict[str, Any] | None:
    for profile in MOCK_FILAMENT_PROFILES:
        if profile["id"] == profile_id:
            return profile
    return None


def _find_printer(printer_id: str) -> dict[str, Any] | None:
    for printer in MOCK_PRINTERS:
        if printer["id"] == printer_id:
            return printer
    return None


def _set_status(values: dict[str, Any]) -> dict[str, Any]:
    allowed = {"connected", "logged_in", "sync_running", "active_tab", "active_printer_id"}
    unknown_keys = [key for key in values if key not in allowed]
    if unknown_keys:
        return {"ok": False, "error": f"unsupported status keys: {', '.join(sorted(unknown_keys))}"}

    with STATE_LOCK:
        for key, value in values.items():
            if key == "active_tab":
                if not isinstance(value, str):
                    return {"ok": False, "error": "active_tab must be string"}
                STATE[key] = value
            elif key == "active_printer_id":
                if not isinstance(value, str):
                    return {"ok": False, "error": "active_printer_id must be string"}
                if _find_printer(value) is None:
                    return {"ok": False, "error": f"unknown printer id '{value}'"}
                STATE[key] = value
            elif key in {"connected", "logged_in", "sync_running"}:
                if not isinstance(value, bool):
                    return {"ok": False, "error": f"{key} must be boolean"}
                STATE[key] = value
    return {"ok": True, "status": _snapshot_status()}


def _record_sync_event(job_id: str, mode: str, duration_ms: int, event: str) -> None:
    with STATE_LOCK:
        history: list[dict[str, Any]] = STATE["sync_history"]
        history.append(
            {
                "job_id": job_id,
                "mode": mode,
                "duration_ms": duration_ms,
                "event": event,
                "timestamp": _utc_now_iso(),
            }
        )
        if len(history) > 20:
            del history[: len(history) - 20]


def _complete_sync(job_id: str) -> None:
    global ACTIVE_SYNC_JOB, ACTIVE_TIMER
    with STATE_LOCK:
        # Ignore stale timer callbacks if another sync started after this one.
        if ACTIVE_SYNC_JOB != job_id:
            return
        STATE["sync_running"] = False
        STATE["last_sync_completed_at"] = _utc_now_iso()
        ACTIVE_SYNC_JOB = None
        ACTIVE_TIMER = None
    _record_sync_event(job_id=job_id, mode="unknown", duration_ms=0, event="completed")


def _start_sync(duration_ms: int, mode: str) -> tuple[str, dict[str, Any]]:
    global ACTIVE_SYNC_JOB, ACTIVE_TIMER
    job_id = str(uuid.uuid4())
    timer = threading.Timer(duration_ms / 1000.0, _complete_sync, args=(job_id,))
    with STATE_LOCK:
        if ACTIVE_TIMER is not None:
            ACTIVE_TIMER.cancel()
        STATE["sync_running"] = True
        ACTIVE_SYNC_JOB = job_id
        ACTIVE_TIMER = timer
    _record_sync_event(job_id=job_id, mode=mode, duration_ms=duration_ms, event="started")
    timer.start()
    return job_id, _snapshot_status()


def _reset_state() -> dict[str, Any]:
    global ACTIVE_SYNC_JOB, ACTIVE_TIMER
    with STATE_LOCK:
        STATE["connected"] = True
        STATE["logged_in"] = False
        STATE["sync_running"] = False
        STATE["active_tab"] = "filamenthub"
        STATE["active_printer_id"] = "printer_voron_24"
        STATE["active_filament_slots"] = {"0": "fp_generic_pla_black", "1": "fp_generic_petg_white"}
        STATE["sync_history"] = []
        STATE["last_sync_completed_at"] = None
        ACTIVE_SYNC_JOB = None
        if ACTIVE_TIMER is not None:
            ACTIVE_TIMER.cancel()
            ACTIVE_TIMER = None
    return {"ok": True, "status": _snapshot_status()}


def _list_filament_profiles(params: dict[str, Any]) -> dict[str, Any]:
    search = params.get("search")
    if search is not None and not isinstance(search, str):
        return {"ok": False, "error": "search must be string"}
    search_norm = (search or "").strip().lower()

    material_type = params.get("material_type")
    if material_type is not None and not isinstance(material_type, str):
        return {"ok": False, "error": "material_type must be string"}
    material_norm = (material_type or "").strip().upper()

    source = params.get("source")
    if source is not None and not isinstance(source, str):
        return {"ok": False, "error": "source must be string"}
    source_norm = (source or "").strip().lower()

    limit = params.get("limit", 100)
    if not isinstance(limit, int) or limit <= 0:
        return {"ok": False, "error": "limit must be positive integer"}

    result: list[dict[str, Any]] = []
    for profile in MOCK_FILAMENT_PROFILES:
        if material_norm and profile["material_type"].upper() != material_norm:
            continue
        if source_norm and str(profile.get("source", "")).lower() != source_norm:
            continue

        if search_norm:
            haystack = " ".join(
                [
                    str(profile.get("name", "")),
                    str(profile.get("material_type", "")),
                    str(profile.get("brand", "")),
                    str(profile.get("color_name", "")),
                    str(profile.get("color_hex", "")),
                ]
            ).lower()
            if search_norm not in haystack:
                continue

        result.append(profile)
        if len(result) >= limit:
            break

    return {"ok": True, "items": result, "count": len(result), "total": len(MOCK_FILAMENT_PROFILES)}


def _get_active_filament(params: dict[str, Any]) -> dict[str, Any]:
    slot = params.get("slot")
    if slot is not None and not isinstance(slot, (str, int)):
        return {"ok": False, "error": "slot must be string or integer"}

    with STATE_LOCK:
        slot_map = dict(STATE["active_filament_slots"])

    if slot is None:
        items = []
        for slot_key, profile_id in slot_map.items():
            profile = _find_filament_profile(profile_id)
            items.append({"slot": slot_key, "profile_id": profile_id, "profile": profile})
        return {"ok": True, "active": items}

    slot_key = str(slot)
    profile_id = slot_map.get(slot_key)
    profile = _find_filament_profile(profile_id) if profile_id else None
    return {"ok": True, "slot": slot_key, "profile_id": profile_id, "profile": profile}


def _set_active_filament(params: dict[str, Any]) -> dict[str, Any]:
    profile_id = params.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        return {"ok": False, "error": "profile_id must be non-empty string"}

    profile = _find_filament_profile(profile_id)
    if profile is None:
        return {"ok": False, "error": f"unknown profile id '{profile_id}'"}

    slot = params.get("slot", "0")
    if not isinstance(slot, (str, int)):
        return {"ok": False, "error": "slot must be string or integer"}
    slot_key = str(slot)

    with STATE_LOCK:
        STATE["active_filament_slots"][slot_key] = profile_id

    return {
        "ok": True,
        "slot": slot_key,
        "profile_id": profile_id,
        "profile": profile,
        "status": _snapshot_status(),
    }


def _list_printers() -> dict[str, Any]:
    with STATE_LOCK:
        active_printer_id = STATE["active_printer_id"]
    return {"ok": True, "items": MOCK_PRINTERS, "count": len(MOCK_PRINTERS), "active_printer_id": active_printer_id}


def _set_active_printer(params: dict[str, Any]) -> dict[str, Any]:
    printer_id = params.get("printer_id")
    if not isinstance(printer_id, str) or not printer_id.strip():
        return {"ok": False, "error": "printer_id must be non-empty string"}
    printer = _find_printer(printer_id)
    if printer is None:
        return {"ok": False, "error": f"unknown printer id '{printer_id}'"}

    with STATE_LOCK:
        STATE["active_printer_id"] = printer_id
    return {"ok": True, "active_printer_id": printer_id, "printer": printer, "status": _snapshot_status()}


def _list_presets() -> dict[str, Any]:
    return {
        "ok": True,
        "presets": {
            "filament": MOCK_FILAMENT_PROFILES,
            "print": MOCK_PRINT_PROFILES,
            "printer": MOCK_PRINTER_PROFILES,
        },
        "counts": {
            "filament": len(MOCK_FILAMENT_PROFILES),
            "print": len(MOCK_PRINT_PROFILES),
            "printer": len(MOCK_PRINTER_PROFILES),
        },
    }


def _get_filament_section_snapshot() -> dict[str, Any]:
    status = _snapshot_status()
    active = _get_active_filament({})
    printers = _list_printers()
    filaments = _list_filament_profiles({})
    with STATE_LOCK:
        sync_history = list(STATE["sync_history"])

    return {
        "ok": True,
        "status": status,
        "printers": printers.get("items", []),
        "active_printer_id": printers.get("active_printer_id"),
        "filament_profiles": filaments.get("items", []),
        "active_filaments": active.get("active", []),
        "sync_history": sync_history,
    }


def handle_command(command: str, params: dict[str, Any]) -> dict[str, Any]:
    if command == "ping":
        return {"ok": True, "pong": True, "ts": time.time(), "protocol_version": PROTOCOL_VERSION}

    if command == "get_status":
        return {
            "ok": True,
            "status": _snapshot_status(),
        }

    if command == "get_capabilities":
        return {
            "ok": True,
            "protocol_version": PROTOCOL_VERSION,
            "commands": SUPPORTED_COMMANDS,
        }

    if command == "trigger_sync":
        raw_duration_ms = params.get("duration_ms", 1500)
        if not isinstance(raw_duration_ms, int) or raw_duration_ms <= 0:
            return {"ok": False, "error": "duration_ms must be a positive integer"}
        mode = params.get("mode", "incremental")
        if not isinstance(mode, str):
            return {"ok": False, "error": "mode must be a string"}
        job_id, status = _start_sync(raw_duration_ms, mode)
        return {
            "ok": True,
            "accepted": True,
            "job_id": job_id,
            "mode": mode,
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

    if command == "reset_state":
        return _reset_state()

    if command == "list_printers":
        return _list_printers()

    if command == "set_active_printer":
        return _set_active_printer(params)

    if command == "list_filament_profiles":
        return _list_filament_profiles(params)

    if command == "get_active_filament":
        return _get_active_filament(params)

    if command == "set_active_filament":
        return _set_active_filament(params)

    if command == "list_presets":
        return _list_presets()

    if command == "get_filament_section_snapshot":
        return _get_filament_section_snapshot()

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

