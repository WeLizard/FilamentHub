"""Data-sheet measurements keep the manufacturer's numbers and refuse ambiguous ones."""

import pytest
from pydantic import ValidationError

from app.schemas.filament import FilamentCreate, FilamentTechnicalProperty


def test_original_value_and_unit_stay_and_exact_conversion_is_added():
    item = FilamentTechnicalProperty(
        code="tensile_modulus", value=2.1, tolerance=0.1, unit="GPa", standard="ISO 527"
    )

    assert (item.value, item.unit) == (2.1, "GPa")
    assert item.canonical_value == 2100


def test_units_without_an_exact_factor_get_no_canonical_value():
    # ASTM Izod J/m is per notch width, not kJ/m²: converting would invent a number.
    item = FilamentTechnicalProperty(
        code="impact_izod", value=30, unit="J/m", conditions={"notch": "notched"}
    )

    assert item.canonical_value is None


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "strength", "value": 50, "unit": "MPa"},
        {"code": "hdt", "value": 55, "unit": "MPa"},
        {"code": "hdt", "min": 60, "max": 50, "unit": "°C"},
        {"code": "hdt", "value": 55, "min": 50, "max": 60, "unit": "°C"},
        {"code": "hdt", "value": 55, "unit": "°C", "conditions": {"direction": "xy"}},
        {"code": "shore_hardness", "value": 95, "unit": "Shore", "conditions": {"scale": "C"}},
        {"code": "hdt", "value": 55, "unit": "°C", "conditions": {"load_mpa": "high"}},
    ],
)
def test_unknown_or_inconsistent_measurements_are_rejected(payload):
    with pytest.raises(ValidationError):
        FilamentTechnicalProperty(**payload)


def test_same_property_under_other_conditions_is_kept_but_exact_repeat_is_not():
    hdt_low = {"code": "hdt", "value": 55, "unit": "°C", "conditions": {"load_mpa": 0.45}}
    hdt_high = {"code": "hdt", "value": 50, "unit": "°C", "conditions": {"load_mpa": 1.8}}
    created = FilamentCreate(
        brand_id=1, name="PLA", material_type="PLA", technical_properties=[hdt_low, hdt_high]
    )
    assert len(created.technical_properties) == 2

    with pytest.raises(ValidationError):
        FilamentCreate(
            brand_id=1,
            name="PLA",
            material_type="PLA",
            technical_properties=[hdt_low, {**hdt_low, "value": 56}],
        )
