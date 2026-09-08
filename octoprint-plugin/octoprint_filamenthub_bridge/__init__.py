"""Native FilamentHub Bridge plugin for OctoPrint."""

from __future__ import annotations

import json
import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Optional, Set
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import flask
import octoprint.plugin
from flask_babel import gettext
from octoprint.events import Events

from .tracker import ExtrusionTracker

PLUGIN_VERSION = "0.1.4"
# A selected manual/tool-routed slot is not proof of physical presence.
CAPABILITIES = ["read", "write", "spool_identity", "consumption"]
HEARTBEAT_INTERVAL_SECONDS = 120
SNAPSHOT_INTERVAL_SECONDS = 120
USAGE_CHECKPOINT_INTERVAL_SECONDS = 300
RETRY_INITIAL_SECONDS = 5
RETRY_MAX_SECONDS = 300
INTERVAL_JITTER_RATIO = 0.2
STARTUP_JITTER_MAX_SECONDS = 120
OUTBOX_DELIVERY_SCHEMA_VERSION = 1
OUTBOX_DELIVERY_ERROR_MAX_LENGTH = 300
OUTBOX_DELIVERY_ATTEMPT_MAX = 1_000_000
OUTBOX_WARNING_COUNT = 100
OUTBOX_WARNING_BYTES = 1_000_000
OUTBOX_WARNING_AGE_SECONDS = 7 * 24 * 60 * 60
RETRYABLE_DELIVERY_STATUS_CODES = {408, 425, 429}


class BridgeRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retry_after_seconds: Optional[float] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class OutboxDeliveryBlockedError(BridgeRequestError):
    """The current-binding head needs an explicit retry after repair."""


class OutboxDeliveryDeferredError(BridgeRequestError):
    """The current-binding head is waiting for its persisted retry deadline."""


def _retry_after_seconds(headers) -> Optional[float]:
    raw_value = headers.get("Retry-After") if headers is not None else None
    if not raw_value:
        return None
    try:
        return max(0.0, min(float(raw_value), RETRY_MAX_SECONDS))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(str(raw_value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
            return max(0.0, min(delay, RETRY_MAX_SECONDS))
        except (TypeError, ValueError, OverflowError):
            return None


def _jittered_delay(base_seconds: float) -> float:
    spread = base_seconds * INTERVAL_JITTER_RATIO
    return random.uniform(max(0.0, base_seconds - spread), base_seconds + spread)


def _retry_delay(failure_count: int, retry_after_seconds: Optional[float]) -> float:
    exponent = min(max(failure_count - 1, 0), 16)
    base = min(RETRY_INITIAL_SECONDS * (2**exponent), RETRY_MAX_SECONDS)
    return min(
        max(_jittered_delay(base), retry_after_seconds or 0.0),
        RETRY_MAX_SECONDS,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc_datetime(value) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _delivery_metadata(event: dict, *, now: Optional[datetime] = None) -> dict:
    now = now or _utc_now()
    raw = event.get("_delivery")
    raw = raw if isinstance(raw, dict) else {}
    queued_at = raw.get("queued_at") or event.get("observed_at")
    if _parse_utc_datetime(queued_at) is None:
        queued_at = now.isoformat()
    attempt_count = raw.get("attempt_count", 0)
    if isinstance(attempt_count, bool) or not isinstance(attempt_count, int):
        attempt_count = 0
    attempt_count = max(0, min(attempt_count, OUTBOX_DELIVERY_ATTEMPT_MAX))
    state = "blocked" if raw.get("state") == "blocked" else "pending"
    last_status = raw.get("last_status")
    if (
        isinstance(last_status, bool)
        or not isinstance(last_status, int)
        or not 100 <= last_status <= 599
    ):
        last_status = None
    last_error = raw.get("last_error")
    if last_error is not None:
        last_error = str(last_error)[:OUTBOX_DELIVERY_ERROR_MAX_LENGTH]
    last_attempt_at = raw.get("last_attempt_at")
    if _parse_utc_datetime(last_attempt_at) is None:
        last_attempt_at = None
    next_attempt_at = raw.get("next_attempt_at")
    if state == "blocked" or _parse_utc_datetime(next_attempt_at) is None:
        next_attempt_at = None
    return {
        "version": OUTBOX_DELIVERY_SCHEMA_VERSION,
        "queued_at": queued_at,
        "state": state,
        "attempt_count": attempt_count,
        "last_attempt_at": last_attempt_at,
        "next_attempt_at": next_attempt_at,
        "last_status": last_status,
        "last_error": last_error,
    }


def _is_retryable_delivery_error(exc: Exception) -> bool:
    if not isinstance(exc, BridgeRequestError):
        return True
    status = exc.status_code
    return (
        status is None
        or status in RETRYABLE_DELIVERY_STATUS_CODES
        or 500 <= status <= 599
    )


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
        self._connection_lock = threading.RLock()
        self._wake_worker = threading.Event()
        self._stop_worker = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._tracker = ExtrusionTracker()
        self._last_snapshot_monotonic = 0.0
        self._printing = False
        self._job_id: Optional[str] = None
        self._job_file: Optional[str] = None
        self._job_started_at: Optional[str] = None
        self._job_routes: Dict[int, dict] = {}
        self._job_binding: Optional[dict] = None
        self._usage_event_sequence = 0
        self._last_usage_checkpoint_monotonic: Optional[float] = None
        self._last_retry_after_seconds: Optional[float] = None
        self._selected_tool: Optional[int] = None

    def get_settings_defaults(self):
        return {
            "server_url": "https://filamenthub.ru",
            "bridge_token": None,
            "instance_id": str(uuid.uuid4()),
            "snapshot": {},
            "snapshot_etag": None,
            "active_slot": None,
            "active_slot_source": None,
            "map_tools_to_slots": False,
            "tool_slot_map": {},
            "routing_revision": 0,
            "binding": None,
            "outbox": [],
            "last_sync_at": None,
            "last_error": None,
        }

    def get_settings_restricted_paths(self):
        return {
            "never": [
                ["bridge_token"],
                ["snapshot"],
                ["binding"],
                ["outbox"],
            ]
        }

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
            },
            {
                "type": "sidebar",
                "name": "FilamentHub",
                "icon": "fas fa-layer-group",
                "custom_bindings": True,
                "data_bind": "visible: paired",
            },
        ]

    def is_template_autoescaped(self):
        return True

    def on_after_startup(self):
        self._stop_worker.clear()
        self._wake_worker.clear()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="filamenthub-bridge",
            daemon=True,
        )
        self._worker.start()
        self._logger.info("FilamentHub Bridge %s started", PLUGIN_VERSION)

    def on_shutdown(self):
        self._checkpoint_usage("shutdown")
        self._stop_worker.set()
        self._wake_worker.set()
        if self._worker is not None:
            self._worker.join(timeout=3)

    def get_api_commands(self):
        return {
            "pair": ["server_url", "pairing_code"],
            "sync": [],
            "search_spools": ["query", "offset"],
            "assign_spool": ["material_slot_id", "spool_id"],
            "select_slot": ["slot_index"],
            "set_mapping_mode": ["map_tools_to_slots"],
            "set_routing": ["mode", "tool_slot_map"],
            "unpair": [],
        }

    def is_api_adminonly(self):
        return True

    def is_api_protected(self):
        return True

    def on_api_get(self, request):
        return flask.jsonify(self._public_state())

    def on_api_command(self, command, data):
        with self._connection_lock:
            return self._on_api_command_locked(command, data)

    def _on_api_command_locked(self, command, data):
        try:
            extra_state = {}
            if command == "pair":
                self._pair(data["server_url"], data["pairing_code"])
                self._sync_once(force_snapshot=True, retry_blocked=True)
            elif command == "sync":
                self._sync_once(force_snapshot=True, retry_blocked=True)
            elif command == "search_spools":
                extra_state["spool_options"] = self._search_spools(
                    data.get("query"), data.get("offset")
                )
            elif command == "assign_spool":
                self._assign_spool(
                    int(data["material_slot_id"]),
                    self._optional_positive_int(data.get("spool_id")),
                )
            elif command == "select_slot":
                self._select_slot(int(data["slot_index"]))
            elif command == "set_mapping_mode":
                enabled = bool(data["map_tools_to_slots"])
                mapping = self._tool_slot_map()
                if enabled and not mapping:
                    mapping = {slot: slot for slot in self._available_slots()}
                self._save_routing(enabled=enabled, mapping=mapping)
            elif command == "set_routing":
                mode = str(data["mode"] or "").strip().lower()
                if mode not in {"manual", "tools"}:
                    raise ValueError("Routing mode must be manual or tools.")
                self._save_routing(
                    enabled=mode == "tools",
                    mapping=self._parse_tool_slot_map(data["tool_slot_map"]),
                )
            elif command == "unpair":
                self._unpair()
            return flask.jsonify({**self._public_state(), **extra_state})
        except Exception as exc:
            self._logger.warning("Bridge API command failed", exc_info=True)
            state = self._public_state()
            status_code = (
                exc.status_code
                if isinstance(exc, BridgeRequestError)
                and exc.status_code is not None
                and 400 <= exc.status_code < 500
                else 400
                if isinstance(exc, ValueError)
                else 502
            )
            return flask.make_response(
                flask.jsonify(error=str(exc), state=state), status_code
            )

    def on_event(self, event, payload):
        if event == Events.PRINT_STARTED:
            self._begin_print(payload)
        elif event == Events.PRINT_DONE:
            self._finish_print("completed", payload)
        elif event == Events.PRINT_CANCELLED:
            self._finish_print("cancelled", payload)
        elif event == Events.PRINT_FAILED:
            self._finish_print("failed", payload)
        elif event == Events.PRINT_PAUSED:
            self._checkpoint_usage("paused")
        elif event == Events.FILAMENT_CHANGE:
            self._checkpoint_usage("filament_change")
        elif event == Events.DISCONNECTING:
            self._checkpoint_usage("disconnect")

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
            sent_tool = self._tracker.tool_index(cmd, gcode)
            if sent_tool is not None:
                if self._printing and self._settings.get_boolean(
                    ["map_tools_to_slots"]
                ):
                    mapping = self._tool_slot_map()
                    if mapping.get(self._tracker.active_tool) != mapping.get(sent_tool):
                        self._queue_usage_locked(
                            event_type="checkpoint",
                            reason="tool_change",
                        )
                # This is the last standard Tn command OctoPrint wrote to the
                # printer. It seeds a subsequent print, but is not presented as
                # firmware-confirmed hardware state.
                self._selected_tool = sent_tool
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
            selected, consumed = self._tracker.process(
                command=cmd,
                gcode=gcode,
                active_slot=self._manual_slot(),
                map_tools_to_slots=self._settings.get_boolean(["map_tools_to_slots"]),
                available_slots=available,
                tool_slot_map=self._tool_slot_map(),
            )
            if consumed > 0:
                self._logger.debug(
                    "Tracked %.3f mm of extrusion in FilamentHub slot %s",
                    consumed,
                    selected,
                )
        return None

    def _public_state(self):
        snapshot = self._settings.get(["snapshot"])
        outbox_observability = self._outbox_observability()
        retained_outbox_size = outbox_observability["retained"]
        commanded_tool = (
            self._tracker.active_tool
            if self._printing and self._settings.get_boolean(["map_tools_to_slots"])
            else None
        )
        return {
            "paired": bool(self._settings.get(["bridge_token"])),
            "server_url": self._settings.get(["server_url"]),
            "snapshot": snapshot,
            "active_slot": self._active_slot(),
            "manual_slot": self._manual_slot(),
            "map_tools_to_slots": self._settings.get_boolean(["map_tools_to_slots"]),
            "routing_mode": (
                "tools"
                if self._settings.get_boolean(["map_tools_to_slots"])
                else "manual"
            ),
            "tool_slot_map": [
                {"tool_index": tool, "slot_index": slot}
                for tool, slot in sorted(self._tool_slot_map().items())
            ],
            "routing_revision": int(self._settings.get(["routing_revision"]) or 0),
            # ``current_tool`` is retained for older Bridge UIs. OctoPrint only
            # confirms that this Tn command was sent; it does not prove the
            # printer physically activated that tool.
            "current_tool": commanded_tool,
            "commanded_tool": commanded_tool,
            "unmapped_tools": (
                sorted(self._tracker.unmapped_tools) if self._printing else []
            ),
            "printing": self._printing,
            "outbox_size": outbox_observability["count"],
            "current_outbox_size": outbox_observability["current"],
            "retained_outbox_size": retained_outbox_size,
            "blocked_outbox_size": outbox_observability["blocked"],
            "outbox_observability": outbox_observability,
            "last_sync_at": self._settings.get(["last_sync_at"]),
            "last_error": (
                self._settings.get(["last_error"])
                or self._retained_usage_error(retained_outbox_size)
            ),
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

    def _request(
        self,
        method: str,
        path: str,
        payload=None,
        extra_headers=None,
        *,
        server_url: Optional[str] = None,
        include_token: bool = True,
    ):
        with self._lock:
            server_url = server_url or self._settings.get(["server_url"])
            token = self._settings.get(["bridge_token"]) if include_token else None
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
            raise BridgeRequestError(
                f"FilamentHub returned HTTP {exc.code}: {content[:300]}",
                status_code=exc.code,
                retry_after_seconds=_retry_after_seconds(exc.headers),
            ) from exc
        except URLError as exc:
            raise BridgeRequestError(f"Cannot reach FilamentHub: {exc.reason}") from exc

    def _pair(self, server_url: str, pairing_code: str) -> None:
        with self._connection_lock:
            self._pair_locked(server_url, pairing_code)

    def _pair_locked(self, server_url: str, pairing_code: str) -> None:
        normalized_server_url = self._normalize_server_url(server_url)
        normalized_pairing_code = str(pairing_code or "").strip().upper()
        if not normalized_pairing_code:
            raise ValueError("Enter the FilamentHub pairing code.")
        with self._lock:
            if self._printing:
                raise ValueError(
                    gettext(
                        "Wait for the active print to finish before changing the "
                        "FilamentHub connection."
                    )
                )
            previous_binding = self._current_binding()
        instance_id = self._settings.get(["instance_id"]) or str(uuid.uuid4())
        _, _, response = self._request(
            "POST",
            "/pair",
            {
                "pairing_code": normalized_pairing_code,
                "instance_id": instance_id,
                "plugin_version": PLUGIN_VERSION,
                "octoprint_version": self._octoprint_version(),
                "capabilities": CAPABILITIES,
            },
            server_url=normalized_server_url,
            include_token=False,
        )
        if not isinstance(response, dict):
            raise ValueError("FilamentHub returned an invalid pairing response.")
        token = response.get("bridge_token")
        binding = self._binding_for_identity(
            response,
            server_url=normalized_server_url,
            instance_id=instance_id,
        )
        if not isinstance(token, str) or not token:
            raise ValueError("FilamentHub returned an invalid pairing response.")
        if binding is None:
            raise ValueError("FilamentHub returned an invalid printer identity.")
        with self._lock:
            if self._printing:
                raise ValueError(
                    gettext(
                        "Pairing completed remotely while a print started. Local "
                        "settings and pending usage were retained, but remote "
                        "credentials may have changed. Wait for the print to finish, "
                        "verify the selected printer, then connect again with a new "
                        "pairing code."
                    )
                )
            self._settings.set(["server_url"], normalized_server_url)
            self._settings.set(["instance_id"], instance_id)
            self._settings.set(["bridge_token"], token)
            self._settings.set(["binding"], binding)
            if previous_binding != binding:
                self._settings.set(["snapshot"], {})
                self._settings.set(["snapshot_etag"], None)
                self._settings.set(["active_slot"], None)
                self._settings.set(["active_slot_source"], None)
                self._settings.set(["map_tools_to_slots"], False)
                self._settings.set(["tool_slot_map"], {})
                self._settings.set(["routing_revision"], 0)
            self._settings.set(
                ["last_error"], self._retained_usage_error(self._retained_outbox_size())
            )
            self._settings.save()

    def _unpair(self) -> None:
        with self._connection_lock:
            self._unpair_locked()

    def _unpair_locked(self) -> None:
        self._request("DELETE", "/connection")
        with self._lock:
            self._settings.set(["bridge_token"], None)
            self._settings.set(["binding"], None)
            self._settings.set(["snapshot"], {})
            self._settings.set(["snapshot_etag"], None)
            self._settings.set(["active_slot"], None)
            self._settings.set(["active_slot_source"], None)
            self._settings.set(["map_tools_to_slots"], False)
            self._settings.set(["tool_slot_map"], {})
            self._settings.set(["routing_revision"], 0)
            self._settings.set(["last_sync_at"], None)
            self._settings.set(
                ["last_error"], self._retained_usage_error(self._retained_outbox_size())
            )
            self._settings.save()

    @staticmethod
    def _service_origin(server_url: str) -> Optional[str]:
        try:
            parsed = urlparse(server_url)
            hostname = (parsed.hostname or "").lower()
            port = parsed.port
        except (TypeError, ValueError):
            return None
        if parsed.scheme not in {"http", "https"} or not hostname:
            return None
        rendered_host = f"[{hostname}]" if ":" in hostname else hostname
        if port is not None and not (
            (parsed.scheme == "https" and port == 443)
            or (parsed.scheme == "http" and port == 80)
        ):
            rendered_host = f"{rendered_host}:{port}"
        return f"{parsed.scheme.lower()}://{rendered_host}"

    @classmethod
    def _binding_for_identity(
        cls,
        payload,
        *,
        server_url: str,
        instance_id: str,
    ) -> Optional[dict]:
        if not isinstance(payload, dict):
            return None
        try:
            physical_printer_id = int(payload["physical_printer_id"])
            material_system_id = int(payload["material_system_id"])
        except (KeyError, TypeError, ValueError):
            return None
        service_origin = cls._service_origin(server_url)
        normalized_instance_id = str(instance_id or "").strip()
        if (
            physical_printer_id < 1
            or material_system_id < 1
            or service_origin is None
            or not normalized_instance_id
        ):
            return None
        return {
            "service_origin": service_origin,
            "instance_id": normalized_instance_id,
            "physical_printer_id": physical_printer_id,
            "material_system_id": material_system_id,
        }

    @classmethod
    def _normalize_binding(cls, payload) -> Optional[dict]:
        if not isinstance(payload, dict):
            return None
        return cls._binding_for_identity(
            payload,
            server_url=str(payload.get("service_origin") or ""),
            instance_id=str(payload.get("instance_id") or ""),
        )

    def _current_binding(self) -> Optional[dict]:
        if not self._settings.get(["bridge_token"]):
            return None
        server_url = self._settings.get(["server_url"]) or ""
        instance_id = str(self._settings.get(["instance_id"]) or "").strip()
        stored_payload = self._settings.get(["binding"])
        if stored_payload is not None:
            stored = self._normalize_binding(stored_payload)
            if (
                stored is None
                or stored["service_origin"] != self._service_origin(server_url)
                or stored["instance_id"] != instance_id
            ):
                return None
            return stored
        return self._binding_for_identity(
            self._settings.get(["snapshot"]) or {},
            server_url=server_url,
            instance_id=instance_id,
        )

    @classmethod
    def _event_matches_binding(cls, event: dict, binding: Optional[dict]) -> bool:
        return binding is not None and cls._normalize_binding(event.get("_binding")) == binding

    def _retained_outbox_size(self) -> int:
        return self._outbox_observability()["retained"]

    def _outbox_observability(self) -> dict:
        outbox = list(self._settings.get(["outbox"]) or [])
        binding = self._current_binding()
        current = [
            event for event in outbox if self._event_matches_binding(event, binding)
        ]
        retained = len(outbox) - len(current)
        blocked = sum(
            1
            for event in current
            if _delivery_metadata(event).get("state") == "blocked"
        )
        try:
            serialized_bytes = len(
                json.dumps(outbox, separators=(",", ":")).encode("utf-8")
            )
        except (TypeError, ValueError):
            serialized_bytes = 0
        now = _utc_now()
        queued_times = [
            _parse_utc_datetime(_delivery_metadata(event, now=now)["queued_at"])
            for event in outbox
        ]
        valid_queued_times = [value for value in queued_times if value is not None]
        oldest_age_seconds = (
            max(0, int((now - min(valid_queued_times)).total_seconds()))
            if valid_queued_times
            else None
        )
        warning_reasons = []
        if len(outbox) >= OUTBOX_WARNING_COUNT:
            warning_reasons.append("count")
        if serialized_bytes >= OUTBOX_WARNING_BYTES:
            warning_reasons.append("bytes")
        if (
            oldest_age_seconds is not None
            and oldest_age_seconds >= OUTBOX_WARNING_AGE_SECONDS
        ):
            warning_reasons.append("age")
        return {
            "count": len(outbox),
            "bytes": serialized_bytes,
            "oldest_age_seconds": oldest_age_seconds,
            "current": len(current),
            "retained": retained,
            "blocked": blocked,
            "warning": bool(warning_reasons),
            "warning_reasons": warning_reasons,
            "soft_limits": {
                "count": OUTBOX_WARNING_COUNT,
                "bytes": OUTBOX_WARNING_BYTES,
                "age_seconds": OUTBOX_WARNING_AGE_SECONDS,
            },
        }

    @staticmethod
    def _retained_usage_error(count: int) -> Optional[str]:
        if count < 1:
            return None
        return gettext(
            "Retained %(count)d pending usage report(s) for another or unknown "
            "FilamentHub printer connection. They will not be sent to the current "
            "connection. Reports with a recorded identity resume only after the "
            "original Bridge instance and printer connection are restored; legacy "
            "reports require manual recovery.",
            count=count,
        )

    def _available_slots(self) -> Set[int]:
        snapshot = self._settings.get(["snapshot"]) or {}
        return {int(slot["index"]) for slot in snapshot.get("slots", [])}

    def _snapshot_slot(self, material_slot_id: int) -> dict:
        snapshot = self._settings.get(["snapshot"]) or {}
        for slot in snapshot.get("slots", []):
            if int(slot.get("material_slot_id", 0)) == material_slot_id:
                return slot
        raise ValueError(
            "The selected slot is not present in the FilamentHub snapshot."
        )

    @staticmethod
    def _optional_positive_int(value) -> Optional[int]:
        if value is None or value == "":
            return None
        parsed = int(value)
        if parsed < 1:
            raise ValueError("Spool identity must be a positive whole number.")
        return parsed

    def _search_spools(self, query, offset) -> dict:
        normalized_query = str(query or "").strip()
        normalized_offset = max(int(offset or 0), 0)
        _, _, response = self._request(
            "GET",
            "/spools?"
            + urlencode(
                {
                    "query": normalized_query,
                    "limit": 25,
                    "offset": normalized_offset,
                }
            ),
        )
        if not isinstance(response, dict) or not isinstance(
            response.get("items"), list
        ):
            raise ValueError("FilamentHub returned an invalid spool list.")
        return response

    def _assign_spool(self, material_slot_id: int, spool_id: Optional[int]) -> None:
        slot = self._snapshot_slot(material_slot_id)
        current_spool = slot.get("spool")
        payload = {
            "expected_revision": int(slot.get("assignment_revision", 0)),
            "expected_spool_id": (
                int(current_spool["id"]) if current_spool is not None else None
            ),
            "spool_id": spool_id,
        }
        try:
            _, _, snapshot = self._request(
                "PATCH", f"/material-slots/{material_slot_id}", payload
            )
        except BridgeRequestError as exc:
            if exc.status_code == 409:
                refreshed = False
                try:
                    self._sync_snapshot()
                    self._settings.save()
                    refreshed = True
                except Exception:
                    self._logger.warning(
                        "Could not refresh the snapshot after an assignment conflict",
                        exc_info=True,
                    )
                raise BridgeRequestError(
                    (
                        "This slot or spool location changed in FilamentHub. "
                        "The latest state was loaded; review it and try again."
                        if refreshed
                        else "This slot or spool location changed in FilamentHub. "
                        "Synchronize the Bridge, then review it and try again."
                    ),
                    status_code=409,
                ) from exc
            raise
        if not isinstance(snapshot, dict):
            raise ValueError("FilamentHub returned an invalid assignment snapshot.")
        revision = snapshot.get("revision")
        if not isinstance(revision, str) or not revision:
            raise ValueError("FilamentHub returned an invalid assignment revision.")
        self._apply_snapshot(snapshot, f'"{revision}"')
        self._settings.set(["last_sync_at"], datetime.now(timezone.utc).isoformat())
        self._settings.set(["last_error"], None)
        self._settings.save()

    def _manual_slot(self) -> Optional[int]:
        value = self._settings.get(["active_slot"])
        return int(value) if value is not None else None

    def _active_slot(self) -> Optional[int]:
        if self._settings.get_boolean(["map_tools_to_slots"]):
            if not self._printing:
                return None
            mapped = self._tool_slot_map().get(self._tracker.active_tool)
            return mapped if mapped in self._available_slots() else None
        return self._manual_slot()

    def _select_slot(self, slot_index: int) -> None:
        if self._settings.get_boolean(["map_tools_to_slots"]):
            raise ValueError(
                "Manual slot selection is unavailable while G-code tool routing is enabled."
            )
        if slot_index not in self._available_slots():
            raise ValueError(
                "The selected slot is not present in the FilamentHub snapshot."
            )
        with self._lock:
            if self._printing and self._manual_slot() != slot_index:
                self._queue_usage_locked(
                    event_type="checkpoint",
                    reason="slot_change",
                )
            self._settings.set(["active_slot"], slot_index)
            self._settings.set(["active_slot_source"], "manual_declaration")
            self._settings.save()
        self._wake_worker.set()

    @staticmethod
    def _parse_tool_slot_map(value) -> Dict[int, int]:
        if not isinstance(value, list):
            raise ValueError("Tool mappings must be a list.")
        mapping: Dict[int, int] = {}
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("Each tool mapping must contain a tool and a slot.")
            try:
                tool_index = int(item["tool_index"])
                slot_index = int(item["slot_index"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Tool and slot indices must be whole numbers."
                ) from exc
            if not 0 <= tool_index <= 1023 or not 0 <= slot_index <= 1023:
                raise ValueError("Tool and slot indices must be between 0 and 1023.")
            if tool_index in mapping:
                raise ValueError(f"T{tool_index} is mapped more than once.")
            mapping[tool_index] = slot_index
        return mapping

    def _tool_slot_map(self) -> Dict[int, int]:
        raw = self._settings.get(["tool_slot_map"]) or {}
        if not raw and self._settings.get_boolean(["map_tools_to_slots"]):
            # Versions before explicit routing stored only the boolean identity
            # mode. Preserve that configuration during an in-place upgrade.
            return {slot: slot for slot in self._available_slots()}
        if not isinstance(raw, dict):
            return {}
        mapping: Dict[int, int] = {}
        for raw_tool, raw_slot in raw.items():
            try:
                tool_index = int(raw_tool)
                slot_index = int(raw_slot)
            except (TypeError, ValueError):
                continue
            if 0 <= tool_index <= 1023 and 0 <= slot_index <= 1023:
                mapping[tool_index] = slot_index
        return mapping

    def _save_routing(self, *, enabled: bool, mapping: Dict[int, int]) -> None:
        missing_slots = sorted(set(mapping.values()) - self._available_slots())
        if missing_slots:
            labels = ", ".join(str(index + 1) for index in missing_slots)
            raise ValueError(f"Unknown FilamentHub slot(s): {labels}.")
        if enabled and not mapping:
            raise ValueError(
                "Map at least one G-code tool before enabling tool routing."
            )
        if self._settings.get(["bridge_token"]):
            _, _, response = self._request(
                "PUT",
                "/routing",
                {
                    "mode": "tools" if enabled else "manual",
                    "tool_slot_map": [
                        {"tool_index": tool, "slot_index": slot}
                        for tool, slot in sorted(mapping.items())
                    ],
                    "expected_revision": int(
                        self._settings.get(["routing_revision"]) or 0
                    ),
                },
            )
            self._apply_server_routing(response)
            self._wake_worker.set()
            return
        self._settings.set_boolean(["map_tools_to_slots"], enabled)
        self._settings.set(
            ["tool_slot_map"],
            {str(tool): slot for tool, slot in sorted(mapping.items())},
        )
        self._settings.save()
        self._wake_worker.set()

    def _apply_server_routing(self, routing) -> None:
        if not isinstance(routing, dict):
            return
        mode = str(routing.get("mode") or "").strip().lower()
        if mode not in {"manual", "tools"}:
            raise ValueError("FilamentHub returned an invalid routing mode.")
        mapping = self._parse_tool_slot_map(routing.get("tool_slot_map"))
        if mode == "tools" and not mapping:
            raise ValueError("FilamentHub returned an empty tool routing map.")
        revision = int(routing.get("revision", 0))
        if revision < 0:
            raise ValueError("FilamentHub returned an invalid routing revision.")
        enabled = mode == "tools"
        with self._lock:
            if (
                self._settings.get_boolean(["map_tools_to_slots"]) == enabled
                and self._tool_slot_map() == mapping
                and int(self._settings.get(["routing_revision"]) or 0) == revision
            ):
                return
            previous_active_slot = self._active_slot()
            next_active_slot = (
                mapping.get(self._tracker.active_tool)
                if enabled and self._printing
                else self._manual_slot()
                if not enabled
                else None
            )
            if self._printing and previous_active_slot != next_active_slot:
                self._queue_usage_locked(
                    event_type="checkpoint",
                    reason="slot_change",
                )
            self._settings.set_boolean(["map_tools_to_slots"], enabled)
            self._settings.set(
                ["tool_slot_map"],
                {str(tool): slot for tool, slot in sorted(mapping.items())},
            )
            self._settings.set(["routing_revision"], revision)
            self._settings.save()

    def _snapshot_spools(self) -> Dict[int, int]:
        return self._spools_from_snapshot(self._settings.get(["snapshot"]) or {})

    @staticmethod
    def _spools_from_snapshot(snapshot: dict) -> Dict[int, int]:
        result = {}
        for slot in snapshot.get("slots", []):
            spool = slot.get("spool")
            if spool:
                result[int(slot["index"])] = int(spool["id"])
        return result

    @staticmethod
    def _usage_routes_from_snapshot(snapshot: dict) -> Dict[int, dict]:
        routes = {}
        for slot in snapshot.get("slots", []):
            spool = slot.get("spool")
            if not spool:
                continue
            route = {"spool_id": int(spool["id"])}
            for key in ("usage_route_proof", "assignment_revision"):
                if slot.get(key) is not None:
                    route[key] = slot[key]
            routes[int(slot["index"])] = route
        return routes

    def _begin_print(self, payload) -> None:
        with self._lock:
            # OctoPrint dispatches events asynchronously. On very short files the
            # sent-G-code hook can initialize tracking before PrintStarted arrives.
            # Never reset material already observed for the same active print.
            if self._printing:
                return
            self._tracker.reset()
            if self._selected_tool is not None:
                self._tracker.active_tool = self._selected_tool
            self._printing = True
            self._job_id = str(uuid.uuid4())
            self._job_file = payload.get("name") or payload.get("path")
            self._job_started_at = datetime.now(timezone.utc).isoformat()
            self._job_routes = self._usage_routes_from_snapshot(
                self._settings.get(["snapshot"]) or {}
            )
            self._job_binding = self._current_binding()
            self._usage_event_sequence = 0
            self._last_usage_checkpoint_monotonic = time.monotonic()
            available = self._available_slots()
            manual_slot = self._manual_slot()
            if (
                not self._settings.get_boolean(["map_tools_to_slots"])
                and manual_slot not in available
            ):
                assigned = sorted(self._job_routes)
                self._settings.set(["active_slot"], assigned[0] if assigned else None)
                self._settings.set(["active_slot_source"], None)
            self._logger.info(
                "Tracking print %s with %d assigned FilamentHub spool(s)",
                self._job_file or self._job_id,
                len(self._job_routes),
            )

    def _checkpoint_usage(self, reason: str) -> None:
        with self._lock:
            if not self._printing or self._job_id is None:
                return
            self._queue_usage_locked(event_type="checkpoint", reason=reason)

    @staticmethod
    def _usage_item_key(item: dict) -> tuple[int, int]:
        return int(item["slot_index"]), int(item["spool_id"])

    def _queue_usage_locked(
        self,
        *,
        event_type: str,
        reason: str,
        outcome: Optional[str] = None,
        duration_s: Optional[float] = None,
    ) -> int:
        if not self._printing or self._job_id is None:
            return 0

        usage = self._tracker.drain_usage()
        items = []
        unattributed_slots = []
        tool_slot_map = (
            self._tool_slot_map()
            if self._settings.get_boolean(["map_tools_to_slots"])
            else {}
        )
        for slot_index, used_length in sorted(usage.items()):
            route = self._job_routes.get(slot_index)
            if used_length <= 0:
                continue
            if route is None:
                unattributed_slots.append(slot_index)
                continue
            items.append(
                {
                    "slot_index": slot_index,
                    "spool_id": route["spool_id"],
                    "used_length_mm": used_length,
                    "evidence": (
                        "route_proof"
                        if route.get("usage_route_proof") is not None
                        else "current_assignment"
                    ),
                }
            )
            if route.get("usage_route_proof") is not None:
                items[-1]["usage_route_proof"] = route["usage_route_proof"]
            matching_tools = [
                tool_index
                for tool_index, mapped_slot in tool_slot_map.items()
                if mapped_slot == slot_index
            ]
            if len(matching_tools) == 1:
                items[-1]["tool_index"] = matching_tools[0]
        if unattributed_slots:
            self._logger.warning(
                "Skipped unattributed usage in FilamentHub slot(s): %s",
                ", ".join(str(slot + 1) for slot in unattributed_slots),
            )

        outbox = list(self._settings.get(["outbox"]) or [])
        observed_at = datetime.now(timezone.utc).isoformat()
        if event_type == "checkpoint":
            pending = next(
                (
                    event
                    for event in reversed(outbox)
                    if event.get("event_type") == "checkpoint"
                    and event.get("job_id") == self._job_id
                    and not event.get("_sealed", False)
                    and event.get("_binding") == self._job_binding
                    and all(
                        item.get("spool_id")
                        == self._job_routes.get(item.get("slot_index"), {}).get("spool_id")
                        and item.get("usage_route_proof")
                        == self._job_routes.get(item.get("slot_index"), {}).get(
                            "usage_route_proof"
                        )
                        for item in event.get("items", [])
                    )
                ),
                None,
            )
            if pending is not None and (items or pending.get("items")):
                merged = {
                    self._usage_item_key(item): dict(item)
                    for item in pending.get("items", [])
                }
                for item in items:
                    key = self._usage_item_key(item)
                    if key in merged:
                        merged[key]["used_length_mm"] += item["used_length_mm"]
                    else:
                        merged[key] = dict(item)
                if len(merged) <= 256:
                    pending["items"] = [merged[key] for key in sorted(merged)]
                    reasons = list(pending.get("reasons") or [])
                    if reason not in reasons:
                        reasons.append(reason)
                    pending["reasons"] = reasons
                    pending["observed_at"] = observed_at
                    pending["_delivery"] = _delivery_metadata(pending)
                    self._settings.set(["outbox"], outbox)
                    self._settings.save()
                    if items:
                        self._last_usage_checkpoint_monotonic = time.monotonic()
                    return len(items)
                pending["_sealed"] = True
            if not items:
                return 0
            self._usage_event_sequence += 1
            event = {
                "contract_version": 2,
                "event_id": (f"{self._job_id}:checkpoint:{self._usage_event_sequence}"),
                "job_id": self._job_id,
                "segment_sequence": self._usage_event_sequence,
                "event_type": "checkpoint",
                "reasons": [reason],
                "file_name": self._job_file,
                "started_at": self._job_started_at,
                "observed_at": observed_at,
                "duration_s": None,
                "items": items,
                "_binding": self._job_binding,
            }
        elif event_type == "terminal":
            self._usage_event_sequence += 1
            event = {
                "contract_version": 2,
                "event_id": f"{self._job_id}:terminal",
                "job_id": self._job_id,
                "segment_sequence": self._usage_event_sequence,
                "event_type": "terminal",
                "reasons": [reason],
                "outcome": outcome,
                "file_name": self._job_file,
                "started_at": self._job_started_at,
                "observed_at": observed_at,
                "duration_s": duration_s,
                "items": items,
                "_binding": self._job_binding,
            }
        else:
            raise ValueError(f"Unsupported usage event type: {event_type}")

        event["_delivery"] = _delivery_metadata(event)
        outbox.append(event)
        self._settings.set(["outbox"], outbox)
        self._settings.save()
        if items:
            self._last_usage_checkpoint_monotonic = time.monotonic()
        return len(items)

    def _finish_print(self, outcome: str, payload) -> None:
        with self._lock:
            if not self._printing or self._job_id is None:
                return
            item_count = self._queue_usage_locked(
                event_type="terminal",
                reason="terminal",
                outcome=outcome,
                duration_s=payload.get("time") if payload else None,
            )
            self._logger.info(
                "Finished tracking print %s: outcome=%s, usage_items=%d",
                self._job_file or self._job_id,
                outcome,
                item_count,
            )
            self._printing = False
            self._job_id = None
            self._job_file = None
            self._job_started_at = None
            self._job_routes = {}
            self._job_binding = None
            self._last_usage_checkpoint_monotonic = None
        self._wake_worker.set()

    def _apply_snapshot(self, payload: dict, etag: Optional[str]) -> None:
        with self._lock:
            binding = self._binding_for_identity(
                payload,
                server_url=self._settings.get(["server_url"]) or "",
                instance_id=self._settings.get(["instance_id"]) or "",
            )
            if binding is not None:
                self._settings.set(["binding"], binding)
            next_job_routes = self._usage_routes_from_snapshot(payload)
            changed_slots = {
                slot_index
                for slot_index in set(self._job_routes) | set(next_job_routes)
                if self._job_routes.get(slot_index) != next_job_routes.get(slot_index)
            }
            if self._printing and changed_slots.intersection(
                self._tracker.used_length_by_slot
            ):
                self._queue_usage_locked(
                    event_type="checkpoint",
                    reason="spool_change",
                )
            if self._printing and changed_slots:
                outbox = list(self._settings.get(["outbox"]) or [])
                for event in outbox:
                    if event.get("job_id") == self._job_id:
                        event["_sealed"] = True
                self._settings.set(["outbox"], outbox)
                self._settings.save()
            self._settings.set(["snapshot"], payload)
            self._settings.set(["snapshot_etag"], etag)
            if self._printing:
                self._job_routes = next_job_routes
            available = self._available_slots()
            manual_slot = self._manual_slot()
            if manual_slot not in available:
                assigned = sorted(self._snapshot_spools())
                fallback = (
                    assigned[0] if assigned else (min(available) if available else None)
                )
                self._settings.set(["active_slot"], fallback)
                self._settings.set(["active_slot_source"], None)

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
            self._apply_snapshot(payload, response_headers.get("ETag"))

    def _send_heartbeat(self) -> None:
        tool_routing = self._settings.get_boolean(["map_tools_to_slots"])
        reported_slot_index = (
            self._active_slot()
            if not tool_routing or self._selected_tool is not None
            else None
        )
        reported_slot_source = None
        if reported_slot_index is not None:
            if tool_routing and self._selected_tool is not None:
                reported_slot_source = "tool_command"
            elif self._settings.get(["active_slot_source"]) == "manual_declaration":
                reported_slot_source = "manual_declaration"
        _, _, response = self._request(
            "POST",
            "/heartbeat",
            {
                "instance_id": self._settings.get(["instance_id"]),
                "plugin_version": PLUGIN_VERSION,
                "octoprint_version": self._octoprint_version(),
                "capabilities": CAPABILITIES,
                "reported_slot_index": reported_slot_index,
                "reported_slot_source": reported_slot_source,
                "routing_mode": (
                    "tools"
                    if self._settings.get_boolean(["map_tools_to_slots"])
                    else "manual"
                ),
                "tool_slot_map": [
                    {"tool_index": tool, "slot_index": slot}
                    for tool, slot in sorted(self._tool_slot_map().items())
                ],
                "routing_revision": int(self._settings.get(["routing_revision"]) or 0),
            },
        )
        if isinstance(response, dict):
            self._apply_server_routing(response.get("routing"))

    def _record_delivery_failure(
        self,
        event: dict,
        binding: dict,
        exc: Exception,
        *,
        blocked: bool,
    ) -> float:
        now = _utc_now()
        retry_after_seconds = getattr(exc, "retry_after_seconds", None)
        with self._lock:
            current = list(self._settings.get(["outbox"]) or [])
            for index, pending in enumerate(current):
                if (
                    pending.get("event_id") == event.get("event_id")
                    and pending.get("_sealed", False)
                    and self._normalize_binding(pending.get("_binding")) == binding
                ):
                    pending = dict(pending)
                    metadata = _delivery_metadata(pending, now=now)
                    attempt_count = min(
                        metadata["attempt_count"] + 1,
                        OUTBOX_DELIVERY_ATTEMPT_MAX,
                    )
                    delay_seconds = (
                        RETRY_MAX_SECONDS
                        if blocked
                        else _retry_delay(attempt_count, retry_after_seconds)
                    )
                    metadata.update(
                        {
                            "state": "blocked" if blocked else "pending",
                            "attempt_count": attempt_count,
                            "last_attempt_at": now.isoformat(),
                            "next_attempt_at": (
                                None
                                if blocked
                                else (now + timedelta(seconds=delay_seconds)).isoformat()
                            ),
                            "last_status": getattr(exc, "status_code", None),
                            "last_error": str(exc)[:OUTBOX_DELIVERY_ERROR_MAX_LENGTH],
                        }
                    )
                    pending["_delivery"] = _delivery_metadata(pending, now=now) | metadata
                    current[index] = pending
                    self._settings.set(["outbox"], current)
                    self._settings.save()
                    return delay_seconds
        return RETRY_MAX_SECONDS if blocked else RETRY_INITIAL_SECONDS

    def _flush_outbox(
        self,
        *,
        retry_blocked: bool = False,
        respect_retry_schedule: bool = False,
    ) -> int:
        with self._connection_lock:
            return self._flush_outbox_locked(
                retry_blocked=retry_blocked,
                respect_retry_schedule=respect_retry_schedule,
            )

    def _flush_outbox_locked(
        self,
        *,
        retry_blocked: bool = False,
        respect_retry_schedule: bool = False,
    ) -> int:
        while True:
            with self._lock:
                outbox = list(self._settings.get(["outbox"]) or [])
                binding = self._current_binding()
                event_index = next(
                    (
                        index
                        for index, candidate in enumerate(outbox)
                        if self._event_matches_binding(candidate, binding)
                    ),
                    None,
                )
                if event_index is None:
                    return len(outbox)
                event = dict(outbox[event_index])
                metadata = _delivery_metadata(event)
                if metadata["state"] == "blocked" and not retry_blocked:
                    raise OutboxDeliveryBlockedError(
                        metadata["last_error"]
                        or "A queued usage event is blocked and needs attention.",
                        status_code=metadata["last_status"],
                        retry_after_seconds=RETRY_MAX_SECONDS,
                    )
                if metadata["state"] == "blocked":
                    metadata["state"] = "pending"
                    metadata["next_attempt_at"] = None
                retry_at = _parse_utc_datetime(metadata["next_attempt_at"])
                now = _utc_now()
                if (
                    respect_retry_schedule
                    and retry_at is not None
                    and retry_at > now
                ):
                    remaining = min(
                        max((retry_at - now).total_seconds(), 0.0),
                        RETRY_MAX_SECONDS,
                    )
                    raise OutboxDeliveryDeferredError(
                        "A queued usage event is waiting for its retry deadline.",
                        retry_after_seconds=remaining,
                    )
                if (
                    not event.get("_sealed", False)
                    or event.get("_delivery") != metadata
                ):
                    event["_sealed"] = True
                    event["_delivery"] = metadata
                    outbox[event_index] = event
                    self._settings.set(["outbox"], outbox)
                    self._settings.save()
                request_payload = {
                    key: value
                    for key, value in event.items()
                    if not key.startswith("_")
                }

            # Never hold the print-tracking lock during network I/O. Once FH
            # acknowledges the event, remove that exact event from the latest
            # outbox value so a terminal event appended concurrently survives.
            try:
                _, _, response = self._request("POST", "/usage", request_payload)
            except Exception as exc:
                blocked = not _is_retryable_delivery_error(exc)
                delay_seconds = self._record_delivery_failure(
                    event,
                    binding,
                    exc,
                    blocked=blocked,
                )
                if isinstance(exc, BridgeRequestError):
                    exc.retry_after_seconds = max(
                        exc.retry_after_seconds or 0.0,
                        delay_seconds,
                    )
                raise
            if not isinstance(response, dict) or response.get("accepted") is not True:
                exc = OutboxDeliveryBlockedError(
                    "FilamentHub returned an invalid usage acknowledgement.",
                    retry_after_seconds=RETRY_MAX_SECONDS,
                )
                self._record_delivery_failure(event, binding, exc, blocked=True)
                raise exc
            with self._lock:
                current = list(self._settings.get(["outbox"]) or [])
                for index, pending in enumerate(current):
                    if (
                        pending.get("event_id") == event.get("event_id")
                        and pending.get("_sealed", False)
                        and self._normalize_binding(pending.get("_binding"))
                        == binding
                    ):
                        current.pop(index)
                        self._settings.set(["outbox"], current)
                        self._settings.save()
                        break

    def _sync_once(
        self,
        *,
        force_snapshot: bool = False,
        retry_blocked: bool = False,
    ) -> bool:
        with self._connection_lock:
            return self._sync_once_locked(
                force_snapshot=force_snapshot,
                retry_blocked=retry_blocked,
            )

    def _sync_once_locked(
        self,
        *,
        force_snapshot: bool = False,
        retry_blocked: bool = False,
    ) -> bool:
        if not self._settings.get(["bridge_token"]):
            return True
        self._last_retry_after_seconds = None
        errors = []
        now_monotonic = time.monotonic()
        try:
            with self._lock:
                if (
                    self._printing
                    and self._last_usage_checkpoint_monotonic is not None
                    and now_monotonic - self._last_usage_checkpoint_monotonic
                    >= USAGE_CHECKPOINT_INTERVAL_SECONDS
                ):
                    self._queue_usage_locked(
                        event_type="checkpoint",
                        reason="periodic",
                    )
        except Exception as exc:
            errors.append(exc)
            self._logger.warning("Usage checkpoint failed", exc_info=True)
        try:
            if (
                force_snapshot
                or now_monotonic - self._last_snapshot_monotonic
                >= SNAPSHOT_INTERVAL_SECONDS
            ):
                self._sync_snapshot()
                self._last_snapshot_monotonic = now_monotonic
        except Exception as exc:
            errors.append(exc)
            self._logger.warning("Snapshot synchronization failed", exc_info=True)
        try:
            self._send_heartbeat()
        except Exception as exc:
            errors.append(exc)
            self._logger.warning("Heartbeat failed", exc_info=True)
        try:
            retained_outbox_size = self._flush_outbox(
                retry_blocked=retry_blocked,
                respect_retry_schedule=not retry_blocked,
            )
        except Exception as exc:
            errors.append(exc)
            retained_outbox_size = self._retained_outbox_size()
            self._logger.warning("Usage outbox delivery failed", exc_info=True)

        if errors:
            retry_delays = [
                getattr(exc, "retry_after_seconds", None) for exc in errors
            ]
            self._last_retry_after_seconds = max(
                (delay for delay in retry_delays if delay is not None),
                default=None,
            )
            self._settings.set(
                ["last_error"],
                " | ".join(dict.fromkeys(str(exc) for exc in errors)),
            )
            success = False
        else:
            self._settings.set(["last_sync_at"], datetime.now(timezone.utc).isoformat())
            self._settings.set(
                ["last_error"], self._retained_usage_error(retained_outbox_size)
            )
            success = True
        self._settings.save()
        plugin_manager = getattr(self, "_plugin_manager", None)
        identifier = getattr(self, "_identifier", None)
        if plugin_manager is not None and identifier is not None:
            self._plugin_manager.send_plugin_message(
                self._identifier, self._public_state()
            )
        return success

    def _worker_loop(self) -> None:
        # A host update can restart many OctoPrint instances at once. Spread
        # their first automatic contact over two minutes; explicit actions
        # still call _sync_once directly or wake the worker immediately.
        delay_seconds = random.uniform(0.0, STARTUP_JITTER_MAX_SECONDS)
        failure_count = 0
        while not self._stop_worker.is_set():
            self._wake_worker.wait(timeout=delay_seconds)
            self._wake_worker.clear()
            if self._stop_worker.is_set():
                return
            if self._sync_once():
                failure_count = 0
                delay_seconds = _jittered_delay(HEARTBEAT_INTERVAL_SECONDS)
            else:
                failure_count += 1
                delay_seconds = _retry_delay(
                    failure_count,
                    self._last_retry_after_seconds,
                )


__plugin_name__ = "FilamentHub Bridge"
__plugin_version__ = PLUGIN_VERSION
__plugin_description__ = "Native outbound material bridge for FilamentHub"
__plugin_pythoncompat__ = ">=3.9,<4"
__plugin_implementation__ = FilamentHubBridgePlugin()
__plugin_hooks__ = {
    "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.on_gcode_sent,
}
