"""Import OrcaSlicer system presets into database."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from pydantic import ValidationError
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Filament,
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
        self._printer_cache: dict[tuple[str, str], Printer] = {}
        self._printer_profile_cache: dict[tuple[str, str], PrinterProfile] = {}
        self._filament_cache: dict[str, Filament | None] = {}

    async def import_all(self, db: AsyncSession) -> dict[str, Any]:
        """Import all vendor bundles."""
        if not self.root_path.exists():
            raise FileNotFoundError(f"Orca presets path not found: {self.root_path}")

        summary: dict[str, Any] = {
            "vendors": 0,
            "printers": 0,
            "printer_profiles": 0,
            "print_profiles": 0,
            "common_profiles": 0,
        }
        vendor_files = sorted(self.root_path.glob("*.json"))
        for vendor_file in vendor_files:
            try:
                bundle = self._load_json(vendor_file, OrcaVendorBundle)
            except ValidationError:
                # Корень bundle.zip содержит не только vendor-файлы, но и служебные
                # (blacklist.json и т.п.) без обязательных name/version. Пропускаем.
                LOG.info("Skipping non-vendor file in bundle root: %s", vendor_file.name)
                continue
            vendor_dir = self.root_path / vendor_file.stem
            LOG.info("Importing Orca bundle '%s'", vendor_file.name)
            vendor_result = await self._import_vendor(db=db, vendor=bundle, vendor_dir=vendor_dir)
            summary["vendors"] += 1
            summary["printers"] += vendor_result["printers"]
            summary["printer_profiles"] += vendor_result["printer_profiles"]
            summary["print_profiles"] += vendor_result["print_profiles"]
            summary["common_profiles"] += vendor_result.get("common_profiles", 0)
        
        # ВАЖНО: Синхронизируем ВСЕ системные принтеры после импорта всех vendor'ов
        # Это гарантирует, что все принтеры получат правильные данные из профилей
        # даже если они были созданы в одном vendor, а профили - в другом
        LOG.info("Синхронизация метаданных для всех системных принтеров...")
        all_system_printers = await db.execute(
            select(Printer).where(Printer.source == "system")
        )
        all_printers = all_system_printers.scalars().all()
        printer_lookup_all = {printer.name: printer for printer in all_printers}
        await self._sync_printer_metadata_from_profiles(db, printer_lookup_all)
        LOG.info("Синхронизация завершена для %d принтеров", len(printer_lookup_all))
        
        return summary

    async def _import_vendor(
        self,
        *,
        db: AsyncSession,
        vendor: OrcaVendorBundle,
        vendor_dir: Path,
    ) -> dict[str, int]:
        counters = {"printers": 0, "printer_profiles": 0, "print_profiles": 0, "common_profiles": 0}
        if not vendor_dir.exists():
            LOG.warning("Vendor directory missing: %s", vendor_dir)
            return counters

        # Сначала импортируем common-профили (они нужны для наследования)
        common_profile_count = await self._import_common_profiles(
            db=db,
            vendor=vendor,
            vendor_dir=vendor_dir,
        )
        counters["common_profiles"] = common_profile_count

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

        # Обновляем printer.extra_metadata данными из printer_profiles (с разрешением наследования)
        await self._sync_printer_metadata_from_profiles(db, printer_lookup)

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
            self._printer_cache[(vendor.name, machine_model.name)] = printer
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

    async def _import_common_profiles(
        self,
        *,
        db: AsyncSession,
        vendor: OrcaVendorBundle,
        vendor_dir: Path,
    ) -> int:
        """Импортировать common-профили (fdm_machine_common, fdm_klipper_common, и т.д.)."""
        count = 0
        for preset_path in self._iter_machine_preset_paths(vendor_dir):
            preset = self._load_json(preset_path, OrcaMachinePreset)
            # Common-профили имеют instantiation="false" или отсутствует printer_model
            if preset.instantiation == "false" or not preset.printer_model:
                profile = await self._upsert_common_profile(
                    db=db,
                    vendor_name=vendor.name,
                    preset=preset,
                )
                count += 1
                self._printer_profile_cache[(vendor.name, preset.name)] = profile
        await db.flush()
        return count

    async def _import_machine_presets(
        self,
        *,
        db: AsyncSession,
        vendor: OrcaVendorBundle,
        vendor_dir: Path,
        printer_lookup: Mapping[str, Printer],
        process_lookup: Mapping[str, str],
    ) -> int:
        """Импортировать обычные профили принтеров (с printer_model)."""
        count = 0
        for preset_path in self._iter_machine_preset_paths(vendor_dir):
            preset = self._load_json(preset_path, OrcaMachinePreset)
            # Пропускаем common-профили (они уже импортированы)
            if preset.instantiation == "false" or not preset.printer_model:
                continue
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
            self._printer_profile_cache[(vendor.name, preset.name)] = profile
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
        display_name, model_name = _normalize_model_name(vendor_name, machine_model.name)

        if printer is None:
            slug_source = f"{vendor_name} {machine_model.name}"
            slug = await generate_unique_slug(
                db=db,
                model=Printer,
                source=slug_source,
                fallback="printer",
            )
            printer = Printer(
                name=display_name,
                manufacturer=vendor_name,
                model=model_name,
                slug=slug,
                source="system",
                vendor=vendor_name,
            )
            db.add(printer)

        printer.manufacturer = vendor_name
        printer.name = display_name
        printer.model = model_name
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
            merged_metadata = dict(printer.extra_metadata or {})
            merged_metadata.update(machine_model.metadata)
            printer.extra_metadata = merged_metadata or None

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

        if profile.printable_area:
            x_min = profile.printable_area.get("x_min", 0.0)
            x_max = profile.printable_area.get("x_max", 0.0)
            y_min = profile.printable_area.get("y_min", 0.0)
            y_max = profile.printable_area.get("y_max", 0.0)
            width = max(0.0, x_max - x_min)
            depth = max(0.0, y_max - y_min)
            if width > 0:
                printer.build_volume_x = width
            if depth > 0:
                printer.build_volume_y = depth

        if profile.printable_height_mm and profile.printable_height_mm > 0:
            printer.build_volume_z = profile.printable_height_mm

        machine_start_gcode = (
            preset.parameters.get("machine_start_gcode")
            or preset.parameters.get("start_gcode")
        )
        start_gcode_value = _normalize_gcode(machine_start_gcode)
        if start_gcode_value:
            profile.start_gcode = start_gcode_value

        machine_end_gcode = (
            preset.parameters.get("machine_end_gcode")
            or preset.parameters.get("end_gcode")
        )
        end_gcode_value = _normalize_gcode(machine_end_gcode)
        if end_gcode_value:
            profile.end_gcode = end_gcode_value

        profile.orcaslicer_settings = _build_machine_settings_dict(preset)
        full_metadata = dict(profile.extra_metadata or {})
        full_metadata.update(preset.parameters)
        if preset.default_print_profile:
            full_metadata.setdefault("default_print_profile", preset.default_print_profile)
        if preset.printer_model:
            full_metadata.setdefault("printer_model", preset.printer_model)
        if preset.nozzle_diameter:
            full_metadata.setdefault("nozzle_diameter", preset.nozzle_diameter)
        profile.extra_metadata = full_metadata or None

        return profile

    async def _upsert_common_profile(
        self,
        *,
        db: AsyncSession,
        vendor_name: str,
        preset: OrcaMachinePreset,
    ) -> PrinterProfile:
        """Создать или обновить common-профиль (без привязки к принтеру)."""
        # Для common-профилей ищем по имени в ЛЮБОМ vendor'е
        # (common-профили могут быть одинаковыми в разных vendor'ах)
        # Предпочитаем Custom vendor, затем первый найденный
        result = await db.execute(
            select(PrinterProfile)
            .where(
                PrinterProfile.name == preset.name,
                PrinterProfile.source == "system",
                PrinterProfile.printer_id.is_(None),  # Только common-профили (без принтера)
            )
            .order_by(
                (PrinterProfile.vendor == "Custom").desc(),  # Custom в первую очередь
                PrinterProfile.vendor.asc(),  # Затем по алфавиту
                PrinterProfile.id.asc(),  # Затем по ID
            )
        )
        profile = result.scalars().first()
        
        if profile is None:
            # Профиль не найден - создаем новый
            slug = await generate_unique_slug(
                db=db,
                model=PrinterProfile,
                source=preset.name,
                fallback="printer-profile",
            )
            profile = PrinterProfile(
                name=preset.name,
                slug=slug,
                printer_id=None,  # Common-профили не привязаны к принтеру
                source="system",
                vendor=vendor_name,
                setting_id=preset.setting_id,
            )
            db.add(profile)
        else:
            # Профиль уже существует - обновляем его, если он из того же vendor'а
            # Или оставляем как есть, если он из другого vendor'а (предпочитаем Custom)
            # Обновляем vendor только если текущий профиль не из Custom
            if profile.vendor != "Custom" and vendor_name == "Custom":
                # Обновляем vendor на Custom (более предпочтительный)
                profile.vendor = vendor_name

        profile.printer_id = None  # Убеждаемся, что common-профиль не привязан к принтеру
        profile.source = "system"
        profile.vendor = vendor_name
        profile.setting_id = preset.setting_id
        profile.external_id = preset.parameters.get("external_id")
        profile.is_official = True
        profile.active = True

        # Для common-профилей не устанавливаем printable_area и printable_height
        # (они могут различаться для разных принтеров)

        machine_start_gcode = (
            preset.parameters.get("machine_start_gcode")
            or preset.parameters.get("start_gcode")
        )
        start_gcode_value = _normalize_gcode(machine_start_gcode)
        if start_gcode_value:
            profile.start_gcode = start_gcode_value

        machine_end_gcode = (
            preset.parameters.get("machine_end_gcode")
            or preset.parameters.get("end_gcode")
        )
        end_gcode_value = _normalize_gcode(machine_end_gcode)
        if end_gcode_value:
            profile.end_gcode = end_gcode_value

        profile.orcaslicer_settings = _build_machine_settings_dict(preset)
        full_metadata = dict(profile.extra_metadata or {})
        full_metadata.update(preset.parameters)
        if preset.default_print_profile:
            full_metadata.setdefault("default_print_profile", preset.default_print_profile)
        if preset.nozzle_diameter:
            full_metadata.setdefault("nozzle_diameter", preset.nozzle_diameter)
        profile.extra_metadata = full_metadata or None

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

        await self._sync_print_profile_links(
            db=db,
            profile=profile,
            vendor_name=vendor_name,
            compatible_printers=profile.compatible_printers,
            compatible_printers_condition=process.compatible_printers_condition,
            compatible_filaments=profile.compatible_filaments,
        )

        return profile

    async def _sync_print_profile_links(
        self,
        *,
        db: AsyncSession,
        profile: PrintProfile,
        vendor_name: str,
        compatible_printers: list[str] | None,
        compatible_printers_condition: str | None,
        compatible_filaments: list[str] | None,
    ) -> None:
        """Synchronise junction tables for printer/filament compatibility."""
        await profile.awaitable_attrs.printer_links
        await profile.awaitable_attrs.filament_links
        profile.printer_links.clear()
        profile.filament_links.clear()

        printer_slugs: set[str] = set()
        if compatible_printers:
            for entry in compatible_printers:
                name = (entry or "").strip()
                if not name:
                    continue

                printer_profile = self._printer_profile_cache.get((vendor_name, name))
                if not printer_profile:
                    result = await db.execute(select(PrinterProfile).where(PrinterProfile.name == name))
                    printer_profile = result.scalar_one_or_none()

                printer: Printer | None = None
                if printer_profile:
                    if printer_profile.printer is not None:
                        printer = printer_profile.printer
                    elif printer_profile.printer_id:
                        printer = await db.get(Printer, printer_profile.printer_id)

                if not printer:
                    base_name = _extract_base_printer_name(name)
                    if base_name:
                        printer = self._printer_cache.get((vendor_name, base_name))
                        if not printer:
                            result = await db.execute(select(Printer).where(Printer.name == base_name))
                            printer = result.scalar_one_or_none()
                        if not printer:
                            result = await db.execute(select(Printer).where(Printer.model == base_name))
                            printer = result.scalar_one_or_none()

                printer_slug = (printer.slug if printer else _slugify_string(name))[:200]
                if printer_slug in printer_slugs:
                    continue
                printer_slugs.add(printer_slug)

                profile.printer_links.append(
                    PrintProfilePrinter(
                        printer_id=printer.id if printer else None,
                        printer_slug=printer_slug,
                        relation_type="explicit",
                    )
                )

        condition = (compatible_printers_condition or "").strip()
        if condition:
            condition_slug = _slugify_string(condition, fallback="condition")[:200]
            if condition_slug in printer_slugs:
                condition_slug = f"{condition_slug}-{len(printer_slugs)+1}"[:200]
            profile.printer_links.append(
                PrintProfilePrinter(
                    printer_id=None,
                    printer_slug=condition_slug,
                    relation_type="condition",
                    condition=condition,
                )
            )

        filament_slugs: set[str] = set()
        if compatible_filaments:
            for entry in compatible_filaments:
                name = (entry or "").strip()
                if not name:
                    continue
                filament_slug = _slugify_string(name)[:200]
                if filament_slug in filament_slugs:
                    continue

                filament = await self._resolve_filament(db=db, identifier=name)
                profile.filament_links.append(
                    PrintProfileFilament(
                        filament_id=filament.id if filament else None,
                        filament_slug=filament_slug,
                        relation_type="explicit",
                    )
                )
                filament_slugs.add(filament_slug)

        await db.flush()

    async def _resolve_filament(self, *, db: AsyncSession, identifier: str) -> Filament | None:
        """Try to find filament by full name or trimmed variant, cached for speed."""
        if identifier in self._filament_cache:
            return self._filament_cache[identifier]

        candidates = [identifier]
        if "@" in identifier:
            candidates.append(identifier.split("@", 1)[0].strip())

        for candidate in candidates:
            if not candidate:
                continue
            result = await db.execute(select(Filament).where(Filament.name == candidate))
            filament = result.scalar_one_or_none()
            if filament:
                self._filament_cache[identifier] = filament
                return filament

        self._filament_cache[identifier] = None
        return None

    async def _resolve_inheritance(
        self,
        db: AsyncSession,
        profile: PrinterProfile,
        visited: set[str] | None = None,
    ) -> dict[str, Any]:
        """
        Рекурсивно разрешить наследование профиля.
        
        Объединяет настройки из всех родительских профилей в порядке наследования:
        - fdm_machine_common (базовый)
        - fdm_klipper_common (наследуется от fdm_machine_common)
        - fdm_toolchanger_common (наследуется от fdm_klipper_common)
        - MyKlipper 0.2 nozzle (наследуется от fdm_klipper_common)
        
        Возвращает объединенный словарь настроек.
        """
        if visited is None:
            visited = set()
        
        # Предотвращаем циклические зависимости
        profile_key = f"{profile.vendor}:{profile.name}"
        if profile_key in visited:
            LOG.warning(
                "Circular inheritance detected for profile '%s' (vendor: '%s')",
                profile.name,
                profile.vendor,
            )
            return {}
        visited.add(profile_key)

        # Начинаем с настроек текущего профиля
        merged_settings = dict(profile.orcaslicer_settings or {})
        
        # Получаем имя родительского профиля из поля inherits
        parent_name = merged_settings.get("inherits")
        if not parent_name:
            # Нет родителя - возвращаем настройки текущего профиля
            # Удаляем служебное поле _inherits_chain, если оно есть
            merged_settings.pop("_inherits_chain", None)
            return merged_settings
        
        # Ищем родительский профиль в базе данных
        # Родительский профиль может быть в том же vendor или в другом
        # Сначала ищем в том же vendor, потом ищем без vendor (общие профили)
        parent_profile: PrinterProfile | None = None
        
        # Поиск 1: В том же vendor
        result = await db.execute(
            select(PrinterProfile)
            .where(
                PrinterProfile.vendor == profile.vendor,
                PrinterProfile.name == parent_name,
                PrinterProfile.source == "system",
            )
        )
        parent_profile = result.scalar_one_or_none()
        
        # Поиск 2: В любом vendor (общие профили типа fdm_machine_common)
        # Может быть несколько профилей с одним именем в разных vendor'ах
        # Предпочитаем "Custom" vendor, затем по алфавиту
        if not parent_profile:
            result = await db.execute(
                select(PrinterProfile)
                .where(
                    PrinterProfile.name == parent_name,
                    PrinterProfile.source == "system",
                )
                .order_by(
                    (PrinterProfile.vendor == "Custom").desc(),  # Custom в первую очередь
                    PrinterProfile.vendor.asc(),  # Затем по алфавиту
                    PrinterProfile.id.asc(),  # Затем по ID (стабильный порядок)
                )
            )
            parent_profile = result.scalars().first()  # Берем первый из отсортированных
        
        if not parent_profile:
            LOG.warning(
                "Parent profile '%s' not found for profile '%s' (vendor: '%s')",
                parent_name,
                profile.name,
                profile.vendor,
            )
            return merged_settings
        
        # Рекурсивно разрешаем наследование для родительского профиля
        parent_settings = await self._resolve_inheritance(db, parent_profile, visited)
        
        # Объединяем настройки: родительские настройки внизу, дочерние настройки поверх
        # (дочерние настройки перезаписывают родительские)
        final_settings = {}
        final_settings.update(parent_settings)
        final_settings.update(merged_settings)
        
        # Сохраняем информацию о наследовании для отладки
        final_settings["_inherits_chain"] = parent_settings.get("_inherits_chain", []) + [parent_name]
        
        return final_settings

    async def _sync_printer_metadata_from_profiles(
        self,
        db: AsyncSession,
        printer_lookup: Mapping[str, Printer],
    ) -> None:
        """Синхронизировать printer.extra_metadata данными из printer_profiles с разрешением наследования."""
        # Служебные поля, которые НЕ нужно переносить в printer.extra_metadata
        # (это поля для внутренней работы OrcaSlicer, не используются в форме)
        EXCLUDE_FIELDS = {
            "type",  # Всегда "machine"
            "name",  # Имя профиля принтера (не принтера)
            "inherits",  # Наследование профилей (уже разрешено)
            "from",  # Источник профиля
            "setting_id",  # ID настроек
            "instantiation",  # Флаг инстанцирования
            "printer_model",  # Уже есть в printer.model
            "default_print_profile",  # Уже есть в printer_profile.default_print_profile_slug
            "nozzle_diameter",  # Уже есть в printer.nozzle_diameter и printer.nozzle_options
            "printable_area",  # Уже есть в printer_profile.printable_area
            "printable_height",  # Уже есть в printer_profile.printable_height_mm и printer.build_volume_z
            "_inherits_chain",  # Служебное поле для отладки
        }


        for printer in printer_lookup.values():
            # Получаем все printer_profiles для этого принтера
            result = await db.execute(
                select(PrinterProfile)
                .where(PrinterProfile.printer_id == printer.id, PrinterProfile.source == "system")
                .order_by(PrinterProfile.id.asc())
            )
            profiles = result.scalars().all()

            # УМНАЯ СИСТЕМА: Обрабатываем принтеры с профилями и без профилей
            if not profiles:
                # У принтера нет профилей - устанавливаем значения по умолчанию
                # Это гарантирует, что все принтеры будут автозаполнены
                merged_metadata = dict(printer.extra_metadata or {})
                if 'printer_structure' not in merged_metadata:
                    merged_metadata['printer_structure'] = 'undefine'
                printer.extra_metadata = merged_metadata if merged_metadata else None
                continue

            # Берем данные из первого профиля и разрешаем наследование
            first_profile = profiles[0]
            
            # Разрешаем наследование: рекурсивно объединяем с родительскими профилями
            # Теперь resolved_settings содержит ВСЕ поля из профиля и всех его родительских профилей
            resolved_settings = await self._resolve_inheritance(db, first_profile)
            
            # УМНАЯ СИСТЕМА: Создаем merged_metadata ИЗ resolved_settings
            # НЕ используем существующий printer.extra_metadata, чтобы не потерять данные из исходников
            # Если поле есть в resolved_settings, это означает, что оно явно задано в исходниках
            # (даже если это пустая строка "" или пустой массив [])
            # 
            # Принцип: система должна быть "умной" и заполнять все значения из исходников,
            # независимо от типа данных или значения
            merged_metadata = {}
            for key, value in resolved_settings.items():
                # Пропускаем служебные поля
                if key in EXCLUDE_FIELDS:
                    continue

                # Пропускаем None значения - это означает отсутствие поля
                if value is None:
                    continue

                # УМНАЯ ЛОГИКА: сохраняем ВСЕ поля из resolved_settings
                # Это позволяет системе автоматически заполнять все значения из исходников
                # независимо от типа данных (строка, массив, число, булево, и т.д.)
                merged_metadata[key] = value

            # Переносим поля из extra_metadata профиля (если их еще нет в merged_metadata)
            # Это дополнительные поля, которые могут быть заданы в профиле напрямую
            profile_metadata = first_profile.extra_metadata or {}
            for key, value in profile_metadata.items():
                if key in EXCLUDE_FIELDS:
                    continue
                if key in merged_metadata:
                    # Уже есть в merged_metadata (из resolved_settings), не перезаписываем
                    continue
                if value is None:
                    # None означает отсутствие значения
                    continue
                # УМНАЯ ЛОГИКА: сохраняем все значения из extra_metadata профиля
                # Если поле есть в extra_metadata, оно должно попадать в printer.extra_metadata
                merged_metadata[key] = value

            # УМНАЯ СИСТЕМА: Заполняем обязательные поля значениями по умолчанию, если их нет в исходниках
            # Это гарантирует, что все принтеры будут автозаполнены, даже если некоторые поля
            # отсутствуют в исходниках OrcaSlicer
            #
            # printer_structure - если не задано в исходниках, используем "undefine" (как в OrcaSlicer)
            # Это значение используется в OrcaSlicer для принтеров без явно заданной структуры
            if 'printer_structure' not in merged_metadata:
                merged_metadata['printer_structure'] = 'undefine'

            # Обновляем printer.extra_metadata
            printer.extra_metadata = merged_metadata if merged_metadata else None

        await db.flush()

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


def _normalize_gcode(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        lines = [str(item).strip() for item in value if item not in (None, "")]
        filtered = [line for line in lines if line]
        return "\n".join(filtered) or None
    text = str(value).strip()
    return text or None


def _normalize_model_name(vendor: str | None, raw_name: str | None) -> tuple[str, str]:
    """Вернуть пару (display_name, model_name) без дублирования производителя."""
    vendor = (vendor or "").strip()
    name = (raw_name or "").strip()
    if not name:
        return vendor or "Unknown Printer", raw_name or "Unknown"

    simplified = re.sub(r"\s+", " ", name)
    model_only = simplified
    if vendor:
        vendor_lower = vendor.lower()
        simplified_lower = simplified.lower()
        if simplified_lower.startswith(vendor_lower):
            model_only = simplified[len(vendor):].strip()
    model_only = re.sub(r"\s+", " ", model_only).strip()
    display = f"{vendor} {model_only}".strip() if vendor else simplified
    return display or simplified, model_only or simplified


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

    # НЕ добавляем значения по умолчанию для полей, которых нет в JSON
    # Это важно для наследования: если поле отсутствует в JSON, оно должно
    # браться из родительского профиля через наследование, а не заменяться значением по умолчанию
    # 
    # OrcaSlicer сам обработает отсутствующие поля через механизм наследования
    # Мы сохраняем только те поля, которые явно указаны в JSON профиле

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


def _extract_base_printer_name(name: str) -> str:
    """Return base printer name without nozzle suffixes or speed qualifiers."""
    stripped = re.sub(r"\([^)]*nozzle[^)]*\)", "", name, flags=re.IGNORECASE)
    stripped = re.sub(r"\b\d+(\.\d+)?\s*nozzle\b", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bdual\b", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped


def _slugify_string(value: str, fallback: str = "item") -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or fallback


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

