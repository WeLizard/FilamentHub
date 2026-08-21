"""Build a small, non-mutating review projection for imported preset drafts."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.brand_slug_redirect import BrandSlugRedirect
from app.models.filament import Filament
from app.models.filament_country_cell import FilamentCountryCell
from app.models.filament_slug_redirect import FilamentSlugRedirect
from app.models.preset import Preset
from app.schemas.preset import (
    PresetDraftAnalysisResponse,
    PresetDraftCatalogMatch,
    PresetDraftSuggestion,
)
from app.services.catalog_feature_search import resolve_catalog_feature_codes
from app.services.preset_demand import demand_counts, preset_demand_signature
from app.services.preset_import_evidence import latest_evidence_settings
from app.services.slug_service import slugify

_MATERIAL_TOKEN_RE = re.compile(
    r"(?:^|[\s_\-@(])(PA-CF|PA-GF|PA6|PA12|PAHT|PC-ABS|PC-CF|ABS-CF|ABS-GF|"
    r"ASA-CF|ASA-GF|PLA-CF|PLA\+|PETG-CF|PET-CF|PP-CF|PP-GF|PETG|PCTG|PET|"
    r"ABS|ASA|TPU|TPE|PA|PC|PVA|PVB|BVOH|HIPS|POM|PP|PE|PHA|PEI|PEEK|PPA|"
    r"PPS|EVA|SBS|PLA)(?=$|[\s_\-@)])",
    re.IGNORECASE,
)
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")
_SEPARATORS_RE = re.compile(r"[\W_]+", re.UNICODE)
_GENERIC_VENDORS = {"generic", "unknown", "default", "custom", "system"}
_BOOKKEEPING_KEYS = {
    "bundle_id",
    "fhub_draft_id",
    "fhub_id",
    "fhub_source",
    "setting_id",
    "filament_settings_id",
    "updated_at",
    "user_id",
}


@dataclass
class _CatalogIndex:
    brands: list[Brand] = field(default_factory=list)
    brand_aliases: dict[str, int] = field(default_factory=dict)
    filaments_by_brand: dict[int, list[Filament]] = field(default_factory=dict)
    local_color_names: dict[int, list[str]] = field(default_factory=dict)
    filament_redirects: dict[int, set[str]] = field(default_factory=dict)


async def _load_catalog_index(
    db: AsyncSession,
    vendors: list[str],
) -> _CatalogIndex:
    """Load every candidate needed for a page of drafts in a fixed query count."""
    vendor_names = {vendor.casefold() for vendor in vendors if vendor}
    vendor_slugs = {slugify(vendor, "") for vendor in vendors if vendor}
    vendor_slugs.discard("")
    index = _CatalogIndex()
    if not vendor_names and not vendor_slugs:
        return index

    brand_conditions = []
    if vendor_names:
        brand_conditions.append(func.lower(Brand.name).in_(vendor_names))
    if vendor_slugs:
        brand_conditions.append(Brand.slug.in_(vendor_slugs))
    index.brands = list(await db.scalars(
        select(Brand).where(Brand.active.is_(True), or_(*brand_conditions))
    ))

    aliases = []
    if vendor_slugs:
        aliases = list(await db.scalars(
            select(BrandSlugRedirect).where(
                BrandSlugRedirect.old_slug.in_(vendor_slugs)
            )
        ))
    known_brand_ids = {brand.id for brand in index.brands}
    missing_alias_ids = {
        alias.brand_id for alias in aliases if alias.brand_id not in known_brand_ids
    }
    if missing_alias_ids:
        index.brands.extend(await db.scalars(
            select(Brand).where(
                Brand.id.in_(missing_alias_ids),
                Brand.active.is_(True),
            )
        ))
    active_brand_ids = {brand.id for brand in index.brands}
    index.brand_aliases = {
        alias.old_slug: alias.brand_id
        for alias in aliases
        if alias.brand_id in active_brand_ids
    }
    if not active_brand_ids:
        return index

    filaments = list(await db.scalars(
        select(Filament)
        .where(
            Filament.active.is_(True),
            Filament.brand_id.in_(active_brand_ids),
        )
        .order_by(Filament.id.asc())
    ))
    for filament in filaments:
        index.filaments_by_brand.setdefault(filament.brand_id, []).append(filament)
    filament_ids = [filament.id for filament in filaments]
    if not filament_ids:
        return index

    for filament_id, market_color_name in await db.execute(
        select(
            FilamentCountryCell.filament_id,
            FilamentCountryCell.market_color_name,
        ).where(
            FilamentCountryCell.filament_id.in_(filament_ids),
            FilamentCountryCell.market_color_name.is_not(None),
        )
    ):
        index.local_color_names.setdefault(filament_id, []).append(market_color_name)
    for filament_id, old_slug in await db.execute(
        select(
            FilamentSlugRedirect.filament_id,
            FilamentSlugRedirect.old_slug,
        ).where(FilamentSlugRedirect.filament_id.in_(filament_ids))
    ):
        index.filament_redirects.setdefault(filament_id, set()).add(old_slug)
    return index


def _first(settings: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = settings.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value is not None and str(value).strip() not in {"", "nil"}:
            return value
    return None


def _text(settings: dict[str, Any], *keys: str) -> str | None:
    value = _first(settings, *keys)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _number(settings: dict[str, Any], *keys: str) -> float | None:
    value = _first(settings, *keys)
    if value is None:
        return None
    try:
        return float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def _normalize(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold().replace("ё", "е")
    return _SEPARATORS_RE.sub(" ", normalized).strip()


def _profile_product_name(name: str, vendor: str | None = None) -> str | None:
    cleaned = re.sub(r"\s*(?:\[fh\]|@fh|@FilamentHub)\s*", " ", name, flags=re.IGNORECASE)
    cleaned = cleaned.split(" @", 1)[0].strip(" -_")
    if vendor:
        cleaned = re.sub(
            rf"^\s*{re.escape(vendor)}(?:\s+|[-_:]+)",
            "",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        ).strip(" -_")
    return cleaned or None


async def _match_brand(
    db: AsyncSession,
    vendor: str | None,
    catalog_index: _CatalogIndex | None = None,
) -> PresetDraftCatalogMatch | None:
    if not vendor or _normalize(vendor) in _GENERIC_VENDORS:
        return None
    vendor_slug = slugify(vendor, "")
    if catalog_index is not None:
        direct = [
            brand
            for brand in catalog_index.brands
            if _normalize(brand.name) == _normalize(vendor)
            or brand.slug == vendor_slug
        ]
        if direct:
            brand = sorted(direct, key=lambda item: (-int(item.verified), item.id))[0]
            return PresetDraftCatalogMatch(
                id=brand.id,
                name=brand.name,
                confidence="exact",
                reasons=["brand_name_or_slug"],
            )
        alias_brand_id = catalog_index.brand_aliases.get(vendor_slug)
        if alias_brand_id is None:
            return None
        brand = next(
            (item for item in catalog_index.brands if item.id == alias_brand_id),
            None,
        )
        if brand is None:
            return None
        return PresetDraftCatalogMatch(
            id=brand.id,
            name=brand.name,
            confidence="strong",
            reasons=["brand_historical_alias"],
        )

    brand = await db.scalar(
        select(Brand)
        .where(
            Brand.active.is_(True),
            (func.lower(Brand.name) == vendor.casefold()) | (Brand.slug == vendor_slug),
        )
        .order_by(Brand.verified.desc(), Brand.id.asc())
        .limit(1)
    )
    if brand is not None:
        return PresetDraftCatalogMatch(
            id=brand.id,
            name=brand.name,
            confidence="exact",
            reasons=["brand_name_or_slug"],
        )

    alias = await db.scalar(
        select(BrandSlugRedirect)
        .where(BrandSlugRedirect.old_slug == vendor_slug)
        .limit(1)
    )
    if alias is None:
        return None
    brand = await db.get(Brand, alias.brand_id)
    if brand is None or not brand.active:
        return None
    return PresetDraftCatalogMatch(
        id=brand.id,
        name=brand.name,
        confidence="strong",
        reasons=["brand_historical_alias"],
    )


async def _match_filaments(
    db: AsyncSession,
    *,
    brand: PresetDraftCatalogMatch | None,
    product_name: str | None,
    preset_name: str,
    material_type: str | None,
    color_hex: str | None,
    catalog_index: _CatalogIndex | None = None,
) -> list[PresetDraftCatalogMatch]:
    if brand is None:
        return []
    if catalog_index is not None:
        filaments = list(catalog_index.filaments_by_brand.get(brand.id, []))
        if material_type:
            filaments = [
                filament
                for filament in filaments
                if _normalize(filament.material_type) == _normalize(material_type)
            ]
    else:
        query = select(Filament).where(
            Filament.active.is_(True),
            Filament.brand_id == brand.id,
        )
        if material_type:
            query = query.where(func.lower(Filament.material_type) == material_type.casefold())
        filaments = list(await db.scalars(query.order_by(Filament.id.asc()).limit(200)))
    if not filaments:
        return []

    if catalog_index is not None:
        local_color_names = catalog_index.local_color_names
        redirects = catalog_index.filament_redirects
    else:
        filament_ids = [item.id for item in filaments]
        local_color_names: dict[int, list[str]] = {}
        for filament_id, market_color_name in await db.execute(
            select(
                FilamentCountryCell.filament_id,
                FilamentCountryCell.market_color_name,
            ).where(
                FilamentCountryCell.filament_id.in_(filament_ids),
                FilamentCountryCell.market_color_name.is_not(None),
            )
        ):
            local_color_names.setdefault(filament_id, []).append(market_color_name)
        redirects: dict[int, set[str]] = {}
        for filament_id, old_slug in await db.execute(
            select(
                FilamentSlugRedirect.filament_id,
                FilamentSlugRedirect.old_slug,
            ).where(FilamentSlugRedirect.filament_id.in_(filament_ids))
        ):
            redirects.setdefault(filament_id, set()).add(old_slug)

    target = _normalize(product_name or preset_name)
    target_slug = slugify(product_name or preset_name, "")
    target_tokens = set(target.split())
    scored: list[tuple[int, PresetDraftCatalogMatch]] = []
    for filament in filaments:
        names = [filament.name]
        if filament.color_name:
            names.append(f"{filament.name} {filament.color_name}")
        names.extend(
            f"{filament.name} {local_name}"
            for local_name in local_color_names.get(filament.id, [])
        )
        normalized_names = {_normalize(name) for name in names if name}
        reasons: list[str] = []
        score = 0
        confidence = "possible"
        if target and target in normalized_names:
            score = 100
            confidence = "exact"
            reasons.append("product_name")
        elif target_slug and (
            target_slug == filament.slug
            or target_slug in redirects.get(filament.id, set())
        ):
            score = 95
            confidence = "exact"
            reasons.append("product_slug_or_alias")
        else:
            filament_tokens = set(_normalize(filament.name).split())
            overlap = len(target_tokens & filament_tokens)
            if filament_tokens and filament_tokens <= target_tokens:
                score += 60
                confidence = "strong"
                reasons.append("product_tokens")
            elif overlap:
                score += min(35, overlap * 15)
                reasons.append("partial_product_tokens")
            if material_type and _normalize(filament.material_type) == _normalize(material_type):
                score += 15
                reasons.append("material_type")
            if color_hex and filament.color_hex and color_hex.upper() == filament.color_hex.upper():
                score += 20
                reasons.append("color_hex")
                if score >= 70:
                    confidence = "strong"
        if score <= 0:
            continue
        scored.append((score, PresetDraftCatalogMatch(
            id=filament.id,
            name=filament.name,
            brand_id=filament.brand_id,
            material_type=filament.material_type,
            color_name=filament.color_name,
            confidence=confidence,
            reasons=reasons,
        )))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [item for _score, item in scored[:5]]


@lru_cache(maxsize=1)
def _material_defaults() -> dict[str, dict[str, Any]]:
    path = Path(__file__).resolve().parent.parent / "data" / "material_defaults.json"
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    data.pop("_comment", None)
    return data


def _add(
    suggestions: dict[str, PresetDraftSuggestion],
    field: str,
    value: str | float | None,
    *,
    source: str,
    confidence: str,
    direct: bool,
) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return
    suggestions[field] = PresetDraftSuggestion(
        value=value,
        source=source,
        confidence=confidence,
        direct=direct,
    )


async def analyze_preset_draft(
    db: AsyncSession,
    preset: Preset,
    *,
    catalog_index: _CatalogIndex | None = None,
    demand_count: int | None = None,
) -> PresetDraftAnalysisResponse:
    settings, evidence_kind = latest_evidence_settings(
        preset.import_evidence,
        preset.orcaslicer_settings,
    )
    trusted_catalog_identity = evidence_kind == "orca_capture"
    identity_source = "orca" if trusted_catalog_identity else "stored_snapshot"
    identity_confidence = "high" if trusted_catalog_identity else "suggested"
    signature = preset.demand_signature or preset_demand_signature(settings, preset.name)
    if demand_count is None and signature:
        demand_count = (await demand_counts(db, {signature})).get(signature, 0)
    if signature and preset.user_id is not None:
        # Old drafts may not have the persisted signature yet; the visible row
        # still represents one real independent observation.
        demand_count = max(demand_count or 0, 1)
    suggestions: dict[str, PresetDraftSuggestion] = {}

    vendor = _text(settings, "filament_vendor")
    generic_source = _normalize(vendor) in _GENERIC_VENDORS
    material_type = _text(settings, "filament_type")
    if material_type:
        material_type = material_type.upper()
    else:
        match = _MATERIAL_TOKEN_RE.search(preset.name or "")
        material_type = match.group(1).upper() if match else None

    raw_color = _text(settings, "filament_colour", "default_filament_colour")
    color = raw_color[:7].upper() if raw_color and _HEX_RE.fullmatch(raw_color) else None

    if not generic_source:
        _add(
            suggestions,
            "brand_name",
            vendor,
            source=identity_source,
            confidence=identity_confidence,
            direct=trusted_catalog_identity,
        )
    material_type_from_settings = bool(_text(settings, "filament_type"))
    _add(
        suggestions,
        "material_type",
        material_type,
        source=identity_source if material_type_from_settings else "profile_name",
        confidence=identity_confidence if material_type_from_settings else "medium",
        direct=trusted_catalog_identity and material_type_from_settings,
    )
    _add(
        suggestions,
        "color_hex",
        color,
        source=identity_source,
        confidence=identity_confidence,
        direct=trusted_catalog_identity,
    )
    _add(
        suggestions,
        "diameter",
        _number(settings, "filament_diameter"),
        source=identity_source,
        confidence=identity_confidence,
        direct=trusted_catalog_identity,
    )
    _add(
        suggestions,
        "density",
        _number(settings, "filament_density"),
        source=identity_source,
        confidence=identity_confidence,
        direct=trusted_catalog_identity,
    )
    _add(
        suggestions,
        "filament_name",
        None if generic_source else _profile_product_name(preset.name, vendor),
        source="profile_name",
        confidence="medium",
        direct=False,
    )
    features = resolve_catalog_feature_codes(preset.name)
    if len(features.color_types) == 1:
        _add(
            suggestions,
            "visual_color_type",
            features.color_types[0],
            source="profile_name",
            confidence="medium",
            direct=False,
        )
    elif len(features.color_types) > 1:
        _add(
            suggestions,
            "visual_color_type",
            "multicolor",
            source="profile_name",
            confidence="suggested",
            direct=False,
        )
    if len(features.color_groups) == 1:
        _add(
            suggestions,
            "color_group",
            features.color_groups[0],
            source="profile_name",
            confidence="medium",
            direct=False,
        )

    nozzle = _number(settings, "nozzle_temperature")
    bed = _number(
        settings,
        "hot_plate_temp",
        "bed_temperature",
        "textured_plate_temp",
        "cool_plate_temp",
        "eng_plate_temp",
    )
    _add(suggestions, "extruder_temp", nozzle, source="orca", confidence="high", direct=True)
    _add(suggestions, "bed_temp", bed, source="orca", confidence="high", direct=True)

    # A genuinely absent value may get a visible FilamentHub suggestion. Exact
    # Orca values such as 200/60 are never treated as placeholders.
    defaults = _material_defaults().get(material_type or "", {})
    if "extruder_temp" not in suggestions:
        _add(
            suggestions,
            "extruder_temp",
            defaults.get("extruder_temp"),
            source="filamenthub_default",
            confidence="suggested",
            direct=False,
        )
    if "bed_temp" not in suggestions:
        _add(
            suggestions,
            "bed_temp",
            defaults.get("bed_temp"),
            source="filamenthub_default",
            confidence="suggested",
            direct=False,
        )
    if "density" not in suggestions:
        _add(
            suggestions,
            "density",
            defaults.get("filament_density"),
            source="filamenthub_default",
            confidence="suggested",
            direct=False,
        )

    brand_match = await _match_brand(db, vendor, catalog_index)
    suggested_name = suggestions.get("filament_name")
    filament_matches = await _match_filaments(
        db,
        brand=brand_match,
        product_name=str(suggested_name.value) if suggested_name is not None else None,
        preset_name=preset.name,
        material_type=material_type,
        color_hex=color,
        catalog_index=catalog_index,
    )

    confirmed = sorted(field for field, item in suggestions.items() if item.direct)
    proposed = sorted(field for field, item in suggestions.items() if not item.direct)
    technical_settings_count = sum(
        1 for key in settings if key not in _BOOKKEEPING_KEYS
    )
    preset_decisions: list[str] = []
    if "extruder_temp" not in confirmed:
        preset_decisions.append("confirm_nozzle_temperature")
    if "bed_temp" not in confirmed:
        preset_decisions.append("confirm_bed_temperature")

    catalog_decisions: list[str] = []
    brand_suggestion = suggestions.get("brand_name")
    if generic_source or not vendor:
        catalog_decisions.append("identify_brand")
    elif brand_match is None:
        catalog_decisions.append("confirm_new_brand")
    elif brand_suggestion is None or not brand_suggestion.direct:
        catalog_decisions.append("confirm_new_brand")
    if "material_type" not in confirmed:
        catalog_decisions.append("confirm_material_type")
    strong_matches = [
        item for item in filament_matches if item.confidence in {"exact", "strong"}
    ]
    if len(strong_matches) == 1 and trusted_catalog_identity:
        pass
    elif strong_matches:
        catalog_decisions.append("choose_catalog_filament")
    else:
        catalog_decisions.append("choose_or_create_filament")
    if "visual_color_type" in suggestions:
        catalog_decisions.append("confirm_color_structure")

    preset_readiness = 0
    if technical_settings_count:
        preset_readiness += 25
    if "extruder_temp" in confirmed:
        preset_readiness += 30
    if "bed_temp" in confirmed:
        preset_readiness += 20
    if "material_type" in confirmed:
        preset_readiness += 15
    if "flow_rate" in confirmed or "fan_speed" in confirmed:
        preset_readiness += 10

    catalog_readiness = 0
    if brand_match is not None and brand_suggestion is not None and brand_suggestion.direct:
        catalog_readiness += 30
    elif vendor and not generic_source:
        catalog_readiness += 15
    if "material_type" in confirmed:
        catalog_readiness += 25
    elif "material_type" in suggestions:
        catalog_readiness += 15
    if len(strong_matches) == 1 and trusted_catalog_identity:
        catalog_readiness += 35
    elif strong_matches or suggested_name is not None:
        catalog_readiness += 15
    if "color_hex" in confirmed:
        catalog_readiness += 10

    decision_count = len(preset_decisions) + len(catalog_decisions)
    if generic_source or len(strong_matches) > 1:
        review_state = "ambiguous"
    elif decision_count == 0:
        review_state = "ready"
    elif decision_count <= 2:
        review_state = "almost_ready"
    else:
        review_state = "needs_decision"
    return PresetDraftAnalysisResponse(
        preset_id=preset.id,
        evidence_kind=evidence_kind,
        suggestions=suggestions,
        brand_match=brand_match,
        filament_matches=filament_matches,
        confirmed_fields=confirmed,
        suggested_fields=proposed,
        preset_readiness_percent=min(100, preset_readiness),
        catalog_readiness_percent=min(100, catalog_readiness),
        technical_settings_count=technical_settings_count,
        preset_decisions=preset_decisions,
        catalog_decisions=catalog_decisions,
        review_state=review_state,
        generic_source=generic_source,
        # Exact low-cardinality counts make a private import guessable. Product
        # UI starts at three independent users, so smaller groups stay hidden.
        similar_import_users=(demand_count or 0) if (demand_count or 0) >= 3 else 0,
    )


async def analyze_preset_drafts(
    db: AsyncSession,
    presets: list[Preset],
) -> list[PresetDraftAnalysisResponse]:
    """Analyze a visible draft page without one catalogue query set per card."""
    vendors = []
    signatures_by_preset: dict[int, str] = {}
    for preset in presets:
        settings, _evidence_kind = latest_evidence_settings(
            preset.import_evidence,
            preset.orcaslicer_settings,
        )
        vendor = _text(settings, "filament_vendor")
        if vendor and _normalize(vendor) not in _GENERIC_VENDORS:
            vendors.append(vendor)
        signature = preset.demand_signature or preset_demand_signature(
            settings, preset.name
        )
        if signature:
            signatures_by_preset[preset.id] = signature
    catalog_index = await _load_catalog_index(db, vendors)
    counts = await demand_counts(db, set(signatures_by_preset.values()))
    return [
        await analyze_preset_draft(
            db,
            preset,
            catalog_index=catalog_index,
            demand_count=counts.get(signatures_by_preset.get(preset.id, ""), 0),
        )
        for preset in presets
    ]
