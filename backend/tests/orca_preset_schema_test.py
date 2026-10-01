"""Guards the generated OrcaSlicer preset schema the website renders from.

The schema is produced by ``scripts/generate_orca_preset_schema.py`` from the
upstream sources; the point here is that a filament key the registry accepts can
never silently drop out of what the website knows about.
"""

import json
import re
from pathlib import Path

import pytest

from app.services.orca_field_registry import ORCA_PRESET_FIELDS

DATA_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "data"
KINDS = ("filament", "process", "machine")

_ENVELOPE = "preset file metadata, not a config option"
_PROJECT_LEVEL = "defined upstream as a project-level key, not part of the filament preset list"
_OBSOLETE = "obsolete: OrcaSlicer drops it on load (ignore list of PrintConfigDef::handle_legacy)"
_RENAMED = "old name: OrcaSlicer renames it on load (PrintConfigDef::handle_legacy)"
_TYPO = "misspelled key in shipped profiles; OrcaSlicer discards it as an unknown key"
_PLACEHOLDER = "G-code placeholder name, not a stored option"
_FOREIGN = (
    "not defined by PrintConfig.cpp at the pinned upstream commit; appears in shipped "
    "vendor/fork profiles and is discarded by OrcaSlicer as an unknown key"
)

# Registry keys deliberately absent from the filament schema, grouped by reason.
# A new registry key must be added to the schema or reviewed into this list.
_NON_UI_FILAMENT_KEYS_BY_REASON: dict[str, tuple[str, ...]] = {
    _ENVELOPE: (
        "_comment",
        "data",
        "description",
        "filament_id",
        "from",
        "instantiation",
        "is_custom_defined",
        "name",
        "renamed_from",
        "setting_id",
        "total",
        "type",
        "version",
    ),
    _PROJECT_LEVEL: ("filament_colour", "filament_settings_id", "plugins"),
    _OBSOLETE: (
        "bed_temperature",
        "bed_temperature_difference",
        "bed_temperature_initial_layer",
        "filament_load_time",
        "filament_unload_time",
    ),
    _RENAMED: ("chamber_temperatures",),
    _TYPO: ("idle_temperture", "nozzle_temperature_intial_layer", "temperture_vitrification"),
    _PLACEHOLDER: ("filament_extruder_id", "first_layer_temperature"),
    _FOREIGN: (
        "activate_chamber_layer",
        "additional_cooling_fan_speed_unseal",
        "bed_type",
        "box_temperature",
        "box_temperature_range_high",
        "box_temperature_range_low",
        "circle_compensation_speed",
        "cool_cds_fan_start_at_height",
        "cool_special_cds_fan_speed",
        "counter_coef_1",
        "counter_coef_2",
        "counter_coef_3",
        "counter_limit_max",
        "counter_limit_min",
        "customized_plate_temp",
        "customized_plate_temp_initial_layer",
        "diameter_limit",
        "disable_fan_first_layers",
        "enable_special_area_additional_cooling_fan",
        "enable_volume_fan",
        "epoxy_resin_plate_temp",
        "epoxy_resin_plate_temp_initial_layer",
        "external_perimeter_speed",
        "fan_cooling_layer_time_BRASS",
        "fan_cooling_layer_time_HS",
        "fan_max_speed_BRASS",
        "fan_max_speed_HS",
        "fan_min_speed_BRASS",
        "fan_min_speed_HS",
        "fan_p2_after_x_layers",
        "fan_p2_before_x_layers",
        "fan_p2_speed_before_x_layers",
        "fan_speed_after_x_layers",
        "filament_bridge_speed",
        "filament_color",
        "filament_enable_overhang_speed",
        "filament_flow_ratio_initial_layer",
        "filament_long_retractions_when_ec",
        "filament_overhang_1_4_speed",
        "filament_overhang_2_4_speed",
        "filament_overhang_3_4_speed",
        "filament_overhang_4_4_speed",
        "filament_overhang_totally_speed",
        "filament_retract_layer_change",
        "filament_retraction_distances_when_ec",
        "filament_scarf_gap",
        "filament_scarf_height",
        "filament_scarf_length",
        "filament_scarf_seam_type",
        "filament_spool_weight",
        "filament_support_printable",
        "filament_toolchange_time",
        "filament_velocity_adaptation_factor",
        "hole_coef_1",
        "hole_coef_2",
        "hole_coef_3",
        "hole_limit_max",
        "hole_limit_min",
        "impact_strength_z",
        "keep_fan_always_on",
        "material_flow_dependent_temperature",
        "material_flow_temp_graph",
        "no_slow_down_for_cooling_on_outwalls",
        "nozzle_temperature_BRASS",
        "nozzle_temperature_HS",
        "nozzle_temperature_initial_layer_BRASS",
        "nozzle_temperature_initial_layer_HS",
        "overhang_threshold_participating_cooling",
        "override_process_overhang_speed",
        "pre_start_fan_time",
        "shrink_ratio",
        "slow_down_layer_time_BRASS",
        "slow_down_layer_time_HS",
        "temp_max",
        "temp_min",
    ),
}
NON_UI_FILAMENT_KEYS = {
    key: reason for reason, keys in _NON_UI_FILAMENT_KEYS_BY_REASON.items() for key in keys
}


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    assert not duplicates, f"duplicate JSON keys: {duplicates}"
    return dict(pairs)


def _load(kind: str) -> dict:
    path = DATA_DIR / f"orcaPresetSchema.{kind}.json"
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)


def _placed_keys(schema: dict) -> list[str]:
    keys: list[str] = []
    for page in schema["pages"]:
        for group in page["groups"]:
            for row in group["rows"]:
                items = [row] if isinstance(row, str) else row["keys"]
                keys += [item if isinstance(item, str) else item["key"] for item in items]
    return keys


def test_every_filament_registry_key_is_in_the_schema_or_reviewed() -> None:
    registry = set(ORCA_PRESET_FIELDS["filament"])
    schema_keys = set(_load("filament")["options"])
    reviewed = set(NON_UI_FILAMENT_KEYS)

    assert len(NON_UI_FILAMENT_KEYS) == sum(map(len, _NON_UI_FILAMENT_KEYS_BY_REASON.values()))
    unreviewed = sorted(registry - schema_keys - reviewed)
    assert not unreviewed, (
        f"registry keys missing from the filament schema and not reviewed: {unreviewed}; "
        "regenerate the schema or add them to the reviewed list with a reason"
    )
    stale = sorted(reviewed - registry)
    assert not stale, f"reviewed keys no longer in the registry: {stale}"
    shadowed = sorted(reviewed & schema_keys)
    assert not shadowed, f"reviewed as non-UI but present in the schema: {shadowed}"


@pytest.mark.parametrize("kind", KINDS)
def test_schema_is_well_formed(kind: str) -> None:
    schema = _load(kind)
    assert schema["format"] == "filamenthub.orca-preset-schema"
    assert schema["kind"] == kind
    assert re.fullmatch(r"[0-9a-f]{40}", schema["source"]["commit"])
    assert schema["diagnostics"]["unresolved"] == []

    options = schema["options"]
    assert options
    for key, option in options.items():
        assert option["mode"] in ("simple", "advanced", "expert"), key
        if option["type"] == "enum":
            assert option.get("values"), f"enum {key} has no values"
        if "labels" in option:
            assert len(option["labels"]) == len(option["values"]), key

    placed = _placed_keys(schema)
    assert len(placed) == len(set(placed)), "an option is placed twice"
    assert set(placed) <= set(options)
