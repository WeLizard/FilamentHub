"""Read-only Moonraker and Happy Hare observation provider."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

from ..errors import HttpRequestError, ProviderUnavailable
from ..http import JsonHttpClient
from .base import ProviderSnapshot

HAPPY_HARE_FIELDS = [
    "num_gates",
    "gate_status",
    "gate_material",
    "gate_color",
    "gate_spool_id",
    "has_bypass",
    "gate",
    "tool",
    "filament_pos",
    "spoolman_support",
]
COLOR_PATTERN = re.compile(r"^[0-9A-F]{6}$")
BYPASS_PROVIDER_INDEX = 1023


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _printer_state(value: Any) -> str:
    state = str(value or "").strip().lower()
    return {
        "standby": "idle",
        "ready": "idle",
        "printing": "printing",
        "paused": "paused",
        "complete": "finished",
        "cancelled": "failed",
        "error": "failed",
    }.get(state, "unknown")


class MoonrakerProvider:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None,
        material_provider: str,
        timeout: float,
        http_client: JsonHttpClient | None = None,
        filamenthub_url: str = "https://filamenthub.ru",
    ) -> None:
        headers = {"X-Api-Key": api_key} if api_key else None
        self.http = http_client or JsonHttpClient(
            base_url,
            allow_http=True,
            timeout=timeout,
            default_headers=headers,
        )
        self.material_provider = material_provider
        self.filamenthub_url = filamenthub_url
        self._capabilities = ["read", "presence", "consumption"]
        self._identity_checked_at = float("-inf")
        self._identity: tuple[str, str] | None = None

    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    def observe(self) -> ProviderSnapshot:
        objects: dict[str, list[str]] = {
            "print_stats": [
                "state",
                "filename",
                "filament_used",
                "total_duration",
                "print_duration",
            ],
            "display_status": ["progress"],
            "extruder": ["temperature", "target"],
            "heater_bed": ["temperature", "target"],
        }
        if self.material_provider == "happy_hare":
            objects["mmu"] = HAPPY_HARE_FIELDS
        try:
            _, decoded, _ = self.http.request(
                "POST",
                "/printer/objects/query",
                payload={"objects": objects},
            )
        except HttpRequestError as exc:
            raise ProviderUnavailable("Moonraker object query failed") from exc
        status = self._status_map(decoded)
        printer = self._printer_snapshot(status)
        usage = self._usage_snapshot(status)
        slots: list[dict[str, Any]] = []
        topology_complete = False
        inventory_key_digest = self._inventory_key_digest()
        if self.material_provider == "happy_hare":
            mmu = status.get("mmu")
            if not isinstance(mmu, dict):
                raise ProviderUnavailable("Happy Hare object 'mmu' is unavailable")
            slots = self._happy_hare_slots(mmu)
            topology_complete = True
            if self._native_spoolman_configured or mmu.get("spoolman_support") != "off":
                # Moonraker's native Spoolman component owns usage for this feed.
                # Running Edge and Orca alongside it must not debit the spool twice.
                usage = None
                self._capabilities = ["read", "presence", "spool_identity"]
            else:
                self._capabilities = ["read", "presence", "spool_identity", "consumption"]
        else:
            self._capabilities = ["read", "presence"]
            if self._native_spoolman_configured:
                usage = None
            else:
                self._capabilities.append("consumption")
        return ProviderSnapshot(
            printer=printer,
            slots=slots,
            slot_topology_complete=topology_complete,
            capabilities=self.capabilities(),
            usage=usage,
            inventory_key_digest=inventory_key_digest,
            device_identity=self._device_identity(),
        )

    def _device_identity(self) -> tuple[str, str] | None:
        if time.monotonic() - self._identity_checked_at < 60:
            return self._identity
        self._identity_checked_at = time.monotonic()
        self._identity = None
        try:
            _, decoded, _ = self.http.request(
                "GET",
                "/server/database/item?namespace=moonraker&key=instance_id",
            )
            value = decoded.get("result", {}).get("value")
            self._identity = ("moonraker_instance", uuid.UUID(str(value)).hex)
        except (HttpRequestError, ValueError, AttributeError, TypeError):
            # Older/restricted servers still provide observations; no hostname
            # or shared SBC serial is substituted for missing instance identity.
            return None
        return self._identity

    def _inventory_key_digest(self) -> str | None:
        self._native_spoolman_configured = True  # Unknown config must not double-debit usage.
        try:
            _, decoded, _ = self.http.request("GET", "/server/config")
        except HttpRequestError:
            return None
        result = decoded.get("result", {}) if isinstance(decoded, dict) else {}
        config = result.get("config") if isinstance(result, dict) else None
        if not isinstance(config, dict):
            return None
        self._native_spoolman_configured = "spoolman" in config
        spoolman = config.get("spoolman", {})
        server = spoolman.get("server") if isinstance(spoolman, dict) else None
        if not isinstance(server, str):
            return None
        try:
            parsed = urlsplit(server)
        except ValueError:
            return None
        cloud = urlsplit(self.filamenthub_url)
        if (parsed.scheme, parsed.netloc) != (cloud.scheme, cloud.netloc):
            return None
        match = re.fullmatch(r"/api/v1/spool_compat/([A-Za-z0-9_-]+)/*", parsed.path)
        if not match or parsed.query or parsed.fragment:
            return None
        return hashlib.sha256(match.group(1).encode()).hexdigest()

    @staticmethod
    def _status_map(decoded: Any) -> dict[str, Any]:
        if not isinstance(decoded, dict):
            raise ProviderUnavailable("Moonraker response is invalid")
        result = decoded.get("result")
        status = result.get("status") if isinstance(result, dict) else None
        if not isinstance(status, dict):
            raise ProviderUnavailable("Moonraker status is missing")
        return status

    @staticmethod
    def _printer_snapshot(status: dict[str, Any]) -> dict[str, Any]:
        print_stats = status.get("print_stats")
        display_status = status.get("display_status")
        extruder = status.get("extruder")
        heater_bed = status.get("heater_bed")
        print_stats = print_stats if isinstance(print_stats, dict) else {}
        display_status = display_status if isinstance(display_status, dict) else {}
        extruder = extruder if isinstance(extruder, dict) else {}
        heater_bed = heater_bed if isinstance(heater_bed, dict) else {}
        printer: dict[str, Any] = {"state": _printer_state(print_stats.get("state"))}
        filename = print_stats.get("filename")
        if isinstance(filename, str) and filename.strip():
            printer["job_name"] = filename.strip()[:300]
        progress = _number(display_status.get("progress"))
        if progress is not None:
            printer["progress_percent"] = max(0, min(100, round(progress * 100)))
        for source, key, target in (
            (extruder, "temperature", "nozzle_temperature"),
            (extruder, "target", "nozzle_target_temperature"),
            (heater_bed, "temperature", "bed_temperature"),
            (heater_bed, "target", "bed_target_temperature"),
        ):
            value = _number(source.get(key))
            if value is not None:
                printer[target] = value
        return printer

    @staticmethod
    def _usage_snapshot(status: dict[str, Any]) -> dict[str, Any] | None:
        print_stats = status.get("print_stats")
        if not isinstance(print_stats, dict):
            return None
        filament_used = _number(print_stats.get("filament_used"))
        if filament_used is None or filament_used < 0:
            return None
        raw_state = str(print_stats.get("state") or "").strip().lower()
        usage: dict[str, Any] = {
            "state": raw_state,
            "filament_used_mm": filament_used,
        }
        filename = print_stats.get("filename")
        if isinstance(filename, str) and filename.strip():
            usage["file_name"] = filename.strip()[:500]
        for source, target in (
            ("total_duration", "total_duration_s"),
            ("print_duration", "print_duration_s"),
        ):
            value = _number(print_stats.get(source))
            if value is not None and value >= 0:
                usage[target] = value
        return usage

    @staticmethod
    def _happy_hare_slots(mmu: dict[str, Any]) -> list[dict[str, Any]]:
        arrays: dict[str, list[Any] | None] = {}
        lengths: set[int] = set()
        for name in ("gate_status", "gate_material", "gate_color", "gate_spool_id"):
            value = mmu.get(name)
            if value is None:
                arrays[name] = None
            elif isinstance(value, list):
                arrays[name] = value
                lengths.add(len(value))
            else:
                raise ProviderUnavailable(f"Happy Hare {name} is not an array")
        gate_count = _integer(mmu.get("num_gates"))
        if gate_count is None:
            if len(lengths) != 1:
                raise ProviderUnavailable("Happy Hare gate count is ambiguous")
            gate_count = next(iter(lengths))
        if gate_count < 1 or gate_count > 256:
            raise ProviderUnavailable("Happy Hare gate count is outside 1..256")
        if any(length != gate_count for length in lengths):
            raise ProviderUnavailable("Happy Hare gate arrays disagree with num_gates")

        selected_gate = _integer(mmu.get("gate"))
        filament_pos = _number(mmu.get("filament_pos"))
        filament_loaded = filament_pos is not None and filament_pos > 0

        def value_at(name: str, index: int, default: Any) -> Any:
            values = arrays[name]
            return values[index] if values is not None else default

        slots: list[dict[str, Any]] = []
        for index in range(gate_count):
            status = _integer(value_at("gate_status", index, -1))
            present = None if status not in {0, 1, 2} else status in {1, 2}
            material = str(value_at("gate_material", index, "") or "").strip()[:80]
            color = str(value_at("gate_color", index, "") or "").lstrip("#").upper()
            slot: dict[str, Any] = {
                "provider_index": index,
                "label": f"Gate {index}",
                "kind": "gate",
                "present": present,
                "active_feed": selected_gate == index and filament_loaded,
                "spool_id": (_integer(value_at("gate_spool_id", index, -1)) or -1),
                "spool_identity_known": arrays["gate_spool_id"] is not None,
            }
            if slot["spool_id"] < 1:
                slot["spool_id"] = None
            if material:
                slot["material"] = material
            if COLOR_PATTERN.fullmatch(color):
                slot["color_hex"] = color
            slots.append(slot)

        has_bypass = mmu.get("has_bypass") is True or selected_gate == -2 or mmu.get("tool") == -2
        if has_bypass:
            slots.append(
                {
                    "provider_index": BYPASS_PROVIDER_INDEX,
                    "label": "Bypass",
                    "kind": "bypass",
                    "present": filament_loaded
                    if selected_gate == -2 or mmu.get("tool") == -2
                    else None,
                    "active_feed": (selected_gate == -2 or mmu.get("tool") == -2)
                    and filament_loaded,
                }
            )
        return slots
