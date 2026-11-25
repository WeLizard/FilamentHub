"""Copy a preset for another colour of its material.

One preset is one colour of one material: its settings may depend on the
colour, and a published preset is used by other people, so it never moves to
another colour. Whoever needs the same settings for another colour gets a
separate private draft that points at the exact source version; the source and
its history stay untouched. The draft becomes public only when its author
publishes it.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import escape_like
from app.models.filament import Filament
from app.models.preset import PUBLIC_PRESET_STATUSES, Preset, PresetModerationStatus
from app.models.preset_version import PresetVersion
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset
from app.services.orcaslicer_preset_contract import ORCA_INVALID_PRESET_NAME_CHARS
from app.services.preset_access import can_manage_preset
from app.services.preset_publication import MANAGED_IDENTITY_KEYS, public_orca_settings

# Provenance of a preset made on the site from another one. Publishing such a
# draft keeps its reviewed settings instead of re-projecting them as an import.
PRESET_SOURCE_COPY = "copy"

# Orca keeps the preset colour under either key depending on the code path.
COLOUR_KEYS = frozenset({"default_filament_colour", "filament_colour", "filament_color"})

# Keys that describe the source row, not its print settings: managed identity
# in Orca and FilamentHub, and import bookkeeping such as the link to the
# spools an import created. The copy gets its own identity and no import past.
_SOURCE_ROW_KEYS = MANAGED_IDENTITY_KEYS | {
    "name",
    "orphaned",
    "orphaned_reason",
    "original_inherits",
    "enrichment",
    "derived_from_external_id",
    "derived_from_draft_id",
}
_SOURCE_ROW_PREFIXES = ("import_",)

_PRESET_NAME_MAX = 200
_NAME_SPACES = re.compile(r"\s+")

CopyAccess = Literal["own", "public"]


def is_site_copy(preset: Preset) -> bool:
    return preset.source == PRESET_SOURCE_COPY


async def copy_access(
    db: AsyncSession, user: User, source: Preset, filament: Filament | None
) -> CopyAccess | None:
    """What of ``source`` this person may copy, or None when it is not theirs to see.

    The author copies their own preset in any state and keeps its stored
    settings. Anyone copies a published preset, but only what the catalogue
    shows to everyone. Someone else's draft is nobody else's business.
    """
    owned = (
        await can_manage_preset(db, user, source, filament)
        if source.is_official
        else source.user_id == user.id
    )
    if owned:
        return "own"
    published = source.active and (
        source.is_official or source.moderation_status in PUBLIC_PRESET_STATUSES
    )
    return "public" if published else None


def _copied_settings(source: Preset, access: CopyAccess, target: Filament) -> dict:
    # An unpublished import still holds private slicer data; publication would
    # project it, so a copy takes the same projection. A published preset of
    # one's own, or a copy made here, already holds reviewed settings.
    keep_stored = access == "own" and (source.active or is_site_copy(source))
    stored = source.orcaslicer_settings if isinstance(source.orcaslicer_settings, dict) else {}
    settings = deepcopy(stored) if keep_stored else public_orca_settings(stored)
    for key in list(settings):
        if (
            key in _SOURCE_ROW_KEYS
            or key in COLOUR_KEYS
            or key.startswith(_SOURCE_ROW_PREFIXES)
        ):
            del settings[key]
    if target.color_hex:
        settings["default_filament_colour"] = [target.color_hex]
        settings["filament_colour"] = [target.color_hex]
    return settings


def _name_part(value: str | None) -> str:
    text = "".join(
        " " if char in ORCA_INVALID_PRESET_NAME_CHARS or ord(char) < 32 else char
        for char in (value or "")
    )
    return _NAME_SPACES.sub(" ", text).strip()


def _colour_label(filament: Filament) -> str:
    return (
        _name_part(filament.color_name)
        or (filament.color_hex or "").upper()
        or _name_part(filament.name)
    )


def copy_name(source_name: str, source_filament: Filament, target: Filament) -> str:
    """The source name with the new colour in place of the old one.

    A name that does not mention the old colour gets the new one appended, so
    the copy never shares its name with the source in the slicer's list.
    """
    base = _name_part(source_name) or _name_part(source_filament.name)
    new_colour = _colour_label(target)
    old_colour = _name_part(source_filament.color_name)
    if old_colour and new_colour:
        pattern = re.compile(rf"(?<!\w){re.escape(old_colour)}(?!\w)", re.IGNORECASE)
        if pattern.search(base):
            return pattern.sub(lambda _match: new_colour, base)[:_PRESET_NAME_MAX].strip()
    suffix = f" ({new_colour})" if new_colour else ""
    return f"{base[:_PRESET_NAME_MAX - len(suffix)].rstrip()}{suffix}"


async def _unique_name(db: AsyncSession, user_id: int, name: str) -> str:
    """Number the name when the author already has a preset called so."""
    rows = await db.scalars(
        select(Preset.name).where(
            Preset.user_id == user_id,
            func.lower(Preset.name).like(f"{escape_like(name.lower())}%", escape="\\"),
        )
    )
    taken = {row.casefold() for row in rows}
    if name.casefold() not in taken:
        return name
    number = 2
    while True:
        suffix = f" {number}"
        candidate = f"{name[:_PRESET_NAME_MAX - len(suffix)].rstrip()}{suffix}"
        if candidate.casefold() not in taken:
            return candidate
        number += 1


async def find_unpublished_copy(
    db: AsyncSession,
    *,
    user_id: int,
    source: Preset,
    source_version_id: int | None,
    target: Filament,
) -> Preset | None:
    """The same request made twice returns the draft it already made."""
    version = (
        Preset.derived_from_version_id == source_version_id
        if source_version_id is not None
        else Preset.derived_from_version_id.is_(None)
    )
    return await db.scalar(
        select(Preset)
        .where(
            Preset.user_id == user_id,
            Preset.source == PRESET_SOURCE_COPY,
            Preset.active.is_(False),
            Preset.derived_from_preset_id == source.id,
            Preset.filament_id == target.id,
            version,
        )
        .order_by(Preset.id.desc())
        .limit(1)
    )


async def build_color_copy(
    db: AsyncSession,
    *,
    user: User,
    source: Preset,
    source_filament: Filament,
    source_version_id: int | None,
    target: Filament,
    access: CopyAccess,
) -> Preset:
    """An unsaved private draft with the source settings for ``target``'s colour."""
    name = await _unique_name(db, user.id, copy_name(source.name, source_filament, target))
    return Preset(
        filament_id=target.id,
        user_id=user.id,
        created_by_user_id=user.id,
        organization_id=None,
        derived_from_preset_id=source.id,
        derived_from_version_id=source_version_id,
        name=name,
        description=source.description,
        extruder_temp=source.extruder_temp,
        bed_temp=source.bed_temp,
        flow_rate=source.flow_rate,
        fan_speed=source.fan_speed,
        retraction_length=source.retraction_length,
        retraction_speed=source.retraction_speed,
        orcaslicer_settings=_copied_settings(source, access, target),
        # The hardware a preset was tuned on is the author's private evidence.
        compat_context=deepcopy(source.compat_context) if access == "own" else None,
        is_official=False,
        is_weighted=False,
        active=False,
        # Nobody but the author sees a draft, so there is nothing to review yet.
        moderation_status=PresetModerationStatus.NOT_REQUIRED,
        source=PRESET_SOURCE_COPY,
    )


async def _used_by_others(db: AsyncSession, preset: Preset) -> bool:
    saved = select(UserSavedPreset.id).where(UserSavedPreset.preset_id == preset.id)
    if preset.user_id is not None:
        saved = saved.where(UserSavedPreset.user_id != preset.user_id)
    if await db.scalar(saved.limit(1)) is not None:
        return True
    fork = select(Preset.id).where(Preset.derived_from_preset_id == preset.id)
    if preset.user_id is not None:
        fork = fork.where(Preset.user_id.is_distinct_from(preset.user_id))
    return await db.scalar(fork.limit(1)) is not None


async def keeps_its_colour(db: AsyncSession, preset: Preset) -> bool:
    """Whether the preset may no longer move to another colour of its material.

    Published presets are used by other people. A draft is the author's alone
    until someone else has saved it or built on it.
    """
    return bool(preset.active) or await _used_by_others(db, preset)


async def switches_locked_colour(db: AsyncSession, preset: Preset, target_id: int) -> bool:
    """Whether moving the preset to ``target_id`` changes a colour people rely on.

    Every material the preset has had counts, so a detour through an unrelated
    material does not open the way to another colour of the original one.
    Returning to a material the preset already had is not a colour change.
    """
    if preset.filament_id is None or target_id == preset.filament_id:
        return False
    from app.services.material_variants import is_color_variant_of_any

    earlier = select(PresetVersion.filament_id).where(
        PresetVersion.preset_id == preset.id,
        PresetVersion.filament_id.is_not(None),
    )
    materials = list(
        await db.scalars(
            select(Filament).where(
                or_(Filament.id == preset.filament_id, Filament.id.in_(earlier))
            )
        )
    )
    if not await is_color_variant_of_any(db, materials, target_id):
        return False
    return await keeps_its_colour(db, preset)
