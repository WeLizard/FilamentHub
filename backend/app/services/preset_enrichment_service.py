"""Service for enriching draft/orphaned presets with material defaults."""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset import Preset

logger = logging.getLogger(__name__)

# Cached material defaults (loaded once)
_material_defaults: dict | None = None

# Dummy defaults used in orca_sync.py when no real values are available.
# If a preset has these exact values, it likely needs enrichment.
_DUMMY_DEFAULTS = {
    "extruder_temp": 200.0,
    "bed_temp": 60.0,
}

# Fields on the Preset model that can be enriched (material scope only)
_ENRICHABLE_FIELDS = [
    "extruder_temp",
    "bed_temp",
    "fan_speed",
    "retraction_length",
    "retraction_speed",
    "flow_rate",
]

# Material detection patterns — order matters: specific first
_MATERIAL_PATTERNS = [
    "PA-CF", "PA-GF", "PA6", "PA12", "PAHT",
    "PC-ABS", "PC-CF",
    "ABS-CF", "ABS-GF",
    "ASA-CF", "ASA-GF",
    "PLA-CF", "PLA+",
    "PETG-CF",
    "PET-CF",
    "PP-CF", "PP-GF",
    "PETG", "PCTG", "PET",
    "ABS", "ASA",
    "TPU", "TPE",
    "PA", "PC",
    "PVA", "PVB", "BVOH",
    "HIPS", "POM",
    "PP", "PE", "PHA",
    "PEI", "PEEK", "PPA", "PPS",
    "EVA", "SBS",
    "PLA",
]


def _load_material_defaults() -> dict:
    """Load material defaults from JSON file. Cached after first call."""
    global _material_defaults
    if _material_defaults is not None:
        return _material_defaults

    defaults_path = Path(__file__).parent.parent / "data" / "material_defaults.json"
    with open(defaults_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Remove comment key
    data.pop("_comment", None)
    _material_defaults = data
    return _material_defaults


def detect_material_type(preset: Preset) -> tuple[str | None, float]:
    """Detect material type from preset data.

    Returns:
        Tuple of (material_type, confidence).
        Confidence: 1.0 = from filament_type field,
                    0.8 = from inherits string,
                    0.5 = from preset name,
                    0.0 = not detected.
    """
    settings = preset.orcaslicer_settings or {}

    # Priority 1: filament_type from orcaslicer_settings (most reliable)
    filament_type = settings.get("filament_type")
    if filament_type:
        if isinstance(filament_type, list) and filament_type:
            filament_type = filament_type[0]
        if isinstance(filament_type, str) and filament_type.strip():
            ft_upper = filament_type.strip().upper()
            defaults = _load_material_defaults()
            # Direct match
            if ft_upper in defaults:
                return ft_upper, 1.0
            # Try pattern matching for composite types
            for pattern in _MATERIAL_PATTERNS:
                if pattern.upper() in ft_upper or ft_upper in pattern.upper():
                    if pattern in defaults:
                        return pattern, 0.95

    # Priority 2: inherits field
    inherits = settings.get("inherits", "")
    if isinstance(inherits, list) and inherits:
        inherits = inherits[0]
    if isinstance(inherits, str) and inherits:
        detected = _extract_material_from_string(inherits)
        if detected:
            return detected, 0.8

    # Priority 3: preset name
    if preset.name:
        detected = _extract_material_from_string(preset.name)
        if detected:
            return detected, 0.5

    return None, 0.0


def _extract_material_from_string(text: str) -> str | None:
    """Extract material type from a string using pattern matching."""
    defaults = _load_material_defaults()
    text_upper = text.upper()

    for pattern in _MATERIAL_PATTERNS:
        # Use word boundary-like matching to avoid false positives
        # e.g., "PA" shouldn't match "SPACE" or "PATH"
        escaped = re.escape(pattern)
        if re.search(rf'(?:^|[\s\-_@(])({escaped})(?:$|[\s\-_@)])', text_upper):
            if pattern in defaults:
                return pattern

    # Fallback: simple substring for less ambiguous types (3+ chars)
    for pattern in _MATERIAL_PATTERNS:
        if len(pattern) >= 3 and pattern.upper() in text_upper:
            if pattern in defaults:
                return pattern

    return None


def _is_dummy_value(field: str, value) -> bool:
    """Check if a field value is a dummy default that should be overwritten."""
    if value is None:
        return True
    if field in _DUMMY_DEFAULTS and value == _DUMMY_DEFAULTS[field]:
        return True
    # Zero values for optional fields indicate missing data
    if field in ("fan_speed", "retraction_length", "retraction_speed", "flow_rate") and (
        value is None or value == 0
    ):
        return True
    return False


# Max volumetric speed below this (mm³/s) is a placeholder, not a real material
# limit — even slow flexibles run well above it. Such values (e.g. 1) leak in from
# imported profiles; enrichment replaces them with the material default.
_MIN_REALISTIC_VOLUMETRIC = 2.0


def _current_volumetric_speed(settings: dict) -> float | None:
    """Read filament_max_volumetric_speed (Orca stores it as a one-element string list)."""
    raw = settings.get("filament_max_volumetric_speed")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def enrich_preset(preset: Preset) -> dict:
    """Enrich a draft preset with material defaults.

    Fills missing model fields from material defaults based on detected material type.
    Does NOT overwrite values explicitly set by the user.

    Args:
        preset: The Preset ORM object to enrich (modified in-place).

    Returns:
        Dict with enrichment metadata:
        - material_type: detected material type
        - confidence: detection confidence (0.0-1.0)
        - filled_fields: list of fields that were filled
        - skipped_fields: list of fields that already had values
    """
    material_type, confidence = detect_material_type(preset)

    result = {
        "material_type": material_type,
        "confidence": confidence,
        "filled_fields": [],
        "skipped_fields": [],
    }

    if material_type is None:
        # Cannot determine material — use PLA as safe fallback
        material_type = "PLA"
        confidence = 0.3
        result["material_type"] = material_type
        result["confidence"] = confidence

    defaults = _load_material_defaults()
    material_defaults = defaults.get(material_type, defaults.get("PLA", {}))

    for field in _ENRICHABLE_FIELDS:
        current_value = getattr(preset, field, None)
        default_value = material_defaults.get(field)

        if default_value is None:
            continue

        if _is_dummy_value(field, current_value):
            setattr(preset, field, default_value)
            result["filled_fields"].append(field)
        else:
            result["skipped_fields"].append(field)

    # Store enrichment metadata in orcaslicer_settings
    if preset.orcaslicer_settings is None:
        preset.orcaslicer_settings = {}

    # Max volumetric speed lives in the settings blob, not a model column. Fill it
    # when missing or when a placeholder (< _MIN_REALISTIC_VOLUMETRIC) leaked in.
    vol_default = material_defaults.get("filament_max_volumetric_speed")
    if vol_default is not None:
        current_vol = _current_volumetric_speed(preset.orcaslicer_settings)
        if current_vol is None or current_vol < _MIN_REALISTIC_VOLUMETRIC:
            preset.orcaslicer_settings["filament_max_volumetric_speed"] = [f"{vol_default:g}"]
            result["filled_fields"].append("filament_max_volumetric_speed")
        else:
            result["skipped_fields"].append("filament_max_volumetric_speed")

    preset.orcaslicer_settings["enrichment"] = {
        "material_type": material_type,
        "confidence": confidence,
        "filled_fields": result["filled_fields"],
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }

    if result["filled_fields"]:
        logger.info(
            f"Enriched preset '{preset.name}' (id={preset.id}): "
            f"material={material_type}, confidence={confidence:.1f}, "
            f"filled={result['filled_fields']}"
        )

    return result


async def enrich_drafts_batch(db: AsyncSession) -> dict:
    """Enrich all unenriched draft presets.

    Returns:
        Summary dict with counts: total, enriched, skipped, errors.
    """
    # Find all draft presets that haven't been enriched yet
    stmt = select(Preset).where(
        Preset.active == False,  # noqa: E712
        Preset.filament_id.is_(None),
    )
    result = await db.execute(stmt)
    drafts = result.scalars().all()

    stats = {"total": len(drafts), "enriched": 0, "skipped": 0, "errors": 0}

    for preset in drafts:
        # Skip already enriched presets
        settings = preset.orcaslicer_settings or {}
        if settings.get("enrichment"):
            stats["skipped"] += 1
            continue

        try:
            enrichment_result = enrich_preset(preset)
            if enrichment_result["filled_fields"]:
                stats["enriched"] += 1
            else:
                stats["skipped"] += 1
        except Exception:
            logger.exception(f"Failed to enrich preset id={preset.id}")
            stats["errors"] += 1

    await db.flush()
    logger.info(f"Batch enrichment complete: {stats}")
    return stats
