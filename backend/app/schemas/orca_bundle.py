"""Schemas for parsing OrcaSlicer system preset bundles.

Используются для импорта официальных пресетов (machine/process) в FilamentHub.
"""

from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field, model_validator


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"1", "true", "yes"}:
            return True
        if lower in {"0", "false", "no"}:
            return False
    return None


def _to_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


class OrcaBundlePointer(BaseModel):
    """Элемент списков вида `*_list` (machine/process)."""

    name: str
    sub_path: str


class OrcaVendorBundle(BaseModel):
    """JSON-файл производителя (root)."""

    name: str
    version: str
    description: str | None = None
    force_update: bool = False
    machine_model_list: list[OrcaBundlePointer] = Field(default_factory=list)
    process_list: list[OrcaBundlePointer] = Field(default_factory=list)
    material_list: list[OrcaBundlePointer] = Field(default_factory=list)
    extra_sections: dict[str, list[OrcaBundlePointer]] = Field(default_factory=dict)

    @model_validator(mode="before")
    def _transform(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        raw_force = values.get("force_update")
        if raw_force is not None:
            converted = _to_bool(raw_force)
            if converted is not None:
                values["force_update"] = converted
        # Собираем неизвестные *_list в extra_sections.
        known_lists = {"machine_model_list", "process_list", "material_list"}
        extras: dict[str, list[dict[str, Any]]] = {}
        for key in list(values.keys()):
            if key.endswith("_list") and key not in known_lists:
                extras[key] = values.pop(key) or []
        if extras:
            values["extra_sections"] = extras
        return values
        return values

    @model_validator(mode="after")
    def _cast_extra_sections(cls, values: "OrcaVendorBundle") -> "OrcaVendorBundle":
        if not values.extra_sections:
            return values
        converted: dict[str, list[OrcaBundlePointer]] = {}
        for key, items in values.extra_sections.items():
            new_items: list[OrcaBundlePointer] = []
            for item in items:
                if isinstance(item, OrcaBundlePointer):
                    new_items.append(item)
                else:
                    new_items.append(OrcaBundlePointer.model_validate(item))
            converted[key] = new_items
        values.extra_sections = converted
        return values


class OrcaMachineModel(BaseModel):
    """Файл `machine_model` (базовая модель принтера)."""

    type: Literal["machine_model"]
    name: str
    model_id: str | None = Field(default=None, alias="model_id")
    nozzle_diameter: str | None = None
    machine_tech: str | None = None
    family: str | None = None
    bed_model: str | None = None
    bed_texture: str | None = None
    hotend_model: str | None = None
    default_materials: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    def _normalise(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        default_materials = values.get("default_materials")
        if isinstance(default_materials, str):
            values["default_materials"] = [item.strip() for item in default_materials.split(";") if item.strip()]

        known = {
            "type",
            "name",
            "model_id",
            "nozzle_diameter",
            "machine_tech",
            "family",
            "bed_model",
            "bed_texture",
            "hotend_model",
            "default_materials",
        }
        extras = {k: values[k] for k in list(values.keys()) if k not in known}
        values["metadata"] = extras
        return values


class OrcaMachinePreset(BaseModel):
    """Файл `machine` (конкретный профиль принтера)."""

    type: Literal["machine"]
    name: str
    inherits: str | None = None
    source: str | None = Field(default=None, alias="from")
    setting_id: str | None = None
    instantiation: bool | None = None
    printer_model: str | None = None
    default_print_profile: str | None = None
    nozzle_diameter: list[str] | None = None
    printable_area: list[str] | None = None
    printable_height: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    def _normalise(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        instantiation = _to_bool(values.get("instantiation"))
        if instantiation is not None:
            values["instantiation"] = instantiation

        values["nozzle_diameter"] = _to_list(values.get("nozzle_diameter"))
        values["printable_area"] = _to_list(values.get("printable_area"))
        printable_height = values.get("printable_height")
        if isinstance(printable_height, list):
            values["printable_height"] = printable_height[0] if printable_height else None

        known = {
            "type",
            "name",
            "inherits",
            "from",
            "setting_id",
            "instantiation",
            "printer_model",
            "default_print_profile",
            "nozzle_diameter",
            "printable_area",
            "printable_height",
        }
        extras = {k: values[k] for k in list(values.keys()) if k not in known}
        values["parameters"] = extras
        return values


class OrcaProcessPreset(BaseModel):
    """Файл `process` (print settings)."""

    type: Literal["process"]
    name: str
    inherits: str | None = None
    source: str | None = Field(default=None, alias="from")
    setting_id: str | None = None
    instantiation: bool | None = None
    compatible_printers_condition: str | None = None
    print_settings_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    def _normalise(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        instantiation = _to_bool(values.get("instantiation"))
        if instantiation is not None:
            values["instantiation"] = instantiation

        known = {
            "type",
            "name",
            "inherits",
            "from",
            "setting_id",
            "instantiation",
            "compatible_printers_condition",
            "print_settings_id",
        }
        extras = {k: values[k] for k in list(values.keys()) if k not in known}
        values["parameters"] = extras
        return values


