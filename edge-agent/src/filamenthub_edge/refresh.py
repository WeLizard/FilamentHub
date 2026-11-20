"""Fixed, locally opted-in Happy Hare refresh with observed acknowledgement."""

from __future__ import annotations

import ast
import math
import time
from typing import Any

from .errors import HttpRequestError, ProviderUnavailable

SAFE_STATES = {"standby", "complete", "cancelled", "error"}
SAFE_MMU_STATES = SAFE_STATES | {"ready", "initialized"}


def baseline_matches(target: dict[str, Any], slots: list[dict[str, Any]]) -> bool:
    """Detect visible drift using the ordinary observation, without extra I/O."""
    observed = {slot.get("provider_index"): slot for slot in slots}
    for gate in target["gates"]:
        slot = observed.get(gate["index"], {})
        if not slot.get("spool_identity_known"):
            return False
        if (slot.get("spool_id") or -1) != gate["spool_id"]:
            return False
        if slot.get("material") and slot["material"] != gate["material"].strip()[:80]:
            return False
        if slot.get("color_hex") and slot["color_hex"].lower() != gate["color"].lower():
            return False
    return True


def safe_status(status: dict[str, Any]) -> bool:
    return (
        status.get("print_stats", {}).get("state") in SAFE_STATES
        and status.get("mmu", {}).get("enabled") is True
        and status.get("pause_resume", {}).get("is_paused") is False
        and status.get("idle_timeout", {}).get("state") in {"Idle", "Ready"}
        and status.get("mmu", {}).get("print_state") in SAFE_MMU_STATES
        and status.get("mmu", {}).get("is_paused") is False
    )


def map_matches(target: dict[str, Any], status: dict[str, Any], default_temp: int) -> bool:
    mmu = status.get("mmu", {})
    guard = status.get("gcode_macro FH_EDGE_REFRESH", {})
    try:
        last_map = guard.get("last_map", "")
        if not isinstance(last_map, str) or len(last_map) > 1024 * 1024:
            return False
        callback = ast.literal_eval(last_map)
        gates = target["gates"]
        if not isinstance(callback, dict) or mmu["num_gates"] != len(gates):
            return False
        for gate in gates:
            index = gate["index"]
            row = callback[index]
            for desired, observed in (
                ("spool_id", "gate_spool_id"), ("name", "gate_filament_name"),
                ("material", "gate_material"), ("vendor", "gate_vendor"),
                ("initial_weight", "gate_initial_weight"),
            ):
                if mmu[observed][index] != gate[desired]:
                    return False
            if str(mmu["gate_color"][index]).lower() != gate["color"].lower():
                return False
            if mmu["gate_temperature"][index] != max(gate["temperature"], default_temp):
                return False
            # Spoolman aliases are NOT the hardware gate_spool_rfid. The guard
            # records the exact successfully applied native callback instead.
            if set(str(row.get("rfids", "")).split(",")) != set(gate["rfids"].split(",")):
                return False
            if row.get("spool_id", -1) != gate["spool_id"]:
                return False
        return True
    except (ValueError, SyntaxError, TypeError, KeyError, IndexError, RecursionError):
        return False


def required_map_fields(target: dict[str, Any], status: dict[str, Any]) -> bool:
    mmu = status.get("mmu", {})
    count = mmu.get("num_gates")
    if type(count) is not int or not 1 <= count <= 256 or count != len(target["gates"]):
        return False
    for field in ("gate_spool_id", "gate_filament_name", "gate_material", "gate_vendor",
                  "gate_color", "gate_temperature", "gate_initial_weight"):
        values = mmu.get(field)
        if not isinstance(values, list) or len(values) != count:
            return False
        if field in {"gate_filament_name", "gate_material", "gate_vendor", "gate_color"}:
            if any(not isinstance(value, str) for value in values):
                return False
        elif any(isinstance(value, bool) or not isinstance(value, (int, float))
                 or not math.isfinite(value) for value in values):
            return False
        elif field == "gate_spool_id" and any(type(value) is not int or value < -1
                                              for value in values):
            return False
    guard = status.get("gcode_macro FH_EDGE_REFRESH", {})
    if any(type(guard.get(field)) is not int or guard[field] < 0
           for field in ("requested", "applied", "deferred")):
        return False
    last_map = guard.get("last_map")
    if not isinstance(last_map, str) or len(last_map) > 1024 * 1024:
        return False
    if last_map:
        try:
            callback = ast.literal_eval(last_map)
            if not isinstance(callback, dict) or any(not isinstance(row, dict)
                                                      for row in callback.values()):
                return False
        except (ValueError, SyntaxError, TypeError, RecursionError):
            return False
    return True


def refresh_happy_hare(provider: Any, target: dict[str, Any], identity: tuple[str, str]) -> str:
    """Return applied/deferred/blocked/pending; never treat HTTP success as ACK."""
    provider.set_refresh_ready(False)
    if provider.material_provider != "happy_hare" or not provider.auto_refresh:
        return "blocked:unsupported_provider"
    provider._identity_checked_at = float("-inf")
    if provider._device_identity() != identity:
        return "blocked:printer_identity"
    if provider._inventory_key_digest() != target.get("inventory_key_digest"):
        return "blocked:inventory_key"
    try:
        _, info, _ = provider.http.request("GET", "/printer/info")
        if info.get("result", {}).get("hostname") != target.get("printer_hostname"):
            return "blocked:printer_hostname"
        _, decoded, _ = provider.http.request("POST", "/printer/objects/query", payload={
            "objects": {"mmu": None, "print_stats": ["state"],
                        "pause_resume": ["is_paused"], "idle_timeout": ["state"],
                        "gcode_macro FH_EDGE_REFRESH": None,
                        "gcode_macro MMU_GATE_MAP": ["guard_version"],
                        "configfile": ["settings"]},
        })
        status = provider._status_map(decoded)
        guard = status.get("gcode_macro FH_EDGE_REFRESH", {})
        settings = status.get("configfile", {}).get("settings", {})
        wrapper = status.get("gcode_macro MMU_GATE_MAP", {})
        if (type(guard.get("guard_version")) is not int or guard["guard_version"] != 1
                or type(wrapper.get("guard_version")) is not int or wrapper["guard_version"] != 1
                or settings.get("gcode_macro mmu_gate_map", {}).get("rename_existing", "").upper()
                != "_FH_ORIGINAL_MMU_GATE_MAP"):
            return "blocked:missing_guard"
        if status.get("mmu", {}).get("spoolman_support") != "pull":
            return "blocked:pull_mode_required"
        if status.get("mmu", {}).get("enabled") is not True:
            return "blocked:mmu_disabled"
        if not required_map_fields(target, status):
            return "blocked:incomplete_map_fields"
        raw_temp = settings.get("mmu", {}).get("default_extruder_temp")
        if (isinstance(raw_temp, bool) or raw_temp is None
                or not math.isfinite(float(raw_temp)) or float(raw_temp) <= 0):
            return "blocked:default_temperature"
        default_temp = int(float(raw_temp))
        provider.set_refresh_ready(True)
        if not safe_status(status):
            return "deferred:printer_busy_or_unknown"
        if map_matches(target, status, default_temp):
            return "applied"
        now = time.monotonic()
        if now < getattr(provider, "_refresh_retry_at", 0):
            return "pending:verification"
        provider._refresh_retry_at = now + 60
        # Both the fixed request macro AND the later native callback reevaluate
        # printer state inside Klipper. No cloud text enters the command stream.
        provider.http.request("POST", "/printer/gcode/script",
                              payload={"script": "FH_EDGE_REFRESH"})
        return "pending:verification"
    except (HttpRequestError, ProviderUnavailable, AttributeError, ValueError, TypeError, KeyError):
        provider.set_refresh_ready(False)
        return "blocked:provider_unavailable"
