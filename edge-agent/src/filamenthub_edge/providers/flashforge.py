"""Flashforge Creator 5 / 5 Pro observations over the printer's LAN HTTP API.

The stock firmware exposes an undocumented HTTP API on port 8898 only while
LAN mode is enabled. Every request carries the printer serial number and the
check code shown on the printer's network screen. Field meanings follow the
community reference (Parallel-7/flashforge-api-docs, Creator 5 firmware
1.7.8-1.9.8) and still need confirmation on more firmware builds.

The printer reports no per-tool filament usage and no confirmed active tool,
so this provider reads printer state and material-station slots only. It does
not claim consumption.
"""

from __future__ import annotations

import math
import re
from typing import Any

from ..errors import HttpRequestError, ProviderUnavailable
from ..http import JsonHttpClient
from .base import ProviderSnapshot

DEFAULT_PORT = 8898
MAX_SLOTS = 16
SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
COLOR_PATTERN = re.compile(r"^#?([0-9A-Fa-f]{6})$")
IDENTITY_KIND = "flashforge_serial"
# Response codes documented for credential and mode failures.
AUTH_FAILED = 1
LAN_MODE_OFF = -2
_STATES = {
    "ready": "idle",
    "heating": "preparing",
    "calibrate_doing": "preparing",
    "printing": "printing",
    "pausing": "paused",
    "paused": "paused",
    "completed": "finished",
    "cancel": "failed",
    "error": "failed",
}


def normalize_serial(value: str) -> str:
    serial = value.strip()
    if not SERIAL_PATTERN.fullmatch(serial):
        raise ValueError("invalid Flashforge serial number")
    return serial


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _temperature(value: Any, *, low: float, high: float) -> float | None:
    number = _number(value)
    if number is None or number < low or number > high:
        # Creator 5 reports -108 for a missing chamber sensor.
        return None
    return round(number, 1)


def _text(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:maximum] or None


def _color(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = COLOR_PATTERN.fullmatch(value.strip())
    return match.group(1).upper() if match else None


def printer_state(value: Any) -> str:
    return _STATES.get(str(value or "").strip().lower(), "unknown")


def _nozzle(detail: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return one nozzle reading only when it is unambiguous."""
    temps = detail.get("nozzleTemps")
    targets = detail.get("nozzleTargetTemps")
    if (
        isinstance(temps, list)
        and isinstance(targets, list)
        and temps
        and len(temps) == len(targets)
    ):
        heated = [
            index for index, target in enumerate(targets)
            if (_number(target) or 0) > 0
        ]
        if len(temps) == 1:
            heated = [0]
        if len(heated) != 1:
            # Several heated tools or none: no single "the nozzle" exists.
            return None, None
        index = heated[0]
        return (
            _temperature(temps[index], low=-50, high=600),
            _temperature(targets[index], low=0, high=600),
        )
    return (
        _temperature(detail.get("rightTemp"), low=-50, high=600),
        _temperature(detail.get("rightTargetTemp"), low=0, high=600),
    )


def build_printer(detail: dict[str, Any]) -> dict[str, Any]:
    state = printer_state(detail.get("status"))
    printer: dict[str, Any] = {"state": state}
    if state in {"printing", "paused", "preparing", "finished", "failed"}:
        job = _text(detail.get("printFileName"), 300)
        if job:
            printer["job_name"] = job
        progress = _number(detail.get("printProgress"))
        if progress is not None and 0 <= progress <= 1:
            printer["progress_percent"] = round(progress * 100)
        if state in {"printing", "paused", "preparing"}:
            remaining = _number(detail.get("estimatedTime"))
            if remaining is not None and 0 <= remaining <= 2_592_000:
                printer["remaining_seconds"] = int(remaining)
        layer = _integer(detail.get("printLayer"))
        total = _integer(detail.get("targetPrintLayer"))
        if layer is not None and 0 <= layer <= 10_000_000:
            printer["current_layer"] = layer
        if total is not None and 0 < total <= 10_000_000:
            printer["total_layers"] = total
    nozzle, nozzle_target = _nozzle(detail)
    for key, value in (
        ("nozzle_temperature", nozzle),
        ("nozzle_target_temperature", nozzle_target),
        ("bed_temperature", _temperature(detail.get("platTemp"), low=-50, high=250)),
        ("bed_target_temperature", _temperature(detail.get("platTargetTemp"), low=0, high=250)),
        ("chamber_temperature", _temperature(detail.get("chamberTemp"), low=-50, high=150)),
    ):
        if value is not None:
            printer[key] = value
    error = _text(detail.get("errorCode"), 80)
    if error and error not in {"0", "E0000"}:
        printer["error_code"] = error
    return printer


def build_slots(detail: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Return material-station slots and whether they form the complete station."""
    station = detail.get("matlStationInfo")
    if not isinstance(station, dict):
        return [], False
    entries = station.get("slotInfos")
    if not isinstance(entries, list) or len(entries) > MAX_SLOTS:
        return [], False
    slots: dict[int, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return [], False
        slot_id = _integer(entry.get("slotId"))
        if slot_id is None or slot_id < 1 or slot_id > MAX_SLOTS or slot_id - 1 in slots:
            return [], False
        present = entry.get("hasFilament")
        slot: dict[str, Any] = {
            "provider_index": slot_id - 1,
            "label": f"Slot {slot_id}",
            "kind": "slot",
            "present": present if isinstance(present, bool) else None,
            "spool_identity_known": False,
        }
        if present is True:
            material = _text(entry.get("materialName"), 80)
            if material and material.strip("?-"):
                slot["material"] = material
            color = _color(entry.get("materialColor"))
            if color:
                slot["color_hex"] = color
        slots[slot_id - 1] = slot
    ordered = [slots[index] for index in sorted(slots)]
    count = _integer(station.get("slotCnt"))
    complete = (
        count is not None and count == len(ordered) > 0 and sorted(slots) == list(range(count))
    )
    return ordered, complete


class FlashforgeProvider:
    def __init__(
        self,
        base_url: str,
        *,
        serial_number: str,
        check_code: str,
        timeout: float,
        http_client: JsonHttpClient | None = None,
    ) -> None:
        self.http = http_client or JsonHttpClient(base_url, allow_http=True, timeout=timeout)
        self.serial_number = normalize_serial(serial_number)
        self._check_code = check_code
        self._capabilities = ["read", "presence"]

    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    def _detail(self) -> dict[str, Any]:
        try:
            _, decoded, _ = self.http.request(
                "POST",
                "/detail",
                payload={"serialNumber": self.serial_number, "checkCode": self._check_code},
            )
        except HttpRequestError as exc:
            raise ProviderUnavailable("Flashforge LAN API did not answer") from exc
        if not isinstance(decoded, dict):
            raise ProviderUnavailable("Flashforge LAN API response is invalid")
        code = _integer(decoded.get("code"))
        if code == AUTH_FAILED:
            raise ProviderUnavailable(
                "Flashforge rejected the serial number or check code"
            )
        if code == LAN_MODE_OFF:
            raise ProviderUnavailable("Flashforge LAN mode is off")
        detail = decoded.get("detail")
        if code != 0 or not isinstance(detail, dict):
            raise ProviderUnavailable("Flashforge LAN API returned an error")
        return detail

    def observe(self) -> ProviderSnapshot:
        detail = self._detail()
        slots, complete = build_slots(detail)
        return ProviderSnapshot(
            printer=build_printer(detail),
            slots=slots,
            slot_topology_complete=complete,
            capabilities=self.capabilities(),
            usage=None,
            # The printer accepted this exact serial number, which makes it
            # device-read identity evidence rather than a configured label.
            device_identity=(IDENTITY_KIND, self.serial_number.upper()),
        )
