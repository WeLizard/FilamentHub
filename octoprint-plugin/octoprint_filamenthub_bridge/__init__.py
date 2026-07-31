"""Native FilamentHub Bridge plugin for OctoPrint."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from typing import Dict, Optional, Set

import flask
import octoprint.plugin
from octoprint.events import Events

from .tracker import ExtrusionTracker

PLUGIN_VERSION = "0.1.0"
CAPABILITIES = ["read", "write", "presence", "spool_identity", "consumption"]
HEARTBEAT_INTERVAL_SECONDS = 45
SNAPSHOT_INTERVAL_SECONDS = 120


class FilamentHubBridgePlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.EventHandlerPlugin,
):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._wake_worker = threading.Event()
        self._stop_worker = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._tracker = ExtrusionTracker()
        self._last_snapshot_monotonic = 0.0
        self._printing = False
        self._job_id: Optional[str] = None
        self._job_file: Optional[str] = None
        self._job_started_at: Optional[str] = None
        self._job_spools: Dict[int, int] = {}

    def get_settings_defaults(self):
        return {
            "server_url": "https://filamenthub.ru",
            "bridge_token": None,
            "instance_id": str(uuid.uuid4()),
            "snapshot": None,
            "snapshot_etag": None,
            "active_slot": None,
            "map_tools_to_slots": False,
            "outbox": [],
            "last_sync_at": None,
            "last_error": None,
        }

    def get_settings_restricted_paths(self):
        return [
            ["bridge_token"],
            ["snapshot"],
            ["outbox"],
        ]

    def get_assets(self):
        return {
            "js": ["js/filamenthub_bridge.js"],
            "css": ["css/filamenthub_bridge.css"],
        }

    def get_template_configs(self):
        return [
            {
                "type": "tab",
                "name": "FilamentHub",
                "custom_bindings": True,
            }
        ]

    def is_template_autoescaped(self):
        return True

    def on_after_startup(self):
        self._stop_worker.clear()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="filamenthub-bridge",
            daemon=True,
        )
        self._worker.start()
        self._wake_worker.set()
        self._logger.info("FilamentHub Bridge %s started", PLUGIN_VERSION)

    def on_shutdown(self):
        self._stop_worker.set()
        self._wake_worker.set()
        if self._worker is not None:
            self._worker.join(timeout=3)

    def get_api_commands(self):
        return {
            "pair": ["server_url", "pairing_code"],
            "sync": [],
            "select_slot": ["slot_index"],
            "set_mapping_mode": ["map_tools_to_slots"],
            "unpair": [],
        }

    def is_api_adminonly(self):
        return True

    def is_api_protected(self):
        return True

    def on_api_get(self, request):
        return flask.jsonify(self._public_state())

    def on_api_command(self, command, data):
        try:
            if command == "pair":
                self._pair(data["server_url"], data["pairing_code"])
                self._sync_once(force_snapshot=True)
            elif command == "sync":
                self._sync_once(force_snapshot=True)
            elif command == "select_slot":
                self._select_slot(int(data["slot_index"]))
            elif command == "set_mapping_mode":
                self._settings.set_boolean(
                    ["map_tools_to_slots"], bool(data["map_tools_to_slots"])
                )
                self._settings.save()
                self._wake_worker.set()
            elif command == "unpair":
                self._settings.set(["bridge_token"], None)
                self._settings.set(["snapshot"], None)
                self._settings.set(["snapshot_etag"], None)
                self._settings.set(["last_error"], None)
                self._settings.save()
            return flask.jsonify(self._public_state())
        except Exception as exc:
            self._logger.warning("Bridge API command failed", exc_info=True)
            return flask.make_response(flask.jsonify(error=str(exc)), 502)

    def on_event(self, event, payload):
        if event == Events.PRINT_STARTED:
            self._begin_print(payload)
        elif event == Events.PRINT_DONE:
            self._finish_print("completed", payload)
        elif event == Events.PRINT_CANCELLED:
            self._finish_print("cancelled", payload)
        elif event == Events.PRINT_FAILED:
            self._finish_print("failed", payload)

    def on_gcode_sent(
        self,
        comm_instance,
        phase,
        cmd,
        cmd_type,
        gcode,
        subcode=None,
        tags=None,
        *args,
        **kwargs,
    ):
        if not cmd:
            return None
        with self._lock:
            if not self._printing:
                try:
                    is_printing = bool(comm_instance.isPrinting())
                except Exception:
                    is_printing = False
                if not is_printing:
                    return None
                current_job = self._printer.get_current_job() or {}
                file_info = current_job.get("file", {}) or {}
                self._begin_print(
                    {
                        "name": file_info.get("name"),
                        "path": file_info.get("path"),
                    }
                )
            available = self._available_slots()
            active_slot = self._active_slot()
            selected, consumed = self._tracker.process(
                command=cmd,
                gcode=gcode,
                active_slot=active_slot,
                map_tools_to_slots=self._settings.get_boolean(["map_tools_to_slots"]),
                available_slots=available,
            )
            if selected != active_slot and selected in available:
                self._settings.set(["active_slot"], selected)
            if consumed > 0:
                self._logger.debug(
                    "Tracked %.3f mm of extrusion in FilamentHub slot %s",
                    consumed,
                    selected,
                )
        return None

    def _public_state(self):
        snapshot = self._settings.get(["snapshot"])
        return {
            "paired": bool(self._settings.get(["bridge_token"])),
            "server_url": self._settings.get(["server_url"]),
            "snapshot": snapshot,
            "active_slot": self._active_slot(),
            "map_tools_to_slots": self._settings.get_boolean(["map_tools_to_slots"]),
            "outbox_size": len(self._settings.get(["outbox"]) or []),
            "last_sync_at": self._settings.get(["last_sync_at"]),
            "last_error": self._settings.get(["last_error"]),
        }

    @staticmethod
    def _normalize_server_url(value: str) -> str:
        url = value.strip().rstrip("/")
        parsed = urlparse(url)
        allowed_local = parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "host.docker.internal",
        }
        if parsed.scheme != "https" and not (parsed.scheme == "http" and allowed_local):
            raise ValueError(
                "FilamentHub address must use HTTPS (HTTP is allowed only locally)."
            )
        if not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Invalid FilamentHub address.")
        return url

    def _octoprint_version(self) -> str:
        try:
            import octoprint

            return str(octoprint.__version__)
        except Exception:
            return "unknown"

    def _request(self, method: str, path: str, payload=None, extra_headers=None):
        server_url = self._settings.get(["server_url"])
        if not server_url:
            raise RuntimeError("FilamentHub address is not configured.")
        headers = {
            "Accept": "application/json",
            "User-Agent": f"OctoPrint-FilamentHubBridge/{PLUGIN_VERSION}",
        }
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        token = self._settings.get(["bridge_token"])
        if token:
            headers["X-FilamentHub-Bridge-Token"] = token
        headers.update(extra_headers or {})
        request = Request(
            f"{server_url}/api/v1/octoprint-bridge{path}", body, headers, method=method
        )
        try:
            with urlopen(request, timeout=15) as response:
                content = response.read()
                return (
                    response.status,
                    response.headers,
                    json.loads(content) if content else None,
                )
        except HTTPError as exc:
            if exc.code == 304:
                return 304, exc.headers, None
            content = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"FilamentHub returned HTTP {exc.code}: {content[:300]}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach FilamentHub: {exc.reason}") from exc

    def _pair(self, server_url: str, pairing_code: str) -> None:
        self._settings.set(["server_url"], self._normalize_server_url(server_url))
        instance_id = self._settings.get(["instance_id"]) or str(uuid.uuid4())
        self._settings.set(["instance_id"], instance_id)
        self._settings.set(["bridge_token"], None)
        self._settings.save()
        _, _, response = self._request(
            "POST",
            "/pair",
            {
                "pairing_code": pairing_code,
                "instance_id": instance_id,
                "plugin_version": PLUGIN_VERSION,
                "octoprint_version": self._octoprint_version(),
                "capabilities": CAPABILITIES,
            },
        )
        self._settings.set(["bridge_token"], response["bridge_token"])
        self._settings.set(["last_error"], None)
        self._settings.save()

    def _available_slots(self) -> Set[int]:
        snapshot = self._settings.get(["snapshot"]) or {}
        return {int(slot["index"]) for slot in snapshot.get("slots", [])}

    def _active_slot(self) -> Optional[int]:
        value = self._settings.get(["active_slot"])
        return int(value) if value is not None else None

    def _select_slot(self, slot_index: int) -> None:
        if slot_index not in self._available_slots():
            raise ValueError(
                "The selected slot is not present in the FilamentHub snapshot."
            )
        self._settings.set(["active_slot"], slot_index)
        self._settings.save()
        self._wake_worker.set()

    def _snapshot_spools(self) -> Dict[int, int]:
        snapshot = self._settings.get(["snapshot"]) or {}
        result = {}
        for slot in snapshot.get("slots", []):
            spool = slot.get("spool")
            if spool:
                result[int(slot["index"])] = int(spool["id"])
        return result

    def _begin_print(self, payload) -> None:
        with self._lock:
            # OctoPrint dispatches events asynchronously. On very short files the
            # sent-G-code hook can initialize tracking before PrintStarted arrives.
            # Never reset material already observed for the same active print.
            if self._printing:
                return
            self._tracker.reset()
            self._printing = True
            self._job_id = str(uuid.uuid4())
            self._job_file = payload.get("name") or payload.get("path")
            self._job_started_at = datetime.now(timezone.utc).isoformat()
            self._job_spools = self._snapshot_spools()
            available = self._available_slots()
            active = self._active_slot()
            if active not in available:
                assigned = sorted(self._job_spools)
                if assigned:
                    self._settings.set(["active_slot"], assigned[0])
            self._logger.info(
                "Tracking print %s with %d assigned FilamentHub spool(s)",
                self._job_file or self._job_id,
                len(self._job_spools),
            )

    def _finish_print(self, outcome: str, payload) -> None:
        with self._lock:
            if not self._printing or self._job_id is None:
                return
            items = []
            for slot_index, used_length in sorted(
                self._tracker.used_length_by_slot.items()
            ):
                spool_id = self._job_spools.get(slot_index)
                if used_length > 0 and spool_id is not None:
                    items.append(
                        {
                            "slot_index": slot_index,
                            "spool_id": spool_id,
                            "used_length_mm": used_length,
                        }
                    )
            if items:
                event = {
                    "event_id": f"{self._job_id}:terminal",
                    "job_id": self._job_id,
                    "outcome": outcome,
                    "file_name": self._job_file,
                    "duration_s": payload.get("time"),
                    "items": items,
                }
                outbox = list(self._settings.get(["outbox"]) or [])
                outbox.append(event)
                self._settings.set(["outbox"], outbox)
                self._settings.save()
            self._logger.info(
                "Finished tracking print %s: outcome=%s, usage_items=%d",
                self._job_file or self._job_id,
                outcome,
                len(items),
            )
            self._printing = False
            self._job_id = None
            self._job_file = None
            self._job_started_at = None
            self._job_spools = {}
        self._wake_worker.set()

    def _sync_snapshot(self) -> None:
        headers = {}
        etag = self._settings.get(["snapshot_etag"])
        if etag:
            headers["If-None-Match"] = etag
        status, response_headers, payload = self._request(
            "GET", "/snapshot", extra_headers=headers
        )
        if status == 304:
            return
        if status == 200 and payload is not None:
            self._settings.set(["snapshot"], payload)
            self._settings.set(["snapshot_etag"], response_headers.get("ETag"))
            available = self._available_slots()
            active = self._active_slot()
            if active not in available:
                assigned = sorted(self._snapshot_spools())
                fallback = (
                    assigned[0] if assigned else (min(available) if available else None)
                )
                self._settings.set(["active_slot"], fallback)

    def _send_heartbeat(self) -> None:
        self._request(
            "POST",
            "/heartbeat",
            {
                "instance_id": self._settings.get(["instance_id"]),
                "plugin_version": PLUGIN_VERSION,
                "octoprint_version": self._octoprint_version(),
                "capabilities": CAPABILITIES,
                "active_slot_index": self._active_slot(),
            },
        )

    def _flush_outbox(self) -> None:
        while True:
            with self._lock:
                outbox = list(self._settings.get(["outbox"]) or [])
                if not outbox:
                    return
                event = outbox[0]

            # Never hold the print-tracking lock during network I/O. Once FH
            # acknowledges the event, remove that exact event from the latest
            # outbox value so a terminal event appended concurrently survives.
            self._request("POST", "/usage", event)
            with self._lock:
                current = list(self._settings.get(["outbox"]) or [])
                for index, pending in enumerate(current):
                    if pending == event:
                        current.pop(index)
                        self._settings.set(["outbox"], current)
                        self._settings.save()
                        break

    def _sync_once(self, *, force_snapshot: bool = False) -> None:
        if not self._settings.get(["bridge_token"]):
            return
        try:
            now_monotonic = time.monotonic()
            if (
                force_snapshot
                or now_monotonic - self._last_snapshot_monotonic
                >= SNAPSHOT_INTERVAL_SECONDS
            ):
                self._sync_snapshot()
                self._last_snapshot_monotonic = now_monotonic
            self._send_heartbeat()
            self._flush_outbox()
            self._settings.set(["last_sync_at"], datetime.now(timezone.utc).isoformat())
            self._settings.set(["last_error"], None)
            self._settings.save()
            self._plugin_manager.send_plugin_message(
                self._identifier, self._public_state()
            )
        except Exception as exc:
            self._settings.set(["last_error"], str(exc))
            self._settings.save()
            self._logger.warning("FilamentHub synchronization failed", exc_info=True)

    def _worker_loop(self) -> None:
        while not self._stop_worker.is_set():
            self._wake_worker.wait(timeout=HEARTBEAT_INTERVAL_SECONDS)
            self._wake_worker.clear()
            if self._stop_worker.is_set():
                return
            self._sync_once()


__plugin_name__ = "FilamentHub Bridge"
__plugin_version__ = PLUGIN_VERSION
__plugin_description__ = "Native outbound material bridge for FilamentHub"
__plugin_pythoncompat__ = ">=3.9,<4"
__plugin_implementation__ = FilamentHubBridgePlugin()
__plugin_hooks__ = {
    "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.on_gcode_sent,
}
