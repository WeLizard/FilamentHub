"""Score presets by how well they fit a user's printer.

The public catalog uses this to surface "recommended for your printer" presets.
Scoring is deterministic: a preset is matched against the printers it is linked
to (``preset.printer_links``) and the best tier wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.filament import Filament
from app.models.preset import PUBLIC_PRESET_STATUSES, Preset
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.services.calculator_printer_compatibility_service import profile_nozzle_hrc

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
    """True only when at least one shared catalog fact is compatible."""
    compared = False
    if a.nozzle_diameter is not None and b.nozzle_diameter is not None:
        compared = True
        if abs(a.nozzle_diameter - b.nozzle_diameter) > NOZZLE_TOLERANCE:
            return False

    for axis_a, axis_b in (
        (a.build_volume_x, b.build_volume_x),
        (a.build_volume_y, b.build_volume_y),
        (a.build_volume_z, b.build_volume_z),
    ):
        if axis_a is not None and axis_b is not None and axis_a > 0:
            compared = True
            if abs(axis_a - axis_b) / axis_a > BUILD_VOLUME_TOLERANCE:
                return False

    return compared


@dataclass(frozen=True)
class PresetPrinterMatch:
    """Best catalog targeting tier and the links that establish it."""

    base_score: float
    reason: str
    printers: tuple[Printer, ...]


def match_preset_for_printer(preset: Preset, printer: Printer) -> PresetPrinterMatch:
    """Return the best catalog tier without treating missing facts as a match."""
    target_mfr = _norm(printer.manufacturer)
    target_model = _norm(printer.model)
    target_family = _norm(printer.family)

    best_score, best_reason = NO_MATCH
    best_printers: list[Printer] = []

    for link in preset.printer_links:
        linked = link.printer
        if linked is None:
            continue

        candidate: tuple[float, str] | None = None
        if linked.id == printer.id:
            candidate = MATCH_EXACT
        elif target_mfr and _norm(linked.manufacturer) == target_mfr:
            if target_model and _norm(linked.model) == target_model:
                candidate = MATCH_SAME_MODEL
            elif target_family and _norm(linked.family) == target_family:
                candidate = MATCH_SAME_FAMILY
            else:
                candidate = MATCH_SAME_MANUFACTURER
        elif _specs_compatible(printer, linked):
            candidate = MATCH_COMPATIBLE_SPECS

        if candidate is None:
            continue
        if candidate[0] > best_score:
            best_score, best_reason = candidate
            best_printers = [linked]
        elif candidate[0] == best_score and all(
            existing.id != linked.id for existing in best_printers
        ):
            best_printers.append(linked)

    return PresetPrinterMatch(best_score, best_reason, tuple(best_printers))


def score_preset_for_printer(preset: Preset, printer: Printer) -> tuple[float, str]:
    """Return ``(base_score, match_reason)`` for how well a preset fits a printer.

    Pure function over the already-loaded ``preset.printer_links[].printer``.
    Returns :data:`NO_MATCH` when the preset targets no compatible printer.
    """
    match = match_preset_for_printer(preset, printer)
    return match.base_score, match.reason


@dataclass(frozen=True)
class RecommendationRankingBonus:
    """One non-technical signal used only to order recommendation candidates."""

    kind: str
    value: float


def ranking_bonuses(preset: Preset) -> list[RecommendationRankingBonus]:
    """Return ranking signals separately so they cannot inflate technical match."""
    bonuses: list[RecommendationRankingBonus] = []
    if preset.is_official:
        bonuses.append(RecommendationRankingBonus(kind="official", value=BONUS_OFFICIAL))
    if preset.is_weighted:
        bonuses.append(RecommendationRankingBonus(kind="weighted", value=BONUS_WEIGHTED))
    if preset.rating:
        bonuses.append(
            RecommendationRankingBonus(
                kind="rating",
                value=min(preset.rating * 0.02, BONUS_RATING_MAX),
            )
        )
    return bonuses


def apply_bonuses(base_score: float, preset: Preset) -> float:
    """Add official/weighted/rating ranking bonuses to a base tier score."""
    return base_score + sum(bonus.value for bonus in ranking_bonuses(preset))


@dataclass
class ScoredPreset:
    """One recommendation with technical evidence kept apart from ranking."""

    preset: Preset
    ranking_base_score: float
    ranking_score: float
    ranking_bonuses: list[RecommendationRankingBonus]
    match_reason: str
    compatibility_status: str
    technical_match: float | None
    evidence_coverage: float
    evidence_count: int
    evidence_total: int
    compatibility_checks: list["RecommendationCompatibilityCheck"]
    hard_conflicts: list[str]


@dataclass(frozen=True)
class RecommendationCompatibilityCheck:
    """One factual machine requirement used by recommendation ranking."""

    kind: str
    status: str
    required_values: tuple[float, ...]
    available_values: tuple[float, ...]
    unit: str
    requirement_source: str
    capability_source: str | None

    @property
    def required_value(self) -> float:
        """Legacy singular projection for existing API consumers."""
        return self.required_values[0]

    @property
    def available_value(self) -> float | None:
        """Legacy singular projection for existing API consumers."""
        return self.available_values[0] if self.available_values else None


@dataclass(frozen=True)
class RecommendationCompatibility:
    """Tri-state compatibility plus independently measurable evidence."""

    status: str
    technical_match: float | None
    evidence_coverage: float
    evidence_count: int
    evidence_total: int
    checks: list[RecommendationCompatibilityCheck]
    hard_conflicts: list[str]


def _positive_numbers(value: Any) -> tuple[float, ...]:
    values = value if isinstance(value, (list, tuple)) else [value]
    result: list[float] = []
    for item in values:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if number <= 0 or any(abs(number - known) <= 0.001 for known in result):
            continue
        result.append(number)
    return tuple(sorted(result))


def _profile_nozzles(profile: PrinterProfile | None) -> tuple[float, ...]:
    if profile is None:
        return ()
    if profile.nozzle_diameters:
        return _positive_numbers(profile.nozzle_diameters)
    return _positive_numbers((profile.orcaslicer_settings or {}).get("nozzle_diameter"))


def _catalog_nozzles(printer: Printer) -> tuple[float, ...]:
    return _positive_numbers([printer.nozzle_diameter, *(printer.nozzle_options or [])])


def _comparison_status(
    required: tuple[float, ...],
    available: tuple[float, ...],
    *,
    minimum: bool = False,
) -> str:
    if not available:
        return "unknown"
    if minimum:
        return "compatible" if max(available) >= max(required) else "incompatible"
    return (
        "compatible"
        if any(abs(expected - actual) <= 0.01 for expected in required for actual in available)
        else "incompatible"
    )


def _check(
    *,
    kind: str,
    required: tuple[float, ...],
    available: tuple[float, ...],
    unit: str,
    requirement_source: str,
    capability_source: str | None,
    minimum: bool = False,
) -> RecommendationCompatibilityCheck:
    return RecommendationCompatibilityCheck(
        kind=kind,
        status=_comparison_status(required, available, minimum=minimum),
        required_values=required,
        available_values=available,
        unit=unit,
        requirement_source=requirement_source,
        capability_source=capability_source if available else None,
    )


def evaluate_preset_compatibility(
    preset: Preset,
    printer: Printer,
    filament: Filament | None,
    printer_profile: PrinterProfile | None,
    *,
    matched_printers: tuple[Printer, ...] | None = None,
) -> RecommendationCompatibility:
    """Compare explicit requirements against exact facts, then catalog fallback."""
    checks: list[RecommendationCompatibilityCheck] = []

    if matched_printers is None:
        matched_printers = match_preset_for_printer(preset, printer).printers

    required_nozzles = _positive_numbers(
        [nozzle for matched in matched_printers for nozzle in _catalog_nozzles(matched)]
    )
    if required_nozzles:
        exact_nozzles = _profile_nozzles(printer_profile)
        available_nozzles = exact_nozzles or _catalog_nozzles(printer)
        checks.append(
            _check(
                kind="nozzle_diameter",
                required=required_nozzles,
                available=available_nozzles,
                unit="mm",
                requirement_source="preset_printer",
                capability_source=("printer_profile" if exact_nozzles else "catalog_printer"),
            )
        )

    if preset.extruder_temp > 0:
        available_temperatures = _positive_numbers(
            printer.max_extruder_temp if printer.max_extruder_temp is not None else None
        )
        checks.append(
            _check(
                kind="hotend_temperature",
                required=(float(preset.extruder_temp),),
                available=available_temperatures,
                unit="°C",
                requirement_source="preset",
                capability_source="catalog_printer",
                minimum=True,
            )
        )

    if preset.bed_temp > 0:
        available_bed_temperatures = _positive_numbers(
            printer.max_bed_temp if printer.max_bed_temp is not None else None
        )
        checks.append(
            _check(
                kind="bed_temperature",
                required=(float(preset.bed_temp),),
                available=available_bed_temperatures,
                unit="°C",
                requirement_source="preset",
                capability_source="catalog_printer",
                minimum=True,
            )
        )

    required_hrc = filament.required_nozzle_hrc if filament is not None else None
    if required_hrc is not None and required_hrc > 0:
        available_hrc = profile_nozzle_hrc(printer_profile)
        checks.append(
            _check(
                kind="nozzle_hrc",
                required=(float(required_hrc),),
                available=_positive_numbers(available_hrc),
                unit="HRC",
                requirement_source="filament_catalog",
                capability_source="printer_profile",
                minimum=True,
            )
        )

    known_checks = [check for check in checks if check.status != "unknown"]
    evidence_count = len(known_checks)
    evidence_total = len(checks)
    coverage = evidence_count / evidence_total if evidence_total else 0.0
    hard_conflicts = [check.kind for check in checks if check.status == "incompatible"]
    if hard_conflicts:
        status = "incompatible"
    elif checks and len(known_checks) == len(checks):
        status = "compatible"
    else:
        status = "unknown"
    technical_match = (
        sum(check.status == "compatible" for check in known_checks) / evidence_count
        if evidence_count
        else None
    )
    return RecommendationCompatibility(
        status=status,
        technical_match=technical_match,
        evidence_coverage=coverage,
        evidence_count=evidence_count,
        evidence_total=evidence_total,
        checks=checks,
        hard_conflicts=hard_conflicts,
    )


async def get_recommended_presets(
    db: AsyncSession,
    printer: Printer,
    filament_id: int | None = None,
    limit: int = 20,
    *,
    printer_profile: PrinterProfile | None = None,
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
    filament = await db.get(Filament, filament_id) if filament_id is not None else None

    scored: list[ScoredPreset] = []
    for preset in presets:
        catalog_match = match_preset_for_printer(preset, printer)
        if catalog_match.base_score <= 0.0:
            continue
        compatibility = evaluate_preset_compatibility(
            preset,
            printer,
            filament,
            printer_profile,
            matched_printers=catalog_match.printers,
        )
        bonuses = ranking_bonuses(preset)
        scored.append(
            ScoredPreset(
                preset=preset,
                ranking_base_score=catalog_match.base_score,
                ranking_score=catalog_match.base_score + sum(bonus.value for bonus in bonuses),
                ranking_bonuses=bonuses,
                match_reason=catalog_match.reason,
                compatibility_status=compatibility.status,
                technical_match=compatibility.technical_match,
                evidence_coverage=compatibility.evidence_coverage,
                evidence_count=compatibility.evidence_count,
                evidence_total=compatibility.evidence_total,
                compatibility_checks=compatibility.checks,
                hard_conflicts=compatibility.hard_conflicts,
            )
        )

    compatibility_priority = {"incompatible": 0, "unknown": 1, "compatible": 2}
    scored.sort(
        key=lambda item: (
            compatibility_priority[item.compatibility_status],
            item.technical_match if item.technical_match is not None else -1.0,
            item.evidence_coverage,
            item.ranking_score,
            item.preset.rating or 0.0,
            -item.preset.id,
        ),
        reverse=True,
    )
    return scored[:limit]
