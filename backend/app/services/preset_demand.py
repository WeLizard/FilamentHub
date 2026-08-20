"""Anonymous cross-user demand signals for imported Orca candidates."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.models.preset import Preset

_SEPARATORS_RE = re.compile(r"[\W_]+", re.UNICODE)
_GENERIC_VENDORS = {"generic", "unknown", "default", "custom", "system"}


def _first_text(settings: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = settings.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value is not None and str(value).strip() not in {"", "nil"}:
            return str(value).strip()
    return None


def _normalize(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold().replace("ё", "е")
    return _SEPARATORS_RE.sub(" ", normalized).strip()


def preset_demand_signature(
    settings: dict[str, Any] | None,
    preset_name: str | None,
) -> str | None:
    """Hash product traits without persisting a user's arbitrary local name."""
    if not isinstance(settings, dict):
        settings = {}
    vendor = _normalize(_first_text(settings, "filament_vendor"))
    if vendor in _GENERIC_VENDORS:
        vendor = ""
    material_type = _normalize(_first_text(settings, "filament_type"))
    color = _normalize(
        _first_text(settings, "filament_colour", "default_filament_colour")
    )
    local_name = _normalize(preset_name)
    if vendor and local_name.startswith(f"{vendor} "):
        local_name = local_name[len(vendor) + 1 :]
    traits = [vendor, material_type, local_name, color]
    if not material_type or not local_name:
        return None
    encoded = json.dumps(traits, ensure_ascii=False, separators=(",", ":"))
    # A plain digest lets anyone with a guessed local name reproduce the value.
    # HMAC keeps the grouping stable inside this deployment without turning the
    # database column into an offline dictionary of users' private preset names.
    return hmac.new(
        app_settings.SECRET_KEY.encode("utf-8"),
        encoded.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def demand_counts(
    db: AsyncSession,
    signatures: set[str],
) -> dict[str, int]:
    if not signatures:
        return {}
    rows = await db.execute(
        select(
            Preset.demand_signature,
            func.count(distinct(Preset.user_id)),
        )
        .where(
            Preset.demand_signature.in_(signatures),
            Preset.user_id.is_not(None),
        )
        .group_by(Preset.demand_signature)
    )
    return {signature: int(count) for signature, count in rows if signature}
