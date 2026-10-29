"""Curation review policy layered on the existing catalog import planner."""

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Brand, CatalogCurationProposal, Filament, Preset
from app.schemas.catalog_curation import CatalogCurationCreate
from app.schemas.catalog_import import CatalogImportDraft
from app.services.catalog_master_import_service import (
    MAX_ROWS,
    SHEET_COLUMNS,
    CatalogMasterImportError,
    _present,
    build_plan,
)

SHEETS = {
    "Brands": ("brands", "brand_key"),
    "Filaments": ("filaments", "filament_key"),
    "BrandMarkets": ("brand_markets", "brand_key"),
    "FilamentMarkets": ("filament_markets", "filament_key"),
    "Presets": ("presets", "preset_key"),
}
CONTROL_FIELDS = {
    "_row",
    "enabled",
    "mode",
    "overwrite",
    "brand_key",
    "filament_key",
    "preset_key",
    "existing_brand",
    "existing_filament",
    "existing_preset",
    "active",
    "published",
    "verified",
    "price_hidden",
    "slug",
    "external_id",
}
PRICE_FIELDS = {"price", "price_per_kg", "currency", "price_display_unit"}
PACKAGING_FIELDS = {"spool_weight", "empty_spool_weight_g"}
SOURCE_FACT_FIELDS = (
    set(SHEET_COLUMNS["Filaments"])
    - CONTROL_FIELDS
    - PRICE_FIELDS
    - PACKAGING_FIELDS
)


def row_key(sheet: str, row: dict[str, Any]) -> str:
    key = str(row.get(SHEETS[sheet][1]) or "").strip()
    if sheet.endswith("Markets"):
        key += ":" + str(row.get("country") or "").strip().upper()
    return key


def validate_proposal(data: CatalogCurationCreate) -> None:
    """Validate shape and source references without inventing missing facts."""
    if not data.title.strip() or not data.coverage_note.strip():
        raise CatalogMasterImportError(
            "ERR_CATALOG_CURATION_INVALID", "Title and coverage are required"
        )
    total = sum(len(getattr(data.draft, field)) for field, _ in SHEETS.values())
    if total == 0 or total > MAX_ROWS:
        raise CatalogMasterImportError(
            "ERR_CATALOG_CURATION_INVALID", "Proposal row count is invalid"
        )
    if len(data.model_dump_json().encode("utf-8")) > 5 * 1024 * 1024:
        raise CatalogMasterImportError("ERR_CATALOG_CURATION_INVALID", "Proposal is too large")
    fields_by_row: dict[tuple[str, str], set[str]] = {}
    for sheet, (field, _) in SHEETS.items():
        for row in getattr(data.draft, field):
            unknown = set(row) - set(SHEET_COLUMNS[sheet]) - {"_row"}
            if unknown:
                raise CatalogMasterImportError(
                    "ERR_CATALOG_CURATION_INVALID",
                    f"Unknown {sheet} fields: {', '.join(sorted(unknown))}",
                )
            if any(_present(row.get(name)) for name in PRICE_FIELDS):
                raise CatalogMasterImportError(
                    "ERR_CATALOG_CURATION_INVALID",
                    "Curation proposals cannot set prices or currency",
                )
            if sheet == "Filaments" and any(_present(row.get(name)) for name in PACKAGING_FIELDS):
                raise CatalogMasterImportError(
                    "ERR_CATALOG_CURATION_INVALID",
                    "Curation materials cannot set packaging properties",
                )
            # Curation does not confer manufacturer verification.
            if sheet == "Brands" and _present(row.get("verified")):
                raise CatalogMasterImportError(
                    "ERR_CATALOG_CURATION_INVALID", "Curation cannot verify a manufacturer"
                )
            key = (sheet, row_key(sheet, row))
            if key in fields_by_row:
                raise CatalogMasterImportError(
                    "ERR_CATALOG_CURATION_INVALID", "Duplicate proposal row key"
                )
            fields_by_row[key] = set(row)
    seen = set()
    for item in data.evidence:
        identity = (item.sheet, item.key, item.field)
        if identity in seen or item.field not in fields_by_row.get((item.sheet, item.key), set()):
            raise CatalogMasterImportError(
                "ERR_CATALOG_CURATION_INVALID", "Evidence must uniquely reference a proposed field"
            )
        seen.add(identity)
    filament_keys = {row_key("Filaments", row) for row in data.draft.filaments}
    unmapped_seen = set()
    for fact in data.unmapped_facts:
        if fact.filament_key not in filament_keys:
            raise CatalogMasterImportError(
                "ERR_CATALOG_CURATION_INVALID",
                "Unmapped facts must reference a proposed filament row",
            )
        identity = (fact.filament_key, fact.property_name.casefold())
        if identity in unmapped_seen:
            raise CatalogMasterImportError(
                "ERR_CATALOG_CURATION_INVALID", "Duplicate unmapped fact for a filament property"
            )
        unmapped_seen.add(identity)
    unmapped_signatures = {
        (
            fact.filament_key,
            fact.property_name.casefold(),
            fact.value_summary.casefold(),
        )
        for fact in data.unmapped_facts
    }
    source_fact_seen = set()
    for fact in data.source_facts:
        if fact.filament_key not in filament_keys:
            raise CatalogMasterImportError(
                "ERR_CATALOG_CURATION_INVALID",
                "Source facts must reference a proposed filament row",
            )
        signature = (fact.filament_key, fact.property_name.casefold())
        if signature in source_fact_seen:
            raise CatalogMasterImportError(
                "ERR_CATALOG_CURATION_INVALID", "Duplicate source fact for a filament property"
            )
        source_fact_seen.add(signature)
        if fact.disposition == "unsupported":
            unsupported_signature = (
                fact.filament_key,
                fact.property_name.casefold(),
                fact.value_summary.casefold(),
            )
            if unsupported_signature not in unmapped_signatures:
                raise CatalogMasterImportError(
                    "ERR_CATALOG_CURATION_INVALID",
                    "Unsupported source facts must link to a matching unmapped fact",
                )
        if fact.disposition == "mapped":
            row = next(
                row for row in data.draft.filaments if row_key("Filaments", row) == fact.filament_key
            )
            for field in fact.mapped_fields:
                if field not in SOURCE_FACT_FIELDS:
                    raise CatalogMasterImportError(
                        "ERR_CATALOG_CURATION_INVALID",
                        f"Source fact references a non-mappable Filaments field: {field}",
                    )
                value = row.get(field)
                if value in (None, "", [], {}):
                    raise CatalogMasterImportError(
                        "ERR_CATALOG_CURATION_INVALID",
                        f"Mapped source fact requires a proposed value for {field}",
                    )
                if ("Filaments", fact.filament_key, field) not in seen:
                    raise CatalogMasterImportError(
                        "ERR_CATALOG_CURATION_INVALID",
                        f"Mapped source fact requires field evidence for {field}",
                    )


def proposal_digest(proposal: CatalogCurationProposal) -> str:
    snapshot = {
        "id": proposal.id,
        "revision": proposal.revision,
        "draft": proposal.draft,
        "evidence": proposal.evidence,
        "unmapped_facts": proposal.unmapped_facts,
        "source_facts": getattr(proposal, "source_facts", []) or [],
        "coverage_note": proposal.coverage_note,
        "title": proposal.title,
    }
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


async def build_curation_plan(
    db: AsyncSession,
    proposal: CatalogCurationProposal,
    *,
    admin_user_id: int,
    gate: Any = None,
) -> tuple[CatalogImportDraft, list[dict[str, Any]]]:
    # Imported here: the claims module reads this module's row helpers.
    from app.services.catalog_quote_claims import gated_source_facts, quote_gate

    draft = CatalogImportDraft.model_validate(proposal.draft)
    plan = await build_plan(db, draft, admin_user_id=admin_user_id, curation=True)
    evidence = {(item["sheet"], item["key"], item["field"]) for item in proposal.evidence}
    # A quote the server could not verify makes its fact unresolved and blocks the
    # row; proposals without quotes are untouched.
    gate = gate if gate is not None else await quote_gate(db, proposal)
    source_facts_by_key: dict[str, list[Any]] = {}
    for fact in gated_source_facts(getattr(proposal, "source_facts", []) or [], gate):
        source_facts_by_key.setdefault(fact["filament_key"], []).append(fact)
    planned_rows = iter(plan)
    models = {
        "Brands": (Brand, "existing_brand"),
        "Filaments": (Filament, "existing_filament"),
        "Presets": (Preset, "existing_preset"),
    }
    for sheet, (field, _) in SHEETS.items():
        for row in getattr(draft, field):
            item = next(planned_rows)
            if item["status"] == "skipped":
                continue
            problems = (
                [item["message"]] if item["status"] == "error" and item.get("message") else []
            )
            fact_review = None
            key = row_key(sheet, row)
            if sheet == "Filaments":
                if row.get("mode") == "create":
                    # Availability is not required: like a user-created material it
                    # defaults to "available".
                    diameter = row.get("diameter")
                    if not str(diameter if diameter is not None else "").strip():
                        problems.append("Create requires explicit values for: diameter")
                if row.get("enabled", True) is not False:
                    facts = source_facts_by_key.get(key, [])
                    if not facts:
                        fact_review = (
                            "Manufacturer facts captured 0/0 (mapped 0, unsupported 0, "
                            "unresolved 0); add source facts before enabling this material"
                        )
                        problems.append(fact_review)
                    else:
                        mapped_count = sum(fact["disposition"] == "mapped" for fact in facts)
                        unsupported_count = sum(
                            fact["disposition"] == "unsupported" for fact in facts
                        )
                        unresolved_count = sum(
                            fact["disposition"] == "unresolved" for fact in facts
                        )
                        captured_count = mapped_count + unsupported_count
                        fact_review = (
                            f"Manufacturer facts captured {captured_count}/{len(facts)} "
                            f"(mapped {mapped_count}, unsupported {unsupported_count}, "
                            f"unresolved {unresolved_count})"
                        )
                        if captured_count * 5 < len(facts) * 4:
                            problems.append(
                                fact_review + "; at least 80% must be accounted for"
                            )
                        if unresolved_count:
                            problems.append(
                                fact_review
                                + f"; resolve {unresolved_count} unresolved manufacturer source fact(s)"
                            )
            missing = sorted(
                name
                for name, value in row.items()
                if name not in CONTROL_FIELDS
                and _present(value)
                and (sheet, key, name) not in evidence
            )
            if missing:
                problems.append("Missing evidence for: " + ", ".join(missing))
            unverified = sorted(
                f"{name} ({gate.blocking('evidence', sheet, key, name)})"
                for name, value in row.items()
                if name not in CONTROL_FIELDS
                and _present(value)
                and gate.blocking("evidence", sheet, key, name)
            )
            if sheet == "Filaments":
                unverified += sorted(
                    f"{fact['property_name']} ({status})"
                    for scope, facts in (
                        ("source_fact", getattr(proposal, "source_facts", []) or []),
                        (
                            "unmapped_fact",
                            [
                                fact
                                for fact in proposal.unmapped_facts or []
                                if fact.get("public_action") == "publish"
                            ],
                        ),
                    )
                    for fact in facts
                    if fact["filament_key"] == key
                    and (
                        status := gate.blocking(
                            scope, "", key, str(fact["property_name"]).casefold()
                        )
                    )
                )
            if unverified:
                problems.append(
                    "Source quote not verified for: " + ", ".join(unverified)
                    + "; verify the sources or correct the quote"
                )
            if sheet in models:
                model, reference_field = models[sheet]
                mode = row.get("mode")
                reference = str(row.get(reference_field) or "").strip()
                if mode not in {"create", "update"}:
                    problems.append("Choose explicit create or update mode")
                elif mode == "create" and reference:
                    problems.append("Create mode cannot reference an existing record")
                elif mode == "update":
                    if not reference:
                        problems.append("Update requires an explicit existing record")
                    elif item.get("target_id") is not None:
                        target = await db.get(model, item["target_id"])
                        # Never accept the planner's natural-identity fallback for
                        # a mistyped reference. Numeric IDs or canonical slugs only.
                        matches = target is not None and (
                            (reference.isdecimal() and int(reference) == target.id)
                            or (
                                not reference.isdecimal()
                                and reference.casefold() == getattr(target, "slug", "").casefold()
                            )
                        )
                        if not matches:
                            problems.append(
                                "Existing record reference does not match the selected target"
                            )
            if problems:
                if fact_review and not any(problem.startswith(fact_review) for problem in problems):
                    problems.append(fact_review)
                item.update(status="error", message="; ".join(problems))
    return draft, plan
