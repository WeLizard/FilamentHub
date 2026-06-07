"""Human-readable labels for OrcaSlicer filament-preset settings keys.

Single source of truth used by the version-history diff endpoint to render
changes as ``Nozzle temperature: 215 -> 220`` instead of raw JSON keys.

Keys are OrcaSlicer ``orcaslicer_settings`` field names (as stored in
``Preset.orcaslicer_settings`` and exported by ``orcaslicer_exporter``).
Anything not listed falls back to the raw key in the diff's
``unmapped_changes`` bucket — so this map does not need to be exhaustive,
only to cover the fields users care about most.
"""

from typing import TypedDict


class FieldLabel(TypedDict):
    """Display metadata for one settings key."""

    label: str
    unit: str | None


# Ordered by rough relevance; lookup is O(1) by dict key regardless.
ORCA_FIELD_LABELS: dict[str, FieldLabel] = {
    # Temperatures
    "nozzle_temperature": {"label": "Nozzle temperature", "unit": "°C"},
    "nozzle_temperature_initial_layer": {"label": "Nozzle temp (first layer)", "unit": "°C"},
    "hot_plate_temp": {"label": "Bed temperature", "unit": "°C"},
    "hot_plate_temp_initial_layer": {"label": "Bed temp (first layer)", "unit": "°C"},
    "cool_plate_temp": {"label": "Cool plate temperature", "unit": "°C"},
    "textured_plate_temp": {"label": "Textured plate temperature", "unit": "°C"},
    "eng_plate_temp": {"label": "Engineering plate temperature", "unit": "°C"},
    "idle_temperature": {"label": "Idle temperature", "unit": "°C"},
    "chamber_temperature": {"label": "Chamber temperature", "unit": "°C"},

    # Flow & extrusion
    "filament_flow_ratio": {"label": "Flow ratio", "unit": None},
    "filament_max_volumetric_speed": {"label": "Max volumetric speed", "unit": "mm³/s"},
    "pressure_advance": {"label": "Pressure advance", "unit": None},
    "enable_pressure_advance": {"label": "Pressure advance enabled", "unit": None},
    "filament_diameter": {"label": "Filament diameter", "unit": "mm"},
    "filament_density": {"label": "Density", "unit": "g/cm³"},

    # Cooling / fan
    "fan_min_speed": {"label": "Min fan speed", "unit": "%"},
    "fan_max_speed": {"label": "Max fan speed", "unit": "%"},
    "fan_cooling_layer_time": {"label": "Fan cooling layer time", "unit": "s"},
    "overhang_fan_speed": {"label": "Overhang fan speed", "unit": "%"},
    "overhang_fan_threshold": {"label": "Overhang fan threshold", "unit": None},
    "close_fan_the_first_x_layers": {"label": "Fan off first N layers", "unit": None},
    "full_fan_speed_layer": {"label": "Full fan speed layer", "unit": None},
    "slow_down_layer_time": {"label": "Slow down layer time", "unit": "s"},
    "slow_down_min_speed": {"label": "Slow down min speed", "unit": "mm/s"},
    "reduce_fan_stop_start_freq": {"label": "Reduce fan stop/start", "unit": None},

    # Retraction (filament-level overrides)
    "filament_retraction_length": {"label": "Retraction length", "unit": "mm"},
    "filament_retraction_speed": {"label": "Retraction speed", "unit": "mm/s"},
    "filament_z_hop": {"label": "Z hop", "unit": "mm"},
    "filament_wipe": {"label": "Wipe", "unit": None},

    # Material identity
    "filament_type": {"label": "Material type", "unit": None},
    "filament_vendor": {"label": "Vendor", "unit": None},
    "default_filament_colour": {"label": "Colour", "unit": None},
    "filament_soluble": {"label": "Soluble", "unit": None},
    "filament_is_support": {"label": "Support material", "unit": None},

    # Temperature ranges (used by compatibility checks)
    "nozzle_temperature_range_low": {"label": "Nozzle temp range (low)", "unit": "°C"},
    "nozzle_temperature_range_high": {"label": "Nozzle temp range (high)", "unit": "°C"},

    # Drying / storage
    "filament_minimal_purge_on_wipe_tower": {"label": "Min purge on wipe tower", "unit": "mm³"},
    "temperature_vitrification": {"label": "Softening temperature", "unit": "°C"},

    # G-code hooks
    "filament_start_gcode": {"label": "Start G-code", "unit": None},
    "filament_end_gcode": {"label": "End G-code", "unit": None},
}


def resolve_field(key: str) -> FieldLabel | None:
    """Return display metadata for a settings key, or None if unmapped."""
    return ORCA_FIELD_LABELS.get(key)
