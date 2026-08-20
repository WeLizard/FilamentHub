"""Build the reviewed public Orca projection of an imported draft."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset import Preset
from app.services.orca_transport import (
    ORCA_SCALAR_FIELDS,
    ORCA_VECTOR_FIELDS,
    project_orca_setting,
)

_PRIVATE_EXACT_KEYS = frozenset(
    {
        "_comment",
        "data",
        "description",
        "filament_notes",
        "notes",
        "plugins",
        "compatible_printers",
        "compatible_printers_condition",
        "compatible_prints",
        "compatible_prints_condition",
        "renamed_from",
        "print_host",
        "print_host_webui",
        "host_type",
        "orphaned",
        "orphaned_reason",
        "derived_from_external_id",
        "derived_from_draft_id",
    }
)

_PRIVATE_KEY_PARTS = frozenset(
    {
        "address",
        "apikey",
        "authorization",
        "credential",
        "hostname",
        "password",
        "printhost",
        "secret",
        "token",
        "uri",
        "url",
        "webui",
    }
)

_MANAGED_IDENTITY_KEYS = frozenset(
    {
        "bundle_id",
        "fhub_draft_id",
        "fhub_id",
        "fhub_source",
        "filament_settings_id",
        "setting_id",
    }
)

_PUBLIC_ORCA_KEYS = (
    ORCA_SCALAR_FIELDS.get("filament", frozenset())
    | ORCA_VECTOR_FIELDS.get("filament", frozenset())
)


def _is_private_import_key(key: str) -> bool:
    normalized = key.strip().casefold()
    if normalized in _PRIVATE_EXACT_KEYS or normalized in _MANAGED_IDENTITY_KEYS:
        return True
    # Imported scripts and notes may contain workstation paths, account names,
    # private macros or network credentials. They remain in import_evidence but
    # are never published merely because the user accepted the catalogue link.
    if "gcode" in normalized or "note" in normalized or "comment" in normalized:
        return True
    parts = {part for part in normalized.replace("-", "_").split("_") if part}
    if parts & _PRIVATE_KEY_PARTS:
        return True
    if "ip" in parts or ("access" in parts and "code" in parts):
        return True
    return False


def public_orca_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """Return the reviewed Orca projection without private import data.

    The original payload is preserved separately in ``Preset.import_evidence``.
    Only fields already known to the Orca transport contract may become public.
    Unknown fields remain intact in private evidence until schema intake can
    classify them; silently publishing an arbitrary nested object would expose
    workstation data under an innocent-looking parent key. FilamentHub rebuilds
    managed identity and printer compatibility authoritatively.
    """
    if not isinstance(settings, dict):
        return {}
    published: dict[str, Any] = {}
    for key, value in settings.items():
        if (
            not isinstance(key, str)
            or key not in _PUBLIC_ORCA_KEYS
            or _is_private_import_key(key)
        ):
            continue
        accepted, projected = project_orca_setting(key, value, "filament")
        if accepted:
            published[key] = deepcopy(projected)
    return published


def apply_managed_orca_identity(preset: Preset) -> None:
    """Attach managed identity without destroying the owner's round-trip data."""
    settings = deepcopy(preset.orcaslicer_settings or {})
    settings["fhub_id"] = preset.id
    settings["fhub_source"] = "filamenthub"
    preset.orcaslicer_settings = settings


def apply_public_orca_identity(preset: Preset) -> None:
    """Project one reviewed draft and attach only FilamentHub-managed identity."""
    preset.orcaslicer_settings = public_orca_settings(preset.orcaslicer_settings)
    apply_managed_orca_identity(preset)


async def prepare_published_draft(
    db: AsyncSession,
    *,
    preset: Preset,
    user_id: int,
    stored_settings: dict[str, Any] | None = None,
) -> None:
    """Turn one reviewed private draft into the managed public projection."""
    stored = dict(stored_settings or {})
    reviewed = (
        dict(preset.orcaslicer_settings)
        if isinstance(preset.orcaslicer_settings, dict)
        else {}
    )
    if not isinstance(preset.import_evidence, dict):
        from app.services.preset_import_evidence import new_import_evidence

        preset.import_evidence = new_import_evidence(
            settings=stored,
            source=preset.source,
            external_id=preset.external_id,
            name=preset.name,
            capture_mode="stored_snapshot",
        )

    old_draft_id = stored.get("fhub_draft_id") or reviewed.get("fhub_draft_id")
    evidence = deepcopy(preset.import_evidence or {})
    promotion_identity = {
        key: value
        for key, value in {
            "external_id": preset.external_id,
            "draft_id": old_draft_id,
        }.items()
        if value
    }
    if promotion_identity:
        evidence["promotion_identity"] = promotion_identity
        preset.import_evidence = evidence
    apply_public_orca_identity(preset)

    from app.models.user_saved_preset import UserSavedPreset

    saved = await db.scalar(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == user_id,
            UserSavedPreset.preset_id == preset.id,
        )
    )
    if saved is None:
        db.add(UserSavedPreset(user_id=user_id, preset_id=preset.id, sync=True))
    else:
        saved.sync = True

    from app.services.preset_funnel_metrics import record_preset_funnel_event

    record_preset_funnel_event(db, "filament_matched_or_created")
