"""Resolve stable slicer material identifiers to FilamentHub catalog records."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset
from app.models.user_saved_preset import UserSavedPreset
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

# The Orca plugin installs managed presets into this local bundle and names each
# one "<filament_type> • <brand> • <preset name>", adding " (FH-<id>)" to the file
# stem when that name is already taken (orca-plugin: filament_display_name,
# preset_file_path). Orca then writes the stem into filament_settings_id.
_MANAGED_PRESET_PREFIX = "_local/filamenthub/"
_MANAGED_NAME_SEPARATOR = " • "
_MANAGED_DUPLICATE_SUFFIX_RE = re.compile(r"\s*\(FH-(\d+)\)$")
_UNSAFE_FILE_NAME_CHARS = frozenset('<>[]:"/\\|?*')
_MAX_FILE_NAME_LENGTH = 120
# Ids come from user-supplied files and must fit the INTEGER primary keys.
_MAX_DB_ID = 2**31 - 1


class _PresetRef(NamedTuple):
    id: int
    filament_id: int | None


@dataclass(frozen=True)
class _ManagedName:
    settings_id: str
    preset_id: int | None
    label_key: str
    type_key: str | None


def _stable_id(value: str | None) -> str | None:
    normalized = (value or "").strip().strip('"')
    return normalized or None


def _file_name_stem(name: str) -> str:
    """Mirror the plugin's ``safe_filename`` so both sides derive one stem."""
    cleaned = "".join(
        "_" if ch in _UNSAFE_FILE_NAME_CHARS or ord(ch) < 32 else ch for ch in name
    ).strip(" ._")
    return cleaned[:_MAX_FILE_NAME_LENGTH].rstrip(" ._") or "preset"


def _label_key(material_type: str, brand_name: str, preset_name: str) -> str:
    parts = [part.strip() for part in (material_type, brand_name, preset_name)]
    return _file_name_stem(_MANAGED_NAME_SEPARATOR.join(part for part in parts if part)).casefold()


def _parse_managed_name(material: CalculatorParsedMaterial) -> _ManagedName | None:
    settings_id = _stable_id(material.settings_id) or _stable_id(material.name)
    if settings_id is None or not settings_id.casefold().startswith(_MANAGED_PRESET_PREFIX):
        return None

    stem = settings_id[len(_MANAGED_PRESET_PREFIX):].strip()
    preset_id: int | None = None
    suffix = _MANAGED_DUPLICATE_SUFFIX_RE.search(stem)
    if suffix:
        candidate_id = int(suffix.group(1))
        if 0 < candidate_id <= _MAX_DB_ID:
            preset_id = candidate_id
        stem = stem[: suffix.start()].strip()

    parts = stem.split(_MANAGED_NAME_SEPARATOR)
    type_key = parts[0].strip().casefold() if len(parts) > 1 else None
    return _ManagedName(
        settings_id=settings_id,
        preset_id=preset_id,
        label_key=stem.casefold(),
        type_key=type_key or None,
    )


def _single_preset_id(presets: Sequence[_PresetRef], filament_id: int) -> int | None:
    matching_ids = {preset.id for preset in presets if preset.filament_id == filament_id}
    return next(iter(matching_ids)) if len(matching_ids) == 1 else None


def _resolution_from_presets(
    *,
    stable_id: str,
    presets: Sequence[_PresetRef],
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


def _resolve_managed_name(
    name: _ManagedName,
    *,
    presets_by_id: dict[int, Preset],
    presets_by_label: dict[str, list[_PresetRef]],
) -> CalculatorMaterialIdentityResolution:
    if name.preset_id is not None:
        # The suffix claims one concrete preset. If the user cannot see it, a
        # same-named preset of their own is a different material.
        preset = presets_by_id.get(name.preset_id)
        if preset is not None:
            resolution = _resolution_from_presets(
                stable_id=name.settings_id,
                presets=[_PresetRef(preset.id, preset.filament_id)],
                source="filamenthub_managed_name",
            )
            if resolution is not None:
                return resolution
        return CalculatorMaterialIdentityResolution(
            status="unresolved",
            stable_id=name.settings_id,
        )

    resolution = _resolution_from_presets(
        stable_id=name.settings_id,
        presets=presets_by_label.get(name.label_key, []),
        source="filamenthub_managed_name",
    )
    return resolution or CalculatorMaterialIdentityResolution(
        status="unresolved",
        stable_id=name.settings_id,
    )


async def _load_managed_presets_by_label(
    db: AsyncSession,
    *,
    user_id: int,
    type_keys: set[str],
) -> dict[str, list[_PresetRef]]:
    if not type_keys:
        return {}
    # Exactly the set the plugin installs into Orca (sync_orchestrator): a
    # same-named draft or unsynced preset never reached the slicer.
    synced_by_user = (
        select(UserSavedPreset.id)
        .where(
            UserSavedPreset.user_id == user_id,
            UserSavedPreset.preset_id == Preset.id,
            UserSavedPreset.sync.is_(True),
        )
        .exists()
    )
    result = await db.execute(
        select(
            Preset.id,
            Preset.name.label("preset_name"),
            Preset.filament_id,
            Filament.material_type,
            Brand.name.label("brand_name"),
        )
        .join(Filament, Filament.id == Preset.filament_id)
        .join(Brand, Brand.id == Filament.brand_id)
        .where(
            func.lower(func.trim(Filament.material_type)).in_(type_keys),
            Preset.active.is_(True),
            synced_by_user,
        )
    )
    presets_by_label: dict[str, list[_PresetRef]] = {}
    for row in result.all():
        key = _label_key(row.material_type, row.brand_name, row.preset_name)
        presets_by_label.setdefault(key, []).append(_PresetRef(row.id, row.filament_id))
    return presets_by_label


async def resolve_calculator_material_identities(
    db: AsyncSession,
    parsed: CalculatorGcodeParseResponse,
    *,
    user_id: int,
) -> CalculatorGcodeParseResponse:
    """Resolve the materials of one job; see the batch variant for the order."""
    [resolved] = await resolve_calculator_material_identities_for_jobs(
        db, [parsed], user_id=user_id
    )
    return resolved


async def resolve_calculator_material_identities_for_jobs(
    db: AsyncSession,
    jobs: Sequence[CalculatorGcodeParseResponse],
    *,
    user_id: int,
) -> list[CalculatorGcodeParseResponse]:
    """Resolve every material of every job with a fixed number of queries.

    Per material, in order:

    1. the plugin's ``fhub_identity_v1`` record for that tool (selected managed
       Preset/PrintProfile/PrinterProfile), kept only when visible to the user;
    2. a namespaced FilamentHub filament id (``FHUB_F_<n>`` / ``FHUB<n>``);
    3. the managed preset name Orca recorded in ``filament_settings_id``
       (``_local/filamenthub/<type> • <brand> • <name>``), matched among the
       active presets the user synced, i.e. the set the plugin installs.

    Orca's own ``filament_id`` is deliberately never an identity. It names a
    material family: every preset derived from the same library parent carries
    the same value, so a single hit says nothing about which filament was used.
    Embedded ids and names are untrusted input.
    """
    jobs = list(jobs)
    managed_names = [
        [_parse_managed_name(material) for material in job.materials] for job in jobs
    ]

    material_identity_ids: set[int] = set()
    print_profile_identity_ids: set[int] = set()
    printer_profile_identity_ids: set[int] = set()
    for job in jobs:
        for item in job.fhub_identities:
            if not 0 < item.entity_id <= _MAX_DB_ID:
                continue
            if item.kind == "material_preset":
                material_identity_ids.add(item.entity_id)
            elif item.kind == "print_profile":
                print_profile_identity_ids.add(item.entity_id)
            elif item.kind == "printer_profile":
                printer_profile_identity_ids.add(item.entity_id)
    suffix_preset_ids = {
        name.preset_id
        for names in managed_names
        for name in names
        if name is not None and name.preset_id is not None
    }

    material_presets_by_id = await visible_material_presets(
        db, user_id=user_id, preset_ids=material_identity_ids | suffix_preset_ids
    )
    allowed_print_profile_ids = await visible_print_profile_ids(
        db, user_id=user_id, profile_ids=print_profile_identity_ids
    )
    allowed_printer_profile_ids = await visible_printer_profile_ids(
        db, user_id=user_id, profile_ids=printer_profile_identity_ids
    )

    visible_identities_by_job = []
    material_presets_by_tool_by_job: list[dict[int, Preset]] = []
    for job in jobs:
        visible_identities = [
            item
            for item in job.fhub_identities
            if (
                (item.kind == "material_preset" and item.entity_id in material_presets_by_id)
                or (item.kind == "print_profile" and item.entity_id in allowed_print_profile_ids)
                or (
                    item.kind == "printer_profile"
                    and item.entity_id in allowed_printer_profile_ids
                )
            )
        ]
        visible_identities_by_job.append(visible_identities)
        material_presets_by_tool_by_job.append(
            {
                item.tool_index: material_presets_by_id[item.entity_id]
                for item in visible_identities
                if item.kind == "material_preset" and item.tool_index is not None
            }
        )

    direct_ids_by_stable_id: dict[str, int] = {}
    name_type_keys: set[str] = set()
    for job, names, presets_by_tool in zip(
        jobs, managed_names, material_presets_by_tool_by_job, strict=True
    ):
        for material, name in zip(job.materials, names, strict=True):
            if material.tool_index in presets_by_tool:
                continue
            stable_id = _stable_id(material.slicer_filament_id)
            match = _FILAMENTHUB_FILAMENT_ID_RE.fullmatch(stable_id) if stable_id else None
            if match and 0 < int(match.group(1)) <= _MAX_DB_ID:
                direct_ids_by_stable_id[stable_id] = int(match.group(1))
            if name is not None and name.preset_id is None and name.type_key is not None:
                name_type_keys.add(name.type_key)

    existing_direct_ids: set[int] = set()
    if direct_ids_by_stable_id:
        result = await db.execute(
            select(Filament.id).where(
                Filament.id.in_(set(direct_ids_by_stable_id.values()))
            )
        )
        existing_direct_ids = set(result.scalars().all())

    presets_by_label = await _load_managed_presets_by_label(
        db, user_id=user_id, type_keys=name_type_keys
    )

    resolved_jobs: list[CalculatorGcodeParseResponse] = []
    for job, names, visible_identities, presets_by_tool in zip(
        jobs,
        managed_names,
        visible_identities_by_job,
        material_presets_by_tool_by_job,
        strict=True,
    ):
        resolved_materials: list[CalculatorParsedMaterial] = []
        for material, name in zip(job.materials, names, strict=True):
            managed_preset = presets_by_tool.get(material.tool_index)
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
            direct_filament_id = (
                direct_ids_by_stable_id.get(stable_id) if stable_id is not None else None
            )
            if stable_id is not None and direct_filament_id in existing_direct_ids:
                resolution = CalculatorMaterialIdentityResolution(
                    status="resolved",
                    source="filamenthub_filament_id",
                    stable_id=stable_id,
                    filament_id=direct_filament_id,
                    candidate_filament_ids=[direct_filament_id],
                )
            elif name is not None:
                resolution = _resolve_managed_name(
                    name,
                    presets_by_id=material_presets_by_id,
                    presets_by_label=presets_by_label,
                )
            elif stable_id is not None:
                resolution = CalculatorMaterialIdentityResolution(
                    status="unresolved",
                    stable_id=stable_id,
                )
            else:
                resolved_materials.append(material)
                continue

            resolved_materials.append(
                material.model_copy(update={"identity_resolution": resolution})
            )

        resolved_jobs.append(
            job.model_copy(
                update={
                    "materials": resolved_materials,
                    "fhub_identities": visible_identities,
                }
            )
        )
    return resolved_jobs
