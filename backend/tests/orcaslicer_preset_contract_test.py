from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.orca_sync import (
    _extract_values_from_orcaslicer_settings,
    _preset_id_from_sync_info,
    get_sync_prefs,
)
from app.schemas.orca_sync import OrcaFilamentPresetPayload
from app.schemas.preset import PresetCreate, PresetUpdate
from app.services.orcaslicer_preset_contract import (
    apply_structured_filament_updates,
    extract_structured_filament_values,
    format_orca_flow_ratio,
    is_allowed_orca_preset_name,
    is_valid_orca_preset_name,
    validate_orca_filament_settings,
)


@pytest.mark.asyncio
async def test_plugin_sync_preferences_expose_every_direction(auth_user, db_session):
    user = SimpleNamespace(
        id=auth_user.id,
        auto_import_local_presets=True,
        sync_printer_endpoints=False,
        allow_filament_presets_import=True,
        allow_filament_presets_export=False,
        allow_printer_profiles_import=False,
        allow_printer_profiles_export=True,
        allow_print_profiles_import=True,
        allow_print_profiles_export=False,
    )

    result = await get_sync_prefs(user, db_session)
    key = result.pop("printer_discovery_key")
    assert isinstance(key, str) and len(key) == 64
    assert result == {
        "auto_import_local_presets": True,
        "sync_printer_endpoints": False,
        "allow_filament_presets_import": True,
        "allow_filament_presets_export": False,
        "allow_printer_profiles_import": False,
        "allow_printer_profiles_export": True,
        "allow_print_profiles_import": True,
        "allow_print_profiles_export": False,
    }


def test_orca_preset_name_matches_native_restrictions():
    assert is_valid_orca_preset_name("Generic PETG @Printer")
    assert not is_valid_orca_preset_name("PLA/0.4")
    assert not is_valid_orca_preset_name("Legacy [fh]")
    assert not is_valid_orca_preset_name("Line\nBreak")
    assert is_allowed_orca_preset_name("PLA/0.4", existing_name="PLA/0.4")
    assert not is_allowed_orca_preset_name("PLA/0.6", existing_name="PLA/0.4")


def test_preset_schema_accepts_current_orca_temperature_range():
    preset = PresetCreate(
        filament_id=1,
        name="High temperature material",
        extruder_temp=460,
        bed_temp=140,
    )

    assert preset.extruder_temp == 460
    assert preset.bed_temp == 140


def test_structured_patch_updates_raw_values_without_dropping_unknown_keys():
    source = {
        "nozzle_temperature": ["210"],
        "filament_plugin_config_overrides": "fixture",
    }

    result = apply_structured_filament_updates(source, {"extruder_temp": 260})

    assert result["nozzle_temperature"] == ["260"]
    assert result["nozzle_temperature_initial_layer"] == ["260"]
    assert result["filament_plugin_config_overrides"] == "fixture"
    assert source["nozzle_temperature"] == ["210"]


def test_structured_patch_wins_over_conflicting_raw_and_clears_optional_values():
    source = {
        "filament_flow_ratio": ["0.91"],
        "fan_min_speed": ["40"],
        "unknown_plugin_setting": "keep",
    }

    result = apply_structured_filament_updates(
        source,
        {"flow_rate": 103.48, "fan_speed": None},
    )

    assert result["filament_flow_ratio"] == ["1.0348"]
    assert "fan_min_speed" not in result
    assert result["unknown_plugin_setting"] == "keep"


def test_required_temperatures_can_be_omitted_but_not_cleared():
    assert PresetUpdate().model_dump(exclude_unset=True) == {}
    assert PresetUpdate(flow_rate=None).model_dump(exclude_unset=True) == {"flow_rate": None}
    assert PresetUpdate(name="Updated").name == "Updated"
    with pytest.raises(ValidationError):
        PresetUpdate(extruder_temp=None)
    with pytest.raises(ValidationError):
        PresetUpdate(bed_temp=None)
    with pytest.raises(ValidationError):
        PresetUpdate(name=None)


def test_flow_ratio_preserves_orca_precision():
    assert format_orca_flow_ratio(92.6) == "0.926"
    assert format_orca_flow_ratio(103.48) == "1.0348"
    extracted = _extract_values_from_orcaslicer_settings({"filament_flow_ratio": "1.0348"})
    assert extracted["flow_rate"] == 103.48


def test_comma_serialized_numeric_vector_is_read_without_rewriting_raw_settings():
    settings = {
        "nozzle_temperature": "220,220",
        "nozzle_temperature_initial_layer": "225,225",
    }

    extracted = extract_structured_filament_values(settings)

    assert extracted["extruder_temp"] == 220
    assert settings == {
        "nozzle_temperature": "220,220",
        "nozzle_temperature_initial_layer": "225,225",
    }


def test_comma_serialized_numeric_vector_validates_every_entry():
    with pytest.raises(ValueError, match="nozzle_temperature"):
        validate_orca_filament_settings({"nozzle_temperature": "220,999999"})


def test_current_orca_catalog_ranges_are_accepted_without_losing_raw_values():
    settings = {
        "filament_flow_ratio": ["0.48"],
        "filament_retraction_length": ["8"],
        "filament_retraction_speed": ["200"],
        "fan_max_speed": ["1000"],
        "textured_plate_temp_initial_layer": ["V"],
    }

    extracted = extract_structured_filament_values(settings)

    assert extracted == {
        "flow_rate": 48.0,
        "retraction_length": 8.0,
        "retraction_speed": 200.0,
    }
    assert settings["fan_max_speed"] == ["1000"]
    assert settings["textured_plate_temp_initial_layer"] == ["V"]


def test_orca_import_rejects_values_outside_the_filament_contract():
    with pytest.raises(ValidationError):
        OrcaFilamentPresetPayload(name="Invalid", extruder_temp=1501)
    with pytest.raises(ValidationError):
        OrcaFilamentPresetPayload(name="Invalid", bed_temp=301)
    with pytest.raises(ValueError, match="nozzle_temperature"):
        _extract_values_from_orcaslicer_settings({"nozzle_temperature": ["999999"]})


def test_raw_validation_checks_every_extruder_and_bed_type():
    with pytest.raises(ValueError, match="nozzle_temperature"):
        validate_orca_filament_settings({"nozzle_temperature": ["200", "999999"]})
    with pytest.raises(ValueError, match="cool_plate_temp"):
        validate_orca_filament_settings({
            "hot_plate_temp": ["60"],
            "cool_plate_temp": ["999"],
        })
    with pytest.raises(ValueError, match="bed_temperature_initial_layer"):
        validate_orca_filament_settings({"bed_temperature_initial_layer": ["nil", "301"]})
    with pytest.raises(ValueError, match="epoxy_resin_plate_temp"):
        validate_orca_filament_settings({"epoxy_resin_plate_temp": "999"})
    with pytest.raises(ValueError, match="filament_flow_ratio"):
        validate_orca_filament_settings({"filament_flow_ratio": ["1", "0"]})
    with pytest.raises(ValueError, match="filament_flow_ratio"):
        validate_orca_filament_settings({"filament_flow_ratio": ["2.1"]})
    with pytest.raises(ValueError, match="filament_retraction_length"):
        validate_orca_filament_settings({"filament_retraction_length": ["20.1"]})
    with pytest.raises(ValueError, match="filament_retraction_speed"):
        validate_orca_filament_settings({"filament_retraction_speed": ["201"]})
    with pytest.raises(ValueError, match="fan_max_speed"):
        validate_orca_filament_settings({"fan_max_speed": ["1001"]})
    with pytest.raises(ValueError, match="fan speed"):
        extract_structured_filament_values({"fan_max_speed": ["50.5"]})


def test_raw_projection_updates_structured_values_and_preserves_explicit_nil():
    assert extract_structured_filament_values({
        "filament_flow_ratio": ["0.92"],
        "fan_min_speed": ["0"],
    }) == {"flow_rate": 92.0, "fan_speed": 0}
    assert extract_structured_filament_values({
        "filament_flow_ratio": ["nil"],
        "filament_retraction_length": ["nil"],
    }) == {"flow_rate": None, "retraction_length": None}


def test_sync_info_accepts_batch_and_individual_export_markers():
    assert _preset_id_from_sync_info("fhub:42:filamenthub") == 42
    assert _preset_id_from_sync_info("filamenthub:preset:42") == 42
    assert _preset_id_from_sync_info("foreign:42") is None
