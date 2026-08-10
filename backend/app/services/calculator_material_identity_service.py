"""Resolve stable slicer material identifiers to FilamentHub catalog records."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament import Filament
from app.models.preset import Preset
from app.schemas.calculator import (
    CalculatorGcodeParseResponse,
    CalculatorMaterialIdentityResolution,
    CalculatorParsedMaterial,
)
from app.services.slicer_identity_access import (
    visible_material_presets,
    visible_print_profile_ids,
    visible_printer_profile_ids,
)

_FILAMENTHUB_FILAMENT_ID_RE = re.compile(
    r"^FHUB(?:_F_)?(\d+)$",
    re.IGNORECASE,
)


def _stable_id(value: str | None) -> str | None:
    normalized = (value or "").strip().strip('"')
    return normalized or None


def _single_preset_id(presets: list[Preset], filament_id: int) -> int | None:
    matching_ids = {preset.id for preset in presets if preset.filament_id == filament_id}
    return next(iter(matching_ids)) if len(matching_ids) == 1 else None


def _resolution_from_presets(
    *,
    stable_id: str,
    presets: list[Preset],
    source: str,
) -> CalculatorMaterialIdentityResolution | None:
    candidate_filament_ids = sorted(
        {preset.filament_id for preset in presets if preset.filament_id is not None}
    )
    if not candidate_filament_ids:
        return None
    if len(candidate_filament_ids) > 1:
        return CalculatorMaterialIdentityResolution(
            status="ambiguous",
            source=source,
            stable_id=stable_id,
            candidate_filament_ids=candidate_filament_ids,
        )

    filament_id = candidate_filament_ids[0]
    return CalculatorMaterialIdentityResolution(
        status="resolved",
        source=source,
        stable_id=stable_id,
        filament_id=filament_id,
        preset_id=_single_preset_id(presets, filament_id),
        candidate_filament_ids=[filament_id],
    )


async def resolve_calculator_material_identities(
    db: AsyncSession,
    parsed: CalculatorGcodeParseResponse,
    *,
    user_id: int,
) -> CalculatorGcodeParseResponse:
    """Resolve namespaced FilamentHub identities, then provider filament ids.

    The plugin's ``fhub_identity_v1`` record identifies the selected managed
    Preset/PrintProfile/PrinterProfile without overloading Orca's own
    ``filament_id`` family identifier. Embedded ids remain untrusted input: only
    entities visible to the current user survive. Legacy ``FHUB_F_<n>`` and
    provider-specific material ids remain readable for older G-code.
    """
    embedded_identities = list(parsed.fhub_identities)
    material_identity_ids = {
        item.entity_id for item in embedded_identities if item.kind == "material_preset"
    }
    print_profile_identity_ids = {
        item.entity_id for item in embedded_identities if item.kind == "print_profile"
    }
    printer_profile_identity_ids = {
        item.entity_id for item in embedded_identities if item.kind == "printer_profile"
    }

    material_presets_by_id = await visible_material_presets(
        db, user_id=user_id, preset_ids=material_identity_ids
    )
    allowed_print_profile_ids = await visible_print_profile_ids(
        db, user_id=user_id, profile_ids=print_profile_identity_ids
    )
    allowed_printer_profile_ids = await visible_printer_profile_ids(
        db, user_id=user_id, profile_ids=printer_profile_identity_ids
    )

    visible_identities = [
        item
        for item in embedded_identities
        if (
            (item.kind == "material_preset" and item.entity_id in material_presets_by_id)
            or (item.kind == "print_profile" and item.entity_id in allowed_print_profile_ids)
            or (
                item.kind == "printer_profile"
                and item.entity_id in allowed_printer_profile_ids
            )
        )
    ]
    material_presets_by_tool = {
        item.tool_index: material_presets_by_id[item.entity_id]
        for item in visible_identities
        if item.kind == "material_preset" and item.tool_index is not None
    }

    stable_ids = {
        stable_id
        for material in parsed.materials
        if material.tool_index not in material_presets_by_tool
        and (stable_id := _stable_id(material.slicer_filament_id)) is not None
    }
    if not stable_ids and not material_presets_by_tool:
        return parsed.model_copy(update={"fhub_identities": visible_identities})

    direct_ids_by_stable_id: dict[str, int] = {}
    direct_filament_ids: set[int] = set()
    provider_ids: set[str] = set()
    for stable_id in stable_ids:
        match = _FILAMENTHUB_FILAMENT_ID_RE.fullmatch(stable_id)
        if match:
            filament_id = int(match.group(1))
            if filament_id > 0:
                direct_ids_by_stable_id[stable_id] = filament_id
                direct_filament_ids.add(filament_id)
        else:
            provider_ids.add(stable_id)

    existing_direct_ids: set[int] = set()
    if direct_filament_ids:
        result = await db.execute(
            select(Filament.id).where(Filament.id.in_(direct_filament_ids))
        )
        existing_direct_ids = set(result.scalars().all())

    user_presets_by_stable_id: dict[str, list[Preset]] = defaultdict(list)
    catalog_presets_by_stable_id: dict[str, list[Preset]] = defaultdict(list)
    if provider_ids:
        result = await db.execute(
            select(Preset).where(
                Preset.filament_id.is_not(None),
                Preset.orcaslicer_settings.is_not(None),
                Preset.orcaslicer_settings["filament_id"].as_string().in_(provider_ids),
                or_(
                    Preset.user_id == user_id,
                    Preset.user_id.is_(None),
                    Preset.is_official.is_(True),
                    Preset.source == "system",
                ),
            )
        )
        for preset in result.scalars().all():
            settings = preset.orcaslicer_settings or {}
            preset_stable_id = _stable_id(settings.get("filament_id"))
            if preset_stable_id not in provider_ids:
                continue
            if preset.user_id == user_id:
                user_presets_by_stable_id[preset_stable_id].append(preset)
            if preset.user_id is None or preset.is_official or preset.source == "system":
                catalog_presets_by_stable_id[preset_stable_id].append(preset)

    resolved_materials: list[CalculatorParsedMaterial] = []
    for material in parsed.materials:
        managed_preset = material_presets_by_tool.get(material.tool_index)
        if managed_preset is not None:
            stable_id = f"fhub:preset:{managed_preset.id}"
            if managed_preset.filament_id is not None:
                resolution = CalculatorMaterialIdentityResolution(
                    status="resolved",
                    source="filamenthub_preset_id",
                    stable_id=stable_id,
                    filament_id=managed_preset.filament_id,
                    preset_id=managed_preset.id,
                    candidate_filament_ids=[managed_preset.filament_id],
                )
            else:
                resolution = CalculatorMaterialIdentityResolution(
                    status="unresolved",
                    source="filamenthub_preset_id",
                    stable_id=stable_id,
                    preset_id=managed_preset.id,
                )
            resolved_materials.append(
                material.model_copy(update={"identity_resolution": resolution})
            )
            continue

        stable_id = _stable_id(material.slicer_filament_id)
        if stable_id is None:
            resolved_materials.append(material)
            continue

        direct_filament_id = direct_ids_by_stable_id.get(stable_id)
        if direct_filament_id is not None:
            if direct_filament_id in existing_direct_ids:
                resolution = CalculatorMaterialIdentityResolution(
                    status="resolved",
                    source="filamenthub_filament_id",
                    stable_id=stable_id,
                    filament_id=direct_filament_id,
                    candidate_filament_ids=[direct_filament_id],
                )
            else:
                resolution = CalculatorMaterialIdentityResolution(
                    status="unresolved",
                    stable_id=stable_id,
                )
        else:
            resolution = _resolution_from_presets(
                stable_id=stable_id,
                presets=user_presets_by_stable_id.get(stable_id, []),
                source="user_preset_filament_id",
            )
            if resolution is None:
                resolution = _resolution_from_presets(
                    stable_id=stable_id,
                    presets=catalog_presets_by_stable_id.get(stable_id, []),
                    source="catalog_preset_filament_id",
                )
            if resolution is None:
                resolution = CalculatorMaterialIdentityResolution(
                    status="unresolved",
                    stable_id=stable_id,
                )

        resolved_materials.append(
            material.model_copy(update={"identity_resolution": resolution})
        )

    return parsed.model_copy(
        update={
            "materials": resolved_materials,
            "fhub_identities": visible_identities,
        }
    )
