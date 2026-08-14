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
    "chamber_minimal_temperature": {"label": "Minimum chamber temperature", "unit": "°C"},

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
    "initial_layer_fan_speed": {"label": "First layer fan speed", "unit": "%"},
    "full_fan_speed_layer": {"label": "Full fan speed layer", "unit": None},
    "slow_down_layer_time": {"label": "Slow down layer time", "unit": "s"},
    "slow_down_min_speed": {"label": "Slow down min speed", "unit": "mm/s"},
    "reduce_fan_stop_start_freq": {"label": "Reduce fan stop/start", "unit": None},
    "activate_air_filtration_during_print": {
        "label": "Air filtration during print",
        "unit": None,
    },
    "activate_air_filtration_on_completion": {
        "label": "Air filtration after print",
        "unit": None,
    },

    # Retraction (filament-level overrides)
    "filament_retraction_length": {"label": "Retraction length", "unit": "mm"},
    "filament_retraction_speed": {"label": "Retraction speed", "unit": "mm/s"},
    "filament_retract_after_wipe": {"label": "Retraction after wipe", "unit": "%"},
    "filament_retract_length_toolchange": {
        "label": "Material-change retraction length",
        "unit": "mm",
    },
    "filament_retract_restart_extra_toolchange": {
        "label": "Material-change extra feed",
        "unit": "mm",
    },
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
    "filament_change_extrusion_role_gcode": {
        "label": "Change extrusion role G-code",
        "unit": None,
    },
    "filament_end_gcode": {"label": "End G-code", "unit": None},

    # Process: quality / strength / speed / multimaterial
    "zaa_enabled": {"label": "Z contouring enabled", "unit": None},
    "zaa_minimize_perimeter_height": {
        "label": "Minimize wall height angle",
        "unit": "°",
    },
    "zaa_min_z": {"label": "Minimum Z height", "unit": "mm"},
    "zaa_dont_alternate_fill_direction": {
        "label": "Do not alternate fill direction",
        "unit": None,
    },
    "wall_maximum_resolution": {"label": "Maximum wall resolution", "unit": "mm"},
    "wall_maximum_deviation": {"label": "Maximum wall deviation", "unit": "mm"},
    "top_surface_fill_order": {"label": "Top surface fill order", "unit": None},
    "top_layer_direction": {"label": "Top layer direction", "unit": "°"},
    "top_surface_expansion": {"label": "Top surface expansion", "unit": "mm"},
    "top_surface_expansion_margin": {
        "label": "Top surface expansion margin",
        "unit": "mm",
    },
    "top_surface_expansion_direction": {
        "label": "Top surface expansion direction",
        "unit": None,
    },
    "sparse_infill_smooth_factor": {
        "label": "Sparse infill smooth factor",
        "unit": "%",
    },
    "separated_infills": {"label": "Separated infills", "unit": None},
    "small_support_perimeter_speed": {
        "label": "Small support perimeters",
        "unit": "mm/s or %",
    },
    "small_support_perimeter_threshold": {
        "label": "Small support perimeters threshold",
        "unit": "mm",
    },
    "toolchange_ordering": {"label": "Toolchange ordering", "unit": None},
    "brim_ears_outer_only": {
        "label": "Brim ears on outer corners only",
        "unit": None,
    },
    "bottom_layer_direction": {"label": "Bottom layer direction", "unit": "°"},
    "bottom_surface_fill_order": {"label": "Bottom surface fill order", "unit": None},
    "bridge_line_width": {"label": "Bridge line width", "unit": "mm or %"},
    "brim_flow_ratio": {"label": "Brim flow ratio", "unit": None},
    "center_of_surface_pattern": {"label": "Surface pattern center", "unit": None},
    "combine_brims": {"label": "Combine brims", "unit": None},
    "elefant_foot_layers_density": {"label": "Elephant foot layers density", "unit": "%"},
    "fuzzy_skin_layers_between_ripple_offset": {"label": "Layers between ripple offset", "unit": None},
    "fuzzy_skin_ripple_offset": {"label": "Fuzzy skin ripple offset", "unit": "%"},
    "fuzzy_skin_ripples_per_layer": {"label": "Fuzzy skin ripples per layer", "unit": None},
    "gyroid_optimized": {"label": "Gyroid Z-buckling optimization", "unit": None},
    "hole_to_polyhole_max_edges": {"label": "Maximum polyhole edges", "unit": None},
    "initial_layer_travel_jerk": {"label": "First layer travel jerk", "unit": "mm/s or %"},
    "ironing_expansion": {"label": "Ironing expansion", "unit": "mm"},
    "lightning_overhang_angle": {"label": "Lightning overhang angle", "unit": "°"},
    "lightning_prune_angle": {"label": "Lightning prune angle", "unit": "°"},
    "lightning_straightening_angle": {"label": "Lightning straightening angle", "unit": "°"},
    "process_change_extrusion_role_gcode": {"label": "Change extrusion role G-code", "unit": None},
    "relative_bridge_angle": {"label": "Relative bridge angle", "unit": None},
}


def resolve_field(key: str) -> FieldLabel | None:
    """Return display metadata for a settings key, or None if unmapped."""
    return ORCA_FIELD_LABELS.get(key)
