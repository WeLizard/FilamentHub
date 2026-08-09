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

_FILAMENTHUB_FILAMENT_ID_RE = re.compile(r"^FHUB(\d+)$", re.IGNORECASE)


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
    """Resolve G-code ``filament_ids`` before any name-based UI fallback.

    ``FHUB<n>`` is our reserved catalog namespace and maps directly to the
    Filament written into an exported FilamentHub profile. Provider-specific
    identifiers are accepted only from the current user's own mapped presets or
    from trusted catalog presets. Conflicting exact mappings remain ambiguous.
    """
    stable_ids = {
        stable_id
        for material in parsed.materials
        if (stable_id := _stable_id(material.slicer_filament_id)) is not None
    }
    if not stable_ids:
        return parsed

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

    return parsed.model_copy(update={"materials": resolved_materials})
