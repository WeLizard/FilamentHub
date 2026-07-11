"""Score presets by how well they fit a user's printer.

The public catalog uses this to surface "recommended for your printer" presets.
Scoring is deterministic: a preset is matched against the printers it is linked
to (``preset.printer_links``) and the best tier wins.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.preset import PUBLIC_PRESET_STATUSES, Preset
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer

# Match tiers as (base_score, reason). Higher is better.
MATCH_EXACT = (1.0, "exact_match")
MATCH_SAME_MODEL = (0.9, "same_model")
MATCH_SAME_FAMILY = (0.7, "same_family")
MATCH_SAME_MANUFACTURER = (0.5, "same_manufacturer")
MATCH_COMPATIBLE_SPECS = (0.3, "compatible_specs")
NO_MATCH = (0.0, "no_match")

# Ranking bonuses added on top of the base tier score.
BONUS_OFFICIAL = 0.05
BONUS_WEIGHTED = 0.03
BONUS_RATING_MAX = 0.1

# Tolerances for the cross-manufacturer "compatible specs" tier.
BUILD_VOLUME_TOLERANCE = 0.20  # ±20% per provided axis
NOZZLE_TOLERANCE = 0.05  # mm


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def _specs_compatible(a: Printer, b: Printer) -> bool:
    """True if nozzle and every provided build-volume axis are within tolerance."""
    if a.nozzle_diameter is not None and b.nozzle_diameter is not None:
        if abs(a.nozzle_diameter - b.nozzle_diameter) > NOZZLE_TOLERANCE:
            return False

    for axis_a, axis_b in (
        (a.build_volume_x, b.build_volume_x),
        (a.build_volume_y, b.build_volume_y),
        (a.build_volume_z, b.build_volume_z),
    ):
        if axis_a is not None and axis_b is not None and axis_a > 0:
            if abs(axis_a - axis_b) / axis_a > BUILD_VOLUME_TOLERANCE:
                return False

    return True


def score_preset_for_printer(preset: Preset, printer: Printer) -> tuple[float, str]:
    """Return ``(base_score, match_reason)`` for how well a preset fits a printer.

    Pure function over the already-loaded ``preset.printer_links[].printer``.
    Returns :data:`NO_MATCH` when the preset targets no compatible printer.
    """
    target_mfr = _norm(printer.manufacturer)
    target_model = _norm(printer.model)
    target_family = _norm(printer.family)

    best = NO_MATCH

    for link in preset.printer_links:
        linked = link.printer
        if linked is None:
            continue
        if linked.id == printer.id:
            return MATCH_EXACT  # nothing beats an exact link

        candidate: tuple[float, str] | None = None
        if target_mfr and _norm(linked.manufacturer) == target_mfr:
            if target_model and _norm(linked.model) == target_model:
                candidate = MATCH_SAME_MODEL
            elif target_family and _norm(linked.family) == target_family:
                candidate = MATCH_SAME_FAMILY
            else:
                candidate = MATCH_SAME_MANUFACTURER
        elif _specs_compatible(printer, linked):
            candidate = MATCH_COMPATIBLE_SPECS

        if candidate is not None and candidate[0] > best[0]:
            best = candidate

    return best


def apply_bonuses(base_score: float, preset: Preset) -> float:
    """Add official/weighted/rating ranking bonuses to a base tier score."""
    score = base_score
    if preset.is_official:
        score += BONUS_OFFICIAL
    if preset.is_weighted:
        score += BONUS_WEIGHTED
    if preset.rating:
        score += min(preset.rating * 0.02, BONUS_RATING_MAX)
    return score


@dataclass
class ScoredPreset:
    """A preset paired with its computed match score and reason."""

    preset: Preset
    match_score: float
    match_reason: str


async def get_recommended_presets(
    db: AsyncSession,
    printer: Printer,
    filament_id: int | None = None,
    limit: int = 20,
) -> list[ScoredPreset]:
    """Load approved+active presets and return the top matches for ``printer``."""
    query = (
        select(Preset)
        .options(selectinload(Preset.printer_links).selectinload(PresetPrinter.printer))
        .where(Preset.active == True)  # noqa: E712 (SQLAlchemy boolean column)
        .where(
            or_(
                Preset.moderation_status.in_(PUBLIC_PRESET_STATUSES),
                Preset.is_official == True,  # noqa: E712
            )
        )
    )
    if filament_id is not None:
        query = query.where(Preset.filament_id == filament_id)

    result = await db.execute(query)
    presets = result.scalars().unique().all()

    scored: list[ScoredPreset] = []
    for preset in presets:
        base, reason = score_preset_for_printer(preset, printer)
        if base <= 0.0:
            continue
        scored.append(
            ScoredPreset(
                preset=preset,
                match_score=apply_bonuses(base, preset),
                match_reason=reason,
            )
        )

    scored.sort(key=lambda item: item.match_score, reverse=True)
    return scored[:limit]
