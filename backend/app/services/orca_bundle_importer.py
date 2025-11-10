"""Import OrcaSlicer system presets into database."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    PrintProfile,
    PrintProfileFilament,
    PrintProfilePrinter,
    Printer,
    PrinterProfile,
)
from app.schemas.orca_bundle import (
    OrcaMachineModel,
    OrcaMachinePreset,
    OrcaProcessPreset,
    OrcaVendorBundle,
)
from app.services.slug_service import generate_unique_slug

LOG = logging.getLogger(__name__)


class OrcaBundleImporter:
    """Importer for OrcaSlicer bundle JSON files."""

    def __init__(self, root_path: Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[3]
        configured_path = Path(root_path or settings.ORCA_SYSTEM_PRESETS_PATH)
        if not configured_path.is_absolute():
            configured_path = (project_root / configured_path).resolve()
        self.root_path = configured_path
        self.project_root = project_root

    async def import_all(self, db: AsyncSession) -> dict[str, Any]:
        """Import all vendor bundles."""
        if not self.root_path.exists():
            raise FileNotFoundError(f"Orca presets path not found: {self.root_path}")

        summary: dict[str, Any] = {"vendors": 0, "printers": 0, "printer_profiles": 0, "print_profiles": 0}
        vendor_files = sorted(self.root_path.glob("*.json"))
        for vendor_file in vendor_files:
            bundle = self._load_json(vendor_file, OrcaVendorBundle)
            vendor_dir = self.root_path / vendor_file.stem
            LOG.info("Importing Orca bundle '%s'", vendor_file.name)
            vendor_result = await self._import_vendor(db=db, vendor=bundle, vendor_dir=vendor_dir)
            summary["vendors"] += 1
            summary["printers"] += vendor_result["printers"]
            summary["printer_profiles"] += vendor_result["printer_profiles"]
            summary["print_profiles"] += vendor_result["print_profiles"]
        return summary

    async def _import_vendor(
        self,
        *,
        db: AsyncSession,
        vendor: OrcaVendorBundle,
        vendor_dir: Path,
    ) -> dict[str, int]:
        counters = {"printers": 0, "printer_profiles": 0, "print_profiles": 0}
        if not vendor_dir.exists():
            LOG.warning("Vendor directory missing: %s", vendor_dir)
            return counters

        printer_lookup = await self._import_machine_models(db, vendor, vendor_dir)
        counters["printers"] = len(printer_lookup)

        process_slug_lookup = await self._import_process_presets(db, vendor, vendor_dir, printer_lookup)
        counters["print_profiles"] = len(process_slug_lookup)

        printer_profile_count = await self._import_machine_presets(
            db=db,
            vendor=vendor,
            vendor_dir=vendor_dir,
            printer_lookup=printer_lookup,
            process_lookup=process_slug_lookup,
        )
        counters["printer_profiles"] = printer_profile_count

        return counters

    async def _import_machine_models(
        self, db: AsyncSession, vendor: OrcaVendorBundle, vendor_dir: Path
    ) -> dict[str, Printer]:
        result: dict[str, Printer] = {}
        for pointer in vendor.machine_model_list:
            model_path = vendor_dir / pointer.sub_path
            machine_model = self._load_json(model_path, OrcaMachineModel)
            printer = await self._upsert_printer(db=db, vendor_name=vendor.name, machine_model=machine_model)
            result[machine_model.name] = printer
        await db.flush()
        return result

    async def _import_process_presets(
        self,
        db: AsyncSession,
        vendor: OrcaVendorBundle,
        vendor_dir: Path,
        printer_lookup: Mapping[str, Printer],
    ) -> dict[str, str]:
        slug_lookup: dict[str, str] = {}
        for pointer in vendor.process_list:
            process_path = vendor_dir / pointer.sub_path
            process = self._load_json(process_path, OrcaProcessPreset)
            profile = await self._upsert_print_profile(
                db=db,
                vendor_name=vendor.name,
                process=process,
                printer_lookup=printer_lookup,
            )
            slug_lookup[process.name] = profile.slug
        await db.flush()
        return slug_lookup

    async def _import_machine_presets(
        self,
        *,
        db: AsyncSession,
        vendor: OrcaVendorBundle,
        vendor_dir: Path,
        printer_lookup: Mapping[str, Printer],
        process_lookup: Mapping[str, str],
    ) -> int:
        count = 0
        for preset_path in self._iter_machine_preset_paths(vendor_dir):
            preset = self._load_json(preset_path, OrcaMachinePreset)
            printer = printer_lookup.get(preset.printer_model or "")
            if not printer:
                LOG.warning(
                    "Printer model '%s' not found for machine preset '%s' (%s)",
                    preset.printer_model,
                    preset.name,
                    vendor.name,
                )
                continue
            profile = await self._upsert_printer_profile(
                db=db,
                vendor_name=vendor.name,
                preset=preset,
                printer=printer,
                default_print_profile_slug=process_lookup.get(preset.default_print_profile or ""),
            )
            count += 1
        await db.flush()
        return count

    async def _upsert_printer(
        self,
        *,
        db: AsyncSession,
        vendor_name: str,
        machine_model: OrcaMachineModel,
    ) -> Printer:
        printer = await self._find_printer(
            db=db,
            vendor_name=vendor_name,
            model_id=machine_model.model_id,
            name=machine_model.name,
        )
        if printer is None:
            slug_source = f"{vendor_name} {machine_model.name}"
            slug = await generate_unique_slug(
                db=db,
                model=Printer,
                source=slug_source,
                fallback="printer",
            )
            printer = Printer(
                name=machine_model.name,
                manufacturer=vendor_name,
                model=machine_model.name,
                slug=slug,
                source="system",
                vendor=vendor_name,
            )
            db.add(printer)

        printer.manufacturer = vendor_name
        printer.model = machine_model.name
        printer.model_id = machine_model.model_id
        printer.family = machine_model.family or printer.family
        printer.technology = machine_model.machine_tech or printer.technology
        printer.source = "system"
        printer.vendor = vendor_name

        default_materials = machine_model.default_materials or []
        if default_materials:
            printer.default_materials = _merge_unique(printer.default_materials, default_materials)

        nozzle_value = _to_float(machine_model.nozzle_diameter)
        if nozzle_value is not None:
            printer.nozzle_diameter = printer.nozzle_diameter or nozzle_value
            printer.nozzle_options = _merge_unique(printer.nozzle_options, [nozzle_value])

        if machine_model.metadata:
            printer.extra_metadata = machine_model.metadata

        return printer

    async def _upsert_printer_profile(
        self,
        *,
        db: AsyncSession,
        vendor_name: str,
        preset: OrcaMachinePreset,
        printer: Printer,
        default_print_profile_slug: str | None,
    ) -> PrinterProfile:
        profile = await self._find_printer_profile(
            db=db,
            vendor_name=vendor_name,
            setting_id=preset.setting_id,
            name=preset.name,
        )
        if profile is None:
            slug = await generate_unique_slug(
                db=db,
                model=PrinterProfile,
                source=preset.name,
                fallback="printer-profile",
            )
            profile = PrinterProfile(
                name=preset.name,
                slug=slug,
                printer_id=printer.id,
                source="system",
                vendor=vendor_name,
                setting_id=preset.setting_id,
            )
            db.add(profile)

        profile.printer_id = printer.id
        profile.description = profile.description
        profile.source = "system"
        profile.vendor = vendor_name
        profile.setting_id = preset.setting_id
        profile.external_id = preset.parameters.get("external_id")
        profile.is_official = True
        profile.active = True
        profile.default_print_profile_slug = default_print_profile_slug or profile.default_print_profile_slug

        nozzle_values = _to_float_list(preset.nozzle_diameter)
        if nozzle_values:
            profile.nozzle_diameters = sorted(set(nozzle_values))
            printer.nozzle_options = _merge_unique(printer.nozzle_options, nozzle_values)

        profile.printable_area = _parse_printable_area(preset.printable_area)
        profile.printable_height_mm = _to_float(preset.printable_height)

        profile.start_gcode = preset.parameters.get("start_gcode") or profile.start_gcode
        profile.end_gcode = preset.parameters.get("end_gcode") or profile.end_gcode

        profile.orcaslicer_settings = _build_machine_settings_dict(preset)
        extra_metadata = dict(preset.parameters)
        profile.extra_metadata = extra_metadata if extra_metadata else None

        return profile

    async def _upsert_print_profile(
        self,
        *,
        db: AsyncSession,
        vendor_name: str,
        process: OrcaProcessPreset,
        printer_lookup: Mapping[str, Printer],
    ) -> PrintProfile:
        profile = await self._find_print_profile(
            db=db,
            vendor_name=vendor_name,
            setting_id=process.setting_id,
            name=process.name,
        )
        if profile is None:
            slug = await generate_unique_slug(
                db=db,
                model=PrintProfile,
                source=process.name,
                fallback="print-profile",
            )
            profile = PrintProfile(
                name=process.name,
                slug=slug,
                source="system",
                vendor=vendor_name,
                setting_id=process.setting_id,
            )
            db.add(profile)

        profile.description = profile.description
        profile.category = _derive_category(process.name)
        profile.source = "system"
        profile.vendor = vendor_name
        profile.setting_id = process.setting_id
        profile.external_id = process.parameters.get("external_id")
        profile.is_official = True
        profile.active = True
        profile.quality_tier = _derive_quality_tier(process.name)
        profile.default_nozzle = _derive_default_nozzle(process.name, process.parameters)
        profile.layer_height_mm = _derive_layer_height(process.parameters)

        profile.compatible_printers = _ensure_list_str(process.parameters.get("compatible_printers"))
        profile.compatible_filaments = _ensure_list_str(process.parameters.get("compatible_filaments"))

        profile.orcaslicer_settings = _build_process_settings_dict(process)
        extra_metadata = dict(process.parameters)
        extra_metadata["compatible_printers_condition"] = process.compatible_printers_condition
        profile.extra_metadata = extra_metadata if extra_metadata else None

        # For now, we do not populate PrintProfilePrinter/Filament junctions.

        return profile

    async def _find_printer(
        self, *, db: AsyncSession, vendor_name: str, model_id: str | None, name: str
    ) -> Printer | None:
        if model_id:
            stmt: Select = select(Printer).where(Printer.model_id == model_id)
        else:
            stmt = select(Printer).where(Printer.vendor == vendor_name, Printer.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_printer_profile(
        self,
        *,
        db: AsyncSession,
        vendor_name: str,
        setting_id: str | None,
        name: str,
    ) -> PrinterProfile | None:
        stmt = select(PrinterProfile).where(PrinterProfile.vendor == vendor_name)
        if setting_id:
            stmt = stmt.where(PrinterProfile.setting_id == setting_id)
        else:
            stmt = stmt.where(PrinterProfile.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_print_profile(
        self,
        *,
        db: AsyncSession,
        vendor_name: str,
        setting_id: str | None,
        name: str,
    ) -> PrintProfile | None:
        stmt = select(PrintProfile).where(PrintProfile.vendor == vendor_name)
        if setting_id:
            stmt = stmt.where(PrintProfile.setting_id == setting_id)
        else:
            stmt = stmt.where(PrintProfile.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def _iter_machine_preset_paths(self, vendor_dir: Path) -> list[Path]:
        machine_dir = vendor_dir / "machine"
        if not machine_dir.exists():
            return []
        paths: list[Path] = []
        for path in sorted(machine_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if data.get("type") == "machine":
                paths.append(path)
        return paths

    def _load_json(self, path: Path, model_type: type[Any]) -> Any:
        if not path.exists():
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8")
        if model_type is dict:
            return json.loads(text)
        return model_type.model_validate_json(text)


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        value_str = str(value).strip()
        return float(value_str)
    except (ValueError, TypeError):
        return None


def _to_float_list(values: Iterable[Any] | None) -> list[float] | None:
    if not values:
        return None
    result = []
    for value in values:
        parsed = _to_float(value)
        if parsed is not None:
            result.append(parsed)
    return result or None


def _parse_printable_area(area: Iterable[str] | None) -> dict[str, float] | None:
    if not area:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for entry in area:
        try:
            x_str, y_str = entry.split("x")
            xs.append(float(x_str))
            ys.append(float(y_str))
        except (ValueError, AttributeError):
            continue
    if not xs or not ys:
        return None
    return {"x_min": min(xs), "x_max": max(xs), "y_min": min(ys), "y_max": max(ys)}


def _build_machine_settings_dict(preset: OrcaMachinePreset) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "type": preset.type,
        "name": preset.name,
        "inherits": preset.inherits,
        "from": preset.source,
        "setting_id": preset.setting_id,
        "instantiation": preset.instantiation,
        "printer_model": preset.printer_model,
        "default_print_profile": preset.default_print_profile,
        "nozzle_diameter": preset.nozzle_diameter,
        "printable_area": preset.printable_area,
        "printable_height": preset.printable_height,
    }
    settings.update(preset.parameters)
    return settings


def _build_process_settings_dict(process: OrcaProcessPreset) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "type": process.type,
        "name": process.name,
        "inherits": process.inherits,
        "from": process.source,
        "setting_id": process.setting_id,
        "instantiation": process.instantiation,
        "compatible_printers_condition": process.compatible_printers_condition,
        "print_settings_id": process.print_settings_id,
    }
    settings.update(process.parameters)
    return settings


def _ensure_list_str(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _derive_layer_height(parameters: Mapping[str, Any]) -> float | None:
    candidate = parameters.get("layer_height")
    layer = _to_float(candidate)
    if layer is not None:
        return layer
    initial = parameters.get("initial_layer_print_height")
    return _to_float(initial)


def _derive_default_nozzle(name: str, parameters: Mapping[str, Any]) -> str | None:
    match = re.search(r"(\d\.\d)\s*nozzle", name.lower())
    if match:
        return match.group(1)
    nozzle = parameters.get("nozzle_diameter")
    if isinstance(nozzle, list) and nozzle:
        return str(nozzle[0])
    if isinstance(nozzle, (str, int, float)):
        return str(nozzle)
    return None


def _derive_quality_tier(name: str) -> str | None:
    lowered = name.lower()
    if "draft" in lowered:
        return "draft"
    if "standard" in lowered:
        return "standard"
    if "optimal" in lowered:
        return "optimal"
    if "highdetail" in lowered or "high detail" in lowered or "extra fine" in lowered or "fine" in lowered:
        return "fine"
    if "superdraft" in lowered or "super draft" in lowered:
        return "superdraft"
    return None


def _derive_category(name: str) -> str | None:
    lowered = name.lower()
    if "support" in lowered:
        return "support"
    if "speed" in lowered:
        return "speed"
    if "quality" in lowered:
        return "quality"
    if "draft" in lowered:
        return "draft"
    if "standard" in lowered:
        return "standard"
    return None


def _merge_unique(existing: Iterable[Any] | None, new_values: Iterable[Any]) -> list[Any]:
    result = list(existing or [])
    for value in new_values:
        if value not in result:
            result.append(value)
    return result


async def run_import() -> dict[str, Any]:
    from app.db.session import AsyncSessionLocal

    importer = OrcaBundleImporter()
    async with AsyncSessionLocal() as session:
        summary = await importer.import_all(session)
        await session.commit()
        return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_import())

