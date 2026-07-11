"""Tests for the max-volumetric-speed enrichment gate.

filament_max_volumetric_speed lives in the orcaslicer_settings blob, not a model
column. Enrichment fills it from the material default when it is missing or when a
placeholder value (below _MIN_REALISTIC_VOLUMETRIC) leaked in from an imported
profile, but leaves a real value untouched.
"""

from app.models.preset import Preset
from app.services.preset_enrichment_service import enrich_preset


def _preset(settings: dict) -> Preset:
    return Preset(id=1, name="Test PLA", active=True, orcaslicer_settings=settings)


def test_placeholder_volumetric_replaced_with_material_default():
    preset = _preset({"filament_type": ["PLA"], "filament_max_volumetric_speed": ["1"]})
    result = enrich_preset(preset)
    assert preset.orcaslicer_settings["filament_max_volumetric_speed"] == ["12"]
    assert "filament_max_volumetric_speed" in result["filled_fields"]


def test_missing_volumetric_filled():
    preset = _preset({"filament_type": ["PLA"]})
    enrich_preset(preset)
    assert preset.orcaslicer_settings["filament_max_volumetric_speed"] == ["12"]


def test_realistic_volumetric_preserved():
    preset = _preset({"filament_type": ["PLA"], "filament_max_volumetric_speed": ["18"]})
    result = enrich_preset(preset)
    assert preset.orcaslicer_settings["filament_max_volumetric_speed"] == ["18"]
    assert "filament_max_volumetric_speed" in result["skipped_fields"]
