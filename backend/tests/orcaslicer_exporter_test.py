"""Tests for the filament export scope guard.

A filament profile must not carry process-scope keys (OrcaSlicer
`s_Preset_print_options`). The exporter's `orcaslicer_settings` passthrough
drops them so a process setting that ends up in the blob (e.g. via reverse
sync) never leaks into the exported filament JSON.
"""

import pytest

from app.models.filament import Filament
from app.models.preset import Preset
from app.services.orcaslicer_exporter import generate_profile_info, preset_to_orcaslicer_json


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
