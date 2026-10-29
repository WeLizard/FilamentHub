"""Reference of measured filament properties published in manufacturer data sheets.

Each property keeps the manufacturer's number and unit exactly as written; a
value in the property's canonical unit is stored beside it only when the units
convert by definition (GPa to MPa, J/m is not kJ/m²). The same property may be
listed more than once when the conditions differ (printed along or across the
layers, HDT at 0.45 or 1.8 MPa), so conditions are structured, not free text.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

PropertyCategory = Literal["mechanical", "thermal", "physical", "electrical", "optical"]

# Factors to the canonical unit, by definition only.
_PRESSURE = {
    "MPa": 1.0,
    "GPa": 1000.0,
    "N/mm²": 1.0,
    "psi": 0.006894757293168,
    "ksi": 6.894757293168,
}
_TEMPERATURE = {"°C": 1.0}
_PERCENT = {"%": 1.0}

CONDITION_VALUES: dict[str, tuple[str, ...]] = {
    "direction": ("xy", "yx", "xz", "zx", "z", "along_layers", "across_layers", "not_stated"),
    "specimen": ("printed", "injection_moulded", "not_stated"),
    "point": ("yield", "break"),
    "notch": ("notched", "unnotched"),
    "method": ("A", "B", "A50", "A120", "B50", "B120"),
    "scale": ("A", "D"),
}
# Numeric conditions, with their unit in the key name.
NUMERIC_CONDITIONS = frozenset({"load_mpa", "load_n", "load_kg", "temperature_c", "rate_c_per_h"})


@dataclass(frozen=True)
class TechnicalProperty:
    code: str
    category: PropertyCategory
    canonical_unit: str
    units: Mapping[str, float | None]
    conditions: frozenset[str] = frozenset()


def _property(
    code: str,
    category: PropertyCategory,
    canonical_unit: str,
    units: Mapping[str, float | None],
    *conditions: str,
) -> TechnicalProperty:
    return TechnicalProperty(code, category, canonical_unit, units, frozenset(conditions))


_MECHANICAL_TEST = ("direction", "specimen")

TECHNICAL_PROPERTIES: dict[str, TechnicalProperty] = {
    item.code: item
    for item in (
        _property("tensile_strength", "mechanical", "MPa", _PRESSURE, *_MECHANICAL_TEST, "point"),
        _property("tensile_modulus", "mechanical", "MPa", _PRESSURE, *_MECHANICAL_TEST),
        _property("elongation", "mechanical", "%", _PERCENT, *_MECHANICAL_TEST, "point"),
        _property("flexural_strength", "mechanical", "MPa", _PRESSURE, *_MECHANICAL_TEST),
        _property("flexural_modulus", "mechanical", "MPa", _PRESSURE, *_MECHANICAL_TEST),
        _property("compressive_strength", "mechanical", "MPa", _PRESSURE, *_MECHANICAL_TEST),
        _property(
            "impact_charpy", "mechanical", "kJ/m²", {"kJ/m²": 1.0}, *_MECHANICAL_TEST, "notch"
        ),
        # ASTM D256 reports J/m (per notch width), ISO 180 kJ/m²: not convertible.
        _property(
            "impact_izod",
            "mechanical",
            "kJ/m²",
            {"kJ/m²": 1.0, "J/m": None},
            *_MECHANICAL_TEST,
            "notch",
        ),
        _property("shore_hardness", "mechanical", "Shore", {"Shore": 1.0}, "scale"),
        _property("hdt", "thermal", "°C", _TEMPERATURE, "load_mpa", "specimen"),
        _property("vicat", "thermal", "°C", _TEMPERATURE, "method", "load_n", "rate_c_per_h"),
        _property("melting_temperature", "thermal", "°C", _TEMPERATURE),
        _property("glass_transition", "thermal", "°C", _TEMPERATURE),
        _property("service_temperature_max", "thermal", "°C", _TEMPERATURE),
        _property(
            "melt_flow_rate", "physical", "g/10 min", {"g/10 min": 1.0}, "temperature_c", "load_kg"
        ),
        _property(
            "melt_volume_rate",
            "physical",
            "cm³/10 min",
            {"cm³/10 min": 1.0},
            "temperature_c",
            "load_kg",
        ),
        _property("shrinkage", "physical", "%", _PERCENT, "direction"),
        _property("water_absorption", "physical", "%", _PERCENT, "temperature_c"),
        _property("diameter_tolerance", "physical", "mm", {"mm": 1.0, "µm": 0.001}),
        _property("ovality", "physical", "mm", {"mm": 1.0, "µm": 0.001}),
        _property("surface_resistivity", "electrical", "Ω/sq", {"Ω/sq": 1.0, "Ω": None}),
        _property("light_transmission", "optical", "%", _PERCENT),
    )
}


def canonical_value(code: str, unit: str, value: float | None) -> float | None:
    """The value in the canonical unit, or None when the unit has no exact factor."""
    factor = TECHNICAL_PROPERTIES[code].units.get(unit)
    if value is None or factor is None:
        return None
    return round(value * factor, 6)


def _condition_text(value: object) -> str:
    # 10 and 10.0 are one load: the key must not depend on how JSON typed it.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}"
    return str(value)


def technical_property_key(item: dict) -> str:
    """Identity of a measurement within one filament, also used to address its evidence."""
    conditions = item.get("conditions") or {}
    parts = [str(item.get("code") or "")]
    parts += [f"{name}={_condition_text(conditions[name])}" for name in sorted(conditions)]
    standard = " ".join(str(item.get("standard") or "").split())
    if standard:
        parts.append(f"std={standard}")
    return ";".join(parts)
