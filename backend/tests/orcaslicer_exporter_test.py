"""Tests for the OrcaSlicer filament export contract.

Two guards live here. A filament profile must not carry process-scope keys
(OrcaSlicer `s_Preset_print_options`). And every exported value must survive
Orca's config loader, which accepts only a JSON string or an array of strings
per option and drops the entire profile otherwise — the observed cause of
managed presets silently missing from OrcaSlicer.
"""

import json
from copy import deepcopy

import pytest

from app.models.filament import Filament
from app.models.preset import Preset
from app.services.orcaslicer_exporter import generate_profile_info, preset_to_orcaslicer_json
from app.services.profile_validator import (
    orca_transport_violations,
    validate_orca_transport_shapes,
)


def _filament() -> Filament:
    return Filament(
        id=1,
        name="Test PLA",
        material_type="PLA",
        diameter=1.75,
        density=1.24,
        color_hex="#FF0000",
    )


def _preset(orcaslicer_settings: dict) -> Preset:
    return Preset(
        id=1,
        name="Test [fh]",
        extruder_temp=210,
        bed_temp=60,
        fan_speed=50,
        flow_rate=100,
        retraction_length=5.0,
        retraction_speed=45.0,
        active=True,
        orcaslicer_settings=orcaslicer_settings,
    )


@pytest.mark.asyncio
async def test_process_keys_are_dropped_from_filament_export():
    preset = _preset({
        "layer_height": ["0.2"],            # process-scope — must be dropped
        "print_speed": ["80"],              # process-scope — must be dropped
        "sparse_infill_density": ["15%"],   # process-scope — must be dropped
        "filament_max_volumetric_speed": ["15"],  # filament-scope — must stay
    })

    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)

    assert "layer_height" not in profile
    assert "print_speed" not in profile
    assert "sparse_infill_density" not in profile
    assert profile.get("filament_max_volumetric_speed") == ["15"]


@pytest.mark.asyncio
async def test_filament_scope_keys_survive():
    preset = _preset({"pressure_advance": ["0.02"], "filament_soluble": ["0"]})

    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)

    assert profile.get("pressure_advance") == ["0.02"]
    assert profile.get("filament_soluble") == ["0"]
    assert profile.get("type") == "filament"


@pytest.mark.asyncio
async def test_unknown_transportable_fields_keep_their_exact_json_shape():
    # A field FilamentHub has not reviewed yet is shipped byte-identical: not
    # renamed, not re-shaped, not wrapped into an array.
    untouched = {
        "future_scalar": "7.25",
        "future_vector": ["left", "2", "0"],
        "future_empty_vector": [],
    }

    profile = await preset_to_orcaslicer_json(
        _preset(untouched), _filament(), db=None
    )

    for key, value in untouched.items():
        assert profile[key] == value
        assert type(profile[key]) is type(value)


@pytest.mark.asyncio
async def test_unknown_untransportable_fields_are_withheld_instead_of_guessed():
    # Orca's loader aborts the whole file on a number, boolean, null or object,
    # so an unreviewed field in one of those shapes cannot be shipped. It must
    # be withheld rather than converted on a guess — the stored blob stays the
    # round-trip authority.
    preset = _preset({
        "future_number": 7.25,
        "future_bool": True,
        "future_object": {"mode": "adaptive", "levels": [1, 3]},
        "future_nullable": None,
        "future_mixed_vector": ["left", 2],
    })

    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)

    for key in (
        "future_number",
        "future_bool",
        "future_object",
        "future_nullable",
        "future_mixed_vector",
    ):
        assert key not in profile
        assert key in preset.orcaslicer_settings


@pytest.mark.asyncio
async def test_known_vector_fields_are_normalized_to_arrays_of_strings():
    # The host Preset API hands the plugin native Python values, so a
    # round-tripped blob carries numeric arrays and scalars. Orca rejected real
    # managed presets over exactly these: "invalid json array for fan_max_speed",
    # "invalid json array for filament_max_volumetric_speed", and a numeric
    # scalar pressure_advance.
    preset = _preset({
        "fan_max_speed": [100],
        "filament_max_volumetric_speed": 10,
        "pressure_advance": 0.025,
        "filament_diameter": [1.75],
        "filament_soluble": [False],
        "filament_retraction_length": [None],
    })

    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)

    assert profile["fan_max_speed"] == ["100"]
    assert profile["filament_max_volumetric_speed"] == ["10"]
    assert profile["pressure_advance"] == ["0.025"]
    assert profile["filament_diameter"] == ["1.75"]
    assert profile["filament_soluble"] == ["0"]
    # Orca's own sentinel for an unset entry of a nullable vector option.
    assert profile["filament_retraction_length"] == ["nil"]


@pytest.mark.asyncio
async def test_enrichment_metadata_never_reaches_orcaslicer():
    # `enrichment` is FilamentHub bookkeeping stored in the settings blob. Orca
    # logged "invalid json type for enrichment" and dropped the whole preset.
    preset = _preset({
        "enrichment": {"material_type": "PETG", "confidence": 0.8},
        "filament_max_volumetric_speed": ["18"],
    })

    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)

    assert "enrichment" not in profile
    assert preset.orcaslicer_settings["enrichment"] == {
        "material_type": "PETG",
        "confidence": 0.8,
    }


@pytest.mark.asyncio
async def test_export_never_mutates_the_stored_settings_blob():
    stored = {
        "enrichment": {"material_type": "PETG"},
        "fan_max_speed": [100],
        "future_object": {"levels": [1, 3]},
        "layer_height": ["0.2"],
        "nozzle_temperature": [245],
    }
    preset = _preset(stored)
    snapshot = deepcopy(stored)

    await preset_to_orcaslicer_json(preset, _filament(), db=None)
    await preset_to_orcaslicer_json(preset, _filament(), db=None)

    assert preset.orcaslicer_settings == snapshot


@pytest.mark.asyncio
async def test_export_is_stable_across_a_full_orcaslicer_round_trip():
    # FH -> export -> what the plugin writes and pushes back -> import -> export.
    # The second export must be transportable and must still carry the unknown
    # field the site has never reviewed.
    preset = _preset({
        "enrichment": {"material_type": "PETG"},
        "fan_max_speed": [100],
        "filament_max_volumetric_speed": 10,
        "future_setting": ["keep me"],
    })

    exported = await preset_to_orcaslicer_json(preset, _filament(), db=None)
    assert orca_transport_violations(exported) == []

    # The plugin serializes the payload to disk and pushes the parsed file back.
    reimported = json.loads(json.dumps(exported))
    imported_preset = _preset(reimported)
    reexported = await preset_to_orcaslicer_json(imported_preset, _filament(), db=None)

    assert reexported == exported
    assert reexported["future_setting"] == ["keep me"]
    assert "enrichment" not in reexported


def test_strict_transport_validation_rejects_a_profile_orcaslicer_would_drop():
    with pytest.raises(ValueError, match="fan_max_speed"):
        validate_orca_transport_shapes({"name": "X", "fan_max_speed": [100]})


@pytest.mark.asyncio
async def test_identity_name_stays_a_scalar_string():
    # A reverse-synced blob carries name/filament_settings_id/ids. The array-wrapping
    # passthrough must NOT re-process them, or the scalar `name` becomes a one-element
    # list and the plugin rejects the export ("Preset name must be a non-empty string").
    preset = _preset({
        "name": "Stale Name From Orca",
        "filament_settings_id": ["Stale Name From Orca"],
        "setting_id": "STALE",
        "type": "filament",
    })

    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)

    assert isinstance(profile["name"], str)
    assert profile["name"] == "Test [fh]"          # authoritative preset.name, unwrapped
    assert profile["setting_id"] == "FHUB000001"   # authoritative id, not the stale blob
    # Orca owns filament_id as an inherited material-family id. Exact FH
    # identity is added to produced G-code by the plugin's post-process hook.
    assert "filament_id" not in profile


@pytest.mark.asyncio
async def test_catalogue_colour_overrides_conflicting_orca_colour_keys():
    preset = _preset({
        "default_filament_colour": ["#00FF00"],
        "filament_colour": ["#0000FF"],
    })

    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)

    assert profile["default_filament_colour"] == ["#FF0000"]
    assert profile["filament_colour"] == ["#FF0000"]


@pytest.mark.asyncio
async def test_compat_context_exported_as_provenance():
    preset = _preset({})
    preset.compat_context = {"nozzle_type": "CHT", "plate": "textured"}
    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)
    assert '"nozzle_type": "CHT"' in profile["fhub_compat_context"]


@pytest.mark.asyncio
async def test_compat_context_absent_when_unset():
    profile = await preset_to_orcaslicer_json(_preset({}), _filament(), db=None)
    assert "fhub_compat_context" not in profile


@pytest.mark.asyncio
async def test_required_nozzle_hrc_exported_from_material():
    # Nozzle hardness is a material property — exported on the profile from the filament.
    fil = _filament()
    fil.required_nozzle_hrc = 50
    profile = await preset_to_orcaslicer_json(_preset({}), fil, db=None)
    assert profile.get("required_nozzle_HRC") == ["50"]


@pytest.mark.asyncio
async def test_structured_flow_ratio_keeps_orca_precision():
    preset = _preset({})
    preset.flow_rate = 92.6
    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)
    assert profile["filament_flow_ratio"] == ["0.926"]


@pytest.mark.asyncio
async def test_structured_retraction_preserves_zero_and_fractional_speed():
    preset = _preset({})
    preset.retraction_length = 0
    preset.retraction_speed = 0.4

    profile = await preset_to_orcaslicer_json(preset, _filament(), db=None)

    assert profile["filament_retraction_length"] == ["0"]
    assert profile["filament_retraction_speed"] == ["0.4"]


def test_info_marker_identifies_every_filamenthub_managed_preset():
    preset = _preset({})
    preset.user_id = None

    info = generate_profile_info(preset, _filament())

    assert "sync_info = filamenthub:preset:1" in info
