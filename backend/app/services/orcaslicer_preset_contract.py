"""Pure helpers for the FilamentHub/OrcaSlicer filament-preset contract."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from math import isfinite
from typing import Any

ORCA_INVALID_PRESET_NAME_CHARS = frozenset('<>[]:/\\|?*"')

_ORCA_NUMERIC_RANGES = {
    "nozzle_temperature": (0, 1500),
    "nozzle_temperature_initial_layer": (0, 1500),
    "bed_temperature": (0, 300),
    "bed_temperature_initial_layer": (0, 300),
    "hot_plate_temp": (0, 300),
    "hot_plate_temp_initial_layer": (0, 300),
    "cool_plate_temp": (0, 300),
    "cool_plate_temp_initial_layer": (0, 300),
    "eng_plate_temp": (0, 300),
    "eng_plate_temp_initial_layer": (0, 300),
    "textured_plate_temp": (0, 300),
    "textured_plate_temp_initial_layer": (0, 300),
    "supertack_plate_temp": (0, 300),
    "supertack_plate_temp_initial_layer": (0, 300),
    "textured_cool_plate_temp": (0, 300),
    "textured_cool_plate_temp_initial_layer": (0, 300),
    "customized_plate_temp": (0, 300),
    "customized_plate_temp_initial_layer": (0, 300),
    "epoxy_resin_plate_temp": (0, 300),
    "epoxy_resin_plate_temp_initial_layer": (0, 300),
    "filament_dev_chamber_drying_bed_temperature": (0, 300),
    "fan_min_speed": (0, 100),
}

_ORCA_BOUNDED_NONNEGATIVE_RANGES = {
    "fan_max_speed": 1000,
    "filament_retraction_length": 20,
    "filament_retraction_speed": 200,
}

_ORCA_VARIANT_SENTINEL_KEYS = {
    key
    for key in _ORCA_NUMERIC_RANGES
    if "plate_temp" in key or key.startswith("bed_temperature")
}


def is_valid_orca_preset_name(name: str) -> bool:
    """Return whether OrcaSlicer's native save dialog accepts ``name``."""
    normalized = name.strip()
    return bool(normalized) and not any(
        char in ORCA_INVALID_PRESET_NAME_CHARS or ord(char) < 32
        for char in normalized
    )


def is_allowed_orca_preset_name(name: str, existing_name: str | None = None) -> bool:
    """Allow an unchanged legacy name while rejecting newly introduced ones."""
    return name == existing_name or is_valid_orca_preset_name(name)


def format_orca_number(value: int | float | Decimal) -> str:
    """Serialize a numeric option without discarding meaningful precision."""
    decimal_value = Decimal(str(value))
    rendered = format(decimal_value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def format_orca_flow_ratio(flow_rate_percent: int | float | Decimal) -> str:
    return format_orca_number(Decimal(str(flow_rate_percent)) / Decimal("100"))


def _numeric_values(settings: Mapping[str, Any], key: str) -> list[float]:
    raw = settings.get(key)
    values = raw if isinstance(raw, (list, tuple)) else [raw]
    parsed: list[float] = []
    for item in values:
        if item is None:
            continue
        if isinstance(item, str):
            normalized = item.strip().lower()
            if normalized in {"", "nil"} or (
                normalized == "v" and key in _ORCA_VARIANT_SENTINEL_KEYS
            ):
                continue
        if isinstance(item, bool):
            raise ValueError(f"OrcaSlicer setting {key} contains a non-numeric value")
        try:
            value = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"OrcaSlicer setting {key} contains a non-numeric value") from exc
        if not isfinite(value):
            raise ValueError(f"OrcaSlicer setting {key} contains a non-finite value")
        parsed.append(value)
    return parsed


def validate_orca_filament_settings(settings: Mapping[str, Any] | None) -> None:
    """Validate every numeric entry that FH maps into structured columns."""
    if settings is None:
        return
    if not isinstance(settings, Mapping):
        raise ValueError("OrcaSlicer settings must be an object")

    for key, (minimum, maximum) in _ORCA_NUMERIC_RANGES.items():
        if key not in settings:
            continue
        for value in _numeric_values(settings, key):
            if not minimum <= value <= maximum:
                raise ValueError(
                    f"OrcaSlicer setting {key}={value} is outside {minimum}..{maximum}"
                )

    for key, maximum in _ORCA_BOUNDED_NONNEGATIVE_RANGES.items():
        if key not in settings:
            continue
        for value in _numeric_values(settings, key):
            if not 0 <= value <= maximum:
                raise ValueError(
                    f"OrcaSlicer setting {key}={value} is outside 0..{maximum}"
                )

    if "filament_flow_ratio" in settings:
        for value in _numeric_values(settings, "filament_flow_ratio"):
            if not 0 < value <= 2:
                raise ValueError(
                    f"OrcaSlicer setting filament_flow_ratio={value} must be greater than 0 and at most 2"
                )


def extract_structured_filament_values(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract the structured FH projection after validating the complete raw vectors."""
    settings = settings or {}
    validate_orca_filament_settings(settings)

    def first(keys: tuple[str, ...]) -> float | None:
        for key in keys:
            values = _numeric_values(settings, key)
            if values:
                return values[0]
        return None

    result: dict[str, Any] = {}
    extruder_temp = first(("nozzle_temperature", "nozzle_temperature_initial_layer"))
    if extruder_temp is not None:
        result["extruder_temp"] = extruder_temp

    bed_temp = first((
        "bed_temperature",
        "hot_plate_temp",
        "cool_plate_temp",
        "eng_plate_temp",
        "textured_plate_temp",
        "supertack_plate_temp",
        "textured_cool_plate_temp",
        "customized_plate_temp",
        "epoxy_resin_plate_temp",
    ))
    if bed_temp is not None:
        result["bed_temp"] = bed_temp

    flow_ratio = first(("filament_flow_ratio",))
    if flow_ratio is not None:
        result["flow_rate"] = round(flow_ratio * 100, 6)
    elif "filament_flow_ratio" in settings:
        result["flow_rate"] = None

    fan = first(("fan_min_speed", "fan_max_speed"))
    if fan is not None:
        if not fan.is_integer():
            raise ValueError("OrcaSlicer fan speed must be an integer")
        # Some profiles shipped with Orca contain legacy fan_max_speed values
        # above the current 0..100 UI range. Preserve them in raw settings but
        # do not force them into FilamentHub's percentage projection.
        if fan <= 100:
            result["fan_speed"] = int(fan)
    elif "fan_min_speed" in settings or "fan_max_speed" in settings:
        result["fan_speed"] = None

    retraction_length = first(("filament_retraction_length",))
    if retraction_length is not None:
        result["retraction_length"] = retraction_length
    elif "filament_retraction_length" in settings:
        result["retraction_length"] = None

    retraction_speed = first(("filament_retraction_speed",))
    if retraction_speed is not None:
        result["retraction_speed"] = retraction_speed
    elif "filament_retraction_speed" in settings:
        result["retraction_speed"] = None

    return result


def apply_structured_filament_updates(
    source: Mapping[str, Any] | None,
    changes: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply explicit structured PATCH fields to the raw Orca settings blob.

    The raw blob remains authoritative for untouched options. Explicit
    structured fields win over conflicting raw values in the same request.
    """
    settings = dict(source or {})

    if "extruder_temp" in changes and changes["extruder_temp"] is not None:
        value = [format_orca_number(changes["extruder_temp"])]
        settings["nozzle_temperature"] = value
        settings["nozzle_temperature_initial_layer"] = value.copy()

    if "bed_temp" in changes and changes["bed_temp"] is not None:
        value = [format_orca_number(changes["bed_temp"])]
        for key in (
            "bed_temperature",
            "bed_temperature_initial_layer",
            "hot_plate_temp",
            "hot_plate_temp_initial_layer",
            "cool_plate_temp",
            "cool_plate_temp_initial_layer",
            "eng_plate_temp",
            "eng_plate_temp_initial_layer",
            "textured_plate_temp",
            "textured_plate_temp_initial_layer",
            "supertack_plate_temp",
            "supertack_plate_temp_initial_layer",
            "textured_cool_plate_temp",
            "textured_cool_plate_temp_initial_layer",
            "customized_plate_temp",
            "customized_plate_temp_initial_layer",
            "epoxy_resin_plate_temp",
            "epoxy_resin_plate_temp_initial_layer",
        ):
            settings[key] = value.copy()

    if "flow_rate" in changes:
        if changes["flow_rate"] is None:
            settings.pop("filament_flow_ratio", None)
        else:
            settings["filament_flow_ratio"] = [format_orca_flow_ratio(changes["flow_rate"])]

    if "fan_speed" in changes:
        if changes["fan_speed"] is None:
            settings.pop("fan_min_speed", None)
        else:
            settings["fan_min_speed"] = [format_orca_number(changes["fan_speed"])]

    if "retraction_length" in changes:
        if changes["retraction_length"] is None:
            settings.pop("filament_retraction_length", None)
        else:
            settings["filament_retraction_length"] = [format_orca_number(changes["retraction_length"])]

    if "retraction_speed" in changes:
        if changes["retraction_speed"] is None:
            settings.pop("filament_retraction_speed", None)
        else:
            settings["filament_retraction_speed"] = [format_orca_number(changes["retraction_speed"])]

    return settings
